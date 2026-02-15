import discord
from discord.ext import commands, tasks
import random
import json
import os
import asyncio
import time
from datetime import datetime, timedelta
from collections import defaultdict

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

DB_FILE = "user_data.json"
SHOP_FILE = "shop_data.json"
GANG_FILE = "gang_data.json"
BATTLE_FILE = "battle_data.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(user_db, f, indent=4)

def load_shop():
    if os.path.exists(SHOP_FILE):
        try:
            with open(SHOP_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_shop():
    with open(SHOP_FILE, "w") as f:
        json.dump(shop_db, f, indent=4)

def load_gangs():
    if os.path.exists(GANG_FILE):
        try:
            with open(GANG_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_gangs():
    with open(GANG_FILE, "w") as f:
        json.dump(gang_db, f, indent=4)

def load_battles():
    if os.path.exists(BATTLE_FILE):
        try:
            with open(BATTLE_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_battles():
    with open(BATTLE_FILE, "w") as f:
        json.dump(battle_db, f, indent=4)

user_db = load_db()
shop_db = load_shop()
gang_db = load_gangs()
battle_db = load_battles()

active_games = {}
active_roulettes = {}
active_slots = {}
active_poker = {}
active_horse_races = {}

def get_user(uid):
    uid_str = str(uid)
    if uid_str not in user_db:
        user_db[uid_str] = {
            "balance": 0,
            "last_work": 0,
            "blacklisted": False,
            "loan": 0,
            "loan_time": 0,
            "last_nag_time": 0,
            "loan_channel": 0,
            "inventory": {},
            "level": 1,
            "exp": 0,
            "daily_streak": 0,
            "last_daily": 0,
            "total_bet": 0,
            "total_win": 0,
            "total_loss": 0,
            "achievements": [],
            "gang": None,
            "vip_level": 0,
            "vip_expires": 0,
            "multiplier": 1.0,
            "last_crime": 0,
            "last_rob": 0,
            "protection": 0
        }
        save_db()
    return user_db[uid_str]

def check_blacklist(d):
    if d.get("balance", 0) < -100000:
        d["blacklisted"] = True
    else:
        d["blacklisted"] = False
    return d.get("blacklisted", False)

def add_exp(uid, amount):
    d = get_user(uid)
    d['exp'] = d.get('exp', 0) + amount
    d['level'] = d.get('level', 1)
    required = d['level'] * 100
    if d['exp'] >= required:
        d['exp'] -= required
        d['level'] += 1
        save_db()
        return True
    save_db()
    return False

@tasks.loop(minutes=1)
async def check_loans():
    now = time.time()
    for uid, data in user_db.items():
        if data.get("loan", 0) > 0:
            loan_start = data.get("loan_time", 0)
            last_nag = data.get("last_nag_time", 0)
            if now - loan_start >= 600:
                if now - last_nag >= 600:
                    channel_id = data.get("loan_channel")
                    channel = bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(f"<@{uid}> 欠钱不还，全家不欢")
                            user_db[uid]["last_nag_time"] = now
                            save_db()
                        except: pass

@tasks.loop(hours=1)
async def check_vip_expiry():
    now = time.time()
    for uid, data in user_db.items():
        if data.get("vip_expires", 0) > 0 and now > data["vip_expires"]:
            data["vip_level"] = 0
            data["vip_expires"] = 0
            data["multiplier"] = 1.0
    save_db()

class BlackjackPvp:
    def __init__(self, bet, dealer_mode, host):
        self.bet = bet
        self.dealer_mode = dealer_mode
        self.host = host
        self.players = []
        self.dealer_user = None
        self.deck = self.create_deck()
        self.state = "joining"
        self.dealer_hand = []
        self.current_player_idx = 0

    def create_deck(self):
        s, r = ['♠️', '♥️', '♦️', '♣️'], ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        d = [(suit, rank) for suit in s for rank in r]
        random.shuffle(d)
        return d

    def calculate_score(self, hand):
        score, aces = 0, 0
        for s, r in hand:
            if r in ['J', 'Q', 'K']: score += 10
            elif r == 'A': score += 11; aces += 1
            else: score += int(r)
        while score > 21 and aces: score -= 10; aces -= 1
        return score

    def format_hand(self, hand, hide=False):
        if not hand: return "🎴"
        if hide: return f"{hand[0][0]}{hand[0][1]} 🎴"
        return " ".join([f"{s}{r}" for s, r in hand])

class BJGameView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=180)
        self.game = game

    @discord.ui.button(label="加入闲家", style=discord.ButtonStyle.primary)
    async def join_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.game.state != "joining": return
        if any(p['user'].id == interaction.user.id for p in self.game.players) or (self.game.dealer_user and self.game.dealer_user.id == interaction.user.id):
            return
        
        d = get_user(interaction.user.id)
        if check_blacklist(d) or d.get('balance', 0) < self.game.bet: return
        
        if len(self.game.players) >= 10: return
        
        self.game.players.append({"user": interaction.user, "hand": [], "done": False, "score": 0, "status": "准备中", "mult": 0})
        await self.update_panel(interaction)

    @discord.ui.button(label="抢庄", style=discord.ButtonStyle.danger)
    async def join_dealer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.game.state != "joining" or self.game.dealer_mode != "player": return
        if self.game.dealer_user: return
        if any(p['user'].id == interaction.user.id for p in self.game.players): return
        
        d = get_user(interaction.user.id)
        if check_blacklist(d) or d.get('balance', 0) < (self.game.bet * 5): return
        
        self.game.dealer_user = interaction.user
        await self.update_panel(interaction)

    @discord.ui.button(label="开始游戏", style=discord.ButtonStyle.success)
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host.id:
            return await interaction.response.send_message("只有发起人能开始", ephemeral=True)
        
        await interaction.response.defer()
        if not self.game.players: return
        if self.game.dealer_mode == "player" and not self.game.dealer_user: return
        
        self.game.state = "dealing"
        for p in self.game.players:
            p['hand'] = [self.game.deck.pop(), self.game.deck.pop()]
            p['status'] = "进行中"
        self.game.dealer_hand = [self.game.deck.pop(), self.game.deck.pop()]
        
        await self.run_game(interaction)

    async def update_panel(self, interaction):
        embed = discord.Embed(title="🃏 21点玩家对决", description=f"赌注: ￥{self.game.bet}\n模式: {'玩家当庄' if self.game.dealer_mode == 'player' else '机器人当庄'}", color=0x3498db)
        dealer_name = self.game.dealer_user.display_name if self.game.dealer_user else ("机器人" if self.game.dealer_mode == 'bot' else "等待抢庄...")
        embed.add_field(name="🏰 庄家", value=dealer_name, inline=False)
        players_list = "\n".join([f"• {p['user'].display_name}" for p in self.game.players]) or "等待加入..."
        embed.add_field(name="👤 闲家列表", value=players_list, inline=False)
        await interaction.edit_original_response(embed=embed, view=self)

    async def run_game(self, interaction):
        ds = self.game.calculate_score(self.game.dealer_hand)
        for p in self.game.players:
            ps = self.game.calculate_score(p['hand'])
            if ps == 21 and ds == 21: p['done'], p['mult'], p['status'] = True, 0, "平局 (双BJ)"
            elif ps == 21: p['done'], p['mult'], p['status'] = True, 2, "Blackjack!"
            elif ds == 21: p['done'], p['mult'], p['status'] = True, -2, "被BJ秒杀"
        
        if ds == 21: await self.settle(interaction)
        else: await self.show_play_screen(interaction)

    async def show_play_screen(self, interaction):
        if self.game.current_player_idx >= len(self.game.players):
            await self.dealer_phase(interaction)
            return

        p = self.game.players[self.game.current_player_idx]
        if p['done']:
            self.game.current_player_idx += 1
            await self.show_play_screen(interaction)
            return

        embed = discord.Embed(title="🃏 正在回合中", color=0xf1c40f)
        embed.add_field(name="🏰 庄家", value=self.game.format_hand(self.game.dealer_hand, hide=True), inline=False)
        for i, pl in enumerate(self.game.players):
            focus = "➡️ " if i == self.game.current_player_idx else ""
            embed.add_field(name=f"{focus}{pl['user'].display_name}", value=f"{self.game.format_hand(pl['hand'])}\n分: {self.game.calculate_score(pl['hand'])} | {pl['status']}", inline=True)
        
        await interaction.edit_original_response(embed=embed, view=PlayActionView(self))

    async def dealer_phase(self, interaction):
        if self.game.dealer_mode == "bot":
            while self.game.calculate_score(self.game.dealer_hand) < 17:
                self.game.dealer_hand.append(self.game.deck.pop())
            await self.settle(interaction)
        else:
            embed = discord.Embed(title="🏰 庄家回合", color=0xff0000)
            embed.add_field(name=f"庄家: {self.game.dealer_user.display_name}", value=f"{self.game.format_hand(self.game.dealer_hand)}\n分: {self.game.calculate_score(self.game.dealer_hand)}", inline=False)
            await interaction.edit_original_response(embed=embed, view=DealerActionView(self))

    async def settle(self, interaction):
        ds = self.game.calculate_score(self.game.dealer_hand)
        embed = discord.Embed(title="🏁 结算面板", color=0x2ecc71)
        embed.add_field(name="🏰 庄家结果", value=f"{self.game.format_hand(self.game.dealer_hand)}\n最终点数: {ds}", inline=False)
        
        total_payout = 0
        for p in self.game.players:
            if not p['done']:
                ps = self.game.calculate_score(p['hand'])
                if ds > 21: p['mult'], p['status'] = 1, "赢 (庄爆)"
                elif ps > ds: p['mult'], p['status'] = 1, "赢"
                elif ps < ds: p['mult'], p['status'] = -1, "输"
                else: p['mult'], p['status'] = 0, "平局"
            reward = int(self.game.bet * p['mult'])
            total_payout += reward
            ud = get_user(p['user'].id)
            ud['balance'] = ud.get('balance', 0) + reward
            if reward > 0:
                ud['total_win'] = ud.get('total_win', 0) + reward
                add_exp(p['user'].id, 10)
            elif reward < 0:
                ud['total_loss'] = ud.get('total_loss', 0) + abs(reward)
            check_blacklist(ud)
            embed.add_field(name=p['user'].display_name, value=f"{p['status']}\n盈亏: ￥{reward}\n余额: {ud['balance']}", inline=True)
        
        if self.game.dealer_user:
            ud_d = get_user(self.game.dealer_user.id)
            ud_d['balance'] = ud_d.get('balance', 0) - total_payout
            check_blacklist(ud_d)
            embed.set_footer(text=f"庄家 {self.game.dealer_user.display_name} 盈亏: ￥{-total_payout} | 余额: {ud_d['balance']}")
        
        save_db()
        await interaction.edit_original_response(embed=embed, view=None)

class PlayActionView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=60)
        self.mv = main_view

    @discord.ui.button(label="要牌", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.mv.game.players[self.mv.game.current_player_idx]
        if interaction.user.id != p['user'].id: return await interaction.response.send_message("不是你的回合", ephemeral=True)
        await interaction.response.defer()
        p['hand'].append(self.mv.game.deck.pop())
        score = self.mv.game.calculate_score(p['hand'])
        if len(p['hand']) == 5 and score <= 21: p['done'], p['mult'], p['status'] = True, 3, "五小龙!"
        elif len(p['hand']) == 5 and score > 21: p['done'], p['mult'], p['status'] = True, -2, "五张爆牌"
        elif score > 21: p['done'], p['mult'], p['status'] = True, -1, "爆牌"
        if p['done']: self.mv.game.current_player_idx += 1
        await self.mv.show_play_screen(interaction)

    @discord.ui.button(label="停牌", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = self.mv.game.players[self.mv.game.current_player_idx]
        if interaction.user.id != p['user'].id: return await interaction.response.send_message("不是你的回合", ephemeral=True)
        await interaction.response.defer()
        p['done'] = True
        self.mv.game.current_player_idx += 1
        await self.mv.show_play_screen(interaction)

class DealerActionView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=60)
        self.mv = main_view

    @discord.ui.button(label="庄家要牌", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.mv.game.dealer_user.id: return
        await interaction.response.defer()
        self.mv.game.dealer_hand.append(self.mv.game.deck.pop())
        score = self.mv.game.calculate_score(self.mv.game.dealer_hand)
        if score >= 21: await self.mv.settle(interaction)
        else:
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name=f"庄家: {self.mv.game.dealer_user.display_name}", value=f"{self.mv.game.format_hand(self.mv.game.dealer_hand)}\n分: {score}", inline=False)
            await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="庄家停牌", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.mv.game.dealer_user.id: return
        await interaction.response.defer()
        await self.mv.settle(interaction)

class RouletteGame:
    def __init__(self, host, channel):
        self.host = host
        self.channel = channel
        self.bets = {}
        self.state = "betting"
        
    def add_bet(self, user, bet_type, amount):
        if user.id not in self.bets:
            self.bets[user.id] = []
        self.bets[user.id].append({"type": bet_type, "amount": amount})
        
    def spin(self):
        return random.randint(0, 36)
    
    def get_color(self, num):
        if num == 0: return "green"
        red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
        return "red" if num in red_numbers else "black"
    
    def calculate_winnings(self, result):
        winnings = {}
        color = self.get_color(result)
        
        for uid, bets in self.bets.items():
            total = 0
            for bet in bets:
                bet_type = bet["type"]
                amount = bet["amount"]
                
                if bet_type == str(result):
                    total += amount * 35
                elif bet_type == "red" and color == "red":
                    total += amount * 2
                elif bet_type == "black" and color == "black":
                    total += amount * 2
                elif bet_type == "even" and result % 2 == 0 and result != 0:
                    total += amount * 2
                elif bet_type == "odd" and result % 2 == 1:
                    total += amount * 2
                elif bet_type == "low" and 1 <= result <= 18:
                    total += amount * 2
                elif bet_type == "high" and 19 <= result <= 36:
                    total += amount * 2
                else:
                    total -= amount
                    
            winnings[uid] = total
        return winnings

class RouletteView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=120)
        self.game = game
        
    @discord.ui.button(label="红色", style=discord.ButtonStyle.danger)
    async def bet_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.place_bet(interaction, "red")
        
    @discord.ui.button(label="黑色", style=discord.ButtonStyle.secondary)
    async def bet_black(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.place_bet(interaction, "black")
        
    @discord.ui.button(label="单数", style=discord.ButtonStyle.primary)
    async def bet_odd(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.place_bet(interaction, "odd")
        
    @discord.ui.button(label="双数", style=discord.ButtonStyle.primary)
    async def bet_even(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.place_bet(interaction, "even")
        
    async def spin_wheel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host.id:
            return await interaction.response.send_message("只有发起人能开始", ephemeral=True)
        await interaction.response.defer()
        result = self.game.spin()
        color = self.game.get_color(result)
        
        embed = discord.Embed(title="🎰 轮盘旋转中...", color=0xffd700)
        msg = await interaction.followup.send(embed=embed)
        
        for i in range(5):
            fake_num = random.randint(0, 36)
            fake_color = self.game.get_color(fake_num)
            color_emoji = "🔴" if fake_color == "red" else "⚫" if fake_color == "black" else "🟢"
            embed.description = f"{color_emoji} {fake_num}"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.5)
        
        color_emoji = "🔴" if color == "red" else "⚫" if color == "black" else "🟢"
        embed.title = "🎰 轮盘结果"
        embed.description = f"{color_emoji} **{result}** ({color})"
        
        winnings = self.game.calculate_winnings(result)
        results_text = ""
        
        for uid, amount in winnings.items():
            user_data = get_user(uid)
            user_data['balance'] += amount
            if amount > 0:
                user_data['total_win'] = user_data.get('total_win', 0) + amount
                add_exp(uid, 15)
            else:
                user_data['total_loss'] = user_data.get('total_loss', 0) + abs(amount)
            check_blacklist(user_data)
            user = await bot.fetch_user(int(uid))
            results_text += f"{user.display_name}: {'+' if amount >= 0 else ''}{amount}\n"
        
        save_db()
        embed.add_field(name="结算", value=results_text or "无投注", inline=False)
        await msg.edit(embed=embed, view=None)
        
        if self.game.channel.id in active_roulettes:
            del active_roulettes[self.game.channel.id]
    
    async def place_bet(self, interaction: discord.Interaction, bet_type: str):
        class BetAmountModal(discord.ui.Modal, title="下注金额"):
            amount = discord.ui.TextInput(label="金额", placeholder="输入下注金额", required=True)
            
            def __init__(self, game, bet_type):
                super().__init__()
                self.game = game
                self.bet_type = bet_type
            
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    amount = int(self.amount.value)
                    if amount <= 0:
                        return await interaction.response.send_message("金额无效", ephemeral=True)
                    
                    user_data = get_user(interaction.user.id)
                    if user_data.get('balance', 0) < amount:
                        return await interaction.response.send_message("余额不足", ephemeral=True)
                    
                    user_data['balance'] = user_data.get('balance', 0) - amount
                    save_db()
                    
                    self.game.add_bet(interaction.user, self.bet_type, amount)
                    await interaction.response.send_message(f"下注成功: {self.bet_type} ￥{amount}", ephemeral=True)
                except ValueError:
                    await interaction.response.send_message("请输入有效数字", ephemeral=True)
        
        await interaction.response.send_modal(BetAmountModal(self.game, bet_type))

class SlotMachine:
    def __init__(self):
        self.symbols = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
        self.weights = [30, 25, 20, 15, 8, 2]
        
    def spin(self):
        return random.choices(self.symbols, weights=self.weights, k=3)
    
    def calculate_payout(self, result, bet):
        if result[0] == result[1] == result[2]:
            if result[0] == "7️⃣": return bet * 100
            elif result[0] == "💎": return bet * 50
            elif result[0] == "🍇": return bet * 20
            elif result[0] == "🍊": return bet * 10
            elif result[0] == "🍋": return bet * 5
            elif result[0] == "🍒": return bet * 3
        elif result[0] == result[1] or result[1] == result[2]:
            return bet * 2
        return 0

class PokerGame:
    def __init__(self, host, ante):
        self.host = host
        self.ante = ante
        self.players = []
        self.deck = self.create_deck()
        self.community = []
        self.pot = 0
        self.current_bet = 0
        self.current_player_idx = 0
        self.stage = "preflop"
        
    def create_deck(self):
        suits = ['♠️', '♥️', '♦️', '♣️']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [(suit, rank) for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
    
    def deal_hands(self):
        for player in self.players:
            player['hand'] = [self.deck.pop(), self.deck.pop()]
            player['bet'] = self.ante
            player['folded'] = False
        self.pot = self.ante * len(self.players)
        
    def deal_flop(self):
        self.deck.pop()
        self.community = [self.deck.pop(), self.deck.pop(), self.deck.pop()]
        self.stage = "flop"
        
    def deal_turn(self):
        self.deck.pop()
        self.community.append(self.deck.pop())
        self.stage = "turn"
        
    def deal_river(self):
        self.deck.pop()
        self.community.append(self.deck.pop())
        self.stage = "river"
        
    def format_card(self, card):
        return f"{card[0]}{card[1]}"
    
    def evaluate_hand(self, hand, community):
        all_cards = hand + community
        return random.randint(1, 10)

class HorseRace:
    def __init__(self, race_id):
        self.race_id = race_id
        self.horses = {
            "1": {"name": "闪电", "speed": random.randint(70, 100), "position": 0},
            "2": {"name": "烈焰", "speed": random.randint(70, 100), "position": 0},
            "3": {"name": "疾风", "speed": random.randint(70, 100), "position": 0},
            "4": {"name": "雷霆", "speed": random.randint(70, 100), "position": 0},
            "5": {"name": "幽灵", "speed": random.randint(70, 100), "position": 0}
        }
        self.bets = {}
        self.finish_line = 100
        self.state = "betting"
        self.results = []
        
    def add_bet(self, user_id, horse_num, amount):
        if user_id not in self.bets:
            self.bets[user_id] = {}
        self.bets[user_id][horse_num] = amount
        
    def race_step(self):
        for horse_id, horse in self.horses.items():
            if horse['position'] < self.finish_line:
                horse['position'] += random.randint(5, horse['speed'] // 10)
                
    def check_finish(self):
        for horse_id, horse in self.horses.items():
            if horse['position'] >= self.finish_line and horse_id not in [r[0] for r in self.results]:
                self.results.append((horse_id, horse['name']))
        return len(self.results) == len(self.horses)
    
    def get_race_display(self):
        display = "🏁 赛马实况 🏁\n\n"
        for horse_id, horse in sorted(self.horses.items()):
            progress = min(20, int(horse['position'] / self.finish_line * 20))
            bar = "🟩" * progress + "⬜" * (20 - progress)
            display += f"{horse['name']}: {bar} {horse['position']}/{self.finish_line}\n"
        return display

class CrashGame:
    def __init__(self):
        self.multiplier = 1.00
        self.crashed = False
        self.crash_point = random.uniform(1.01, 10.0)
        self.players = {}
        
    def update(self):
        if not self.crashed:
            self.multiplier += random.uniform(0.01, 0.1)
            if self.multiplier >= self.crash_point:
                self.crashed = True
                self.multiplier = self.crash_point
        return self.crashed
    
    def add_player(self, user_id, bet):
        self.players[user_id] = {"bet": bet, "cashed_out": False, "cashout_mult": 0}
        
    def cashout(self, user_id):
        if user_id in self.players and not self.players[user_id]['cashed_out'] and not self.crashed:
            self.players[user_id]['cashed_out'] = True
            self.players[user_id]['cashout_mult'] = self.multiplier
            return True
        return False

@bot.tree.command(name="bj", description="21点多人对决")
@discord.app_commands.describe(amount="赌注", dealer="庄家模式")
@discord.app_commands.choices(dealer=[
    discord.app_commands.Choice(name="机器人当庄", value="bot"),
    discord.app_commands.Choice(name="玩家当庄", value="player")
])
async def bj(interaction: discord.Interaction, amount: int, dealer: str = "bot"):
    d = get_user(interaction.user.id)
    if check_blacklist(d) or amount <= 0: 
        return await interaction.response.send_message("金额无效或已被黑名单锁定", ephemeral=True)
    game = BlackjackPvp(amount, dealer, interaction.user)
    embed = discord.Embed(title="🃏 21点玩家对决", description=f"发起人: {interaction.user.mention}\n赌注: ￥{amount}\n庄家模式: {'玩家' if dealer == 'player' else '机器人'}\n\n等待闲家加入...", color=0x3498db)
    await interaction.response.send_message(embed=embed, view=BJGameView(game))

@bot.tree.command(name="roulette", description="轮盘赌")
async def roulette(interaction: discord.Interaction):
    if interaction.channel.id in active_roulettes:
        return await interaction.response.send_message("本频道已有进行中的轮盘游戏", ephemeral=True)
    
    game = RouletteGame(interaction.user, interaction.channel)
    active_roulettes[interaction.channel.id] = game
    
    embed = discord.Embed(
        title="🎰 轮盘赌场",
        description="选择你的投注类型并输入金额\n红色/黑色: 2倍\n单数/双数: 2倍\n具体数字: 36倍",
        color=0xff0000
    )
    await interaction.response.send_message(embed=embed, view=RouletteView(game))

@bot.tree.command(name="slots", description="老虎机")
async def slots(interaction: discord.Interaction, amount: int):
    d = get_user(interaction.user.id)
    if check_blacklist(d) or amount <= 0 or d.get('balance', 0) < amount:
        return await interaction.response.send_message("余额不足或金额无效", ephemeral=True)
    
    await interaction.response.defer()
    machine = SlotMachine()
    
    d['balance'] -= amount
    d['total_bet'] = d.get('total_bet', 0) + amount
    save_db()
    
    embed = discord.Embed(title="🎰 老虎机", color=0xffd700)
    embed.add_field(name="旋转中", value="🎰 | 🎰 | 🎰", inline=False)
    msg = await interaction.followup.send(embed=embed)
    
    for i in range(5):
        temp_result = machine.spin()
        embed.set_field_at(0, name="旋转中", value=f"{temp_result[0]} | {temp_result[1]} | {temp_result[2]}", inline=False)
        await msg.edit(embed=embed)
        await asyncio.sleep(0.3)
    
    result = machine.spin()
    payout = machine.calculate_payout(result, amount)
    
    if payout > 0:
        d['balance'] += payout
        d['total_win'] = d.get('total_win', 0) + payout
        add_exp(interaction.user.id, 20)
        status = f"🎉 赢得 ￥{payout}"
        color = 0x2ecc71
    else:
        d['total_loss'] = d.get('total_loss', 0) + amount
        status = "💀 未中奖"
        color = 0xe74c3c
    
    check_blacklist(d)
    save_db()
    
    embed.title = status
    embed.color = color
    embed.set_field_at(0, name="结果", value=f"{result[0]} | {result[1]} | {result[2]}", inline=False)
    embed.add_field(name="余额", value=f"￥{d['balance']}", inline=False)
    await msg.edit(embed=embed)

@bot.tree.command(name="crash", description="崩盘游戏")
async def crash(interaction: discord.Interaction, amount: int):
    d = get_user(interaction.user.id)
    if check_blacklist(d) or amount <= 0 or d.get('balance', 0) < amount:
        return await interaction.response.send_message("余额不足或金额无效", ephemeral=True)
    
    await interaction.response.defer()
    
    game = CrashGame()
    game.add_player(interaction.user.id, amount)
    
    d['balance'] = d.get('balance', 0) - amount
    save_db()
    
    embed = discord.Embed(title="🚀 崩盘游戏", description="点击按钮及时退出!", color=0x3498db)
    embed.add_field(name="倍数", value=f"{game.multiplier:.2f}x", inline=True)
    embed.add_field(name="投注", value=f"￥{amount}", inline=True)
    
    class CrashView(discord.ui.View):
        def __init__(self, game, user_id, bet):
            super().__init__(timeout=30)
            self.game = game
            self.user_id = user_id
            self.bet = bet
            self.msg = None
            
        @discord.ui.button(label="退出", style=discord.ButtonStyle.success)
        async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("这不是你的游戏", ephemeral=True)
            
            if self.game.cashout(self.user_id):
                await interaction.response.defer()
                winnings = int(self.bet * self.game.multiplier)
                user_data = get_user(self.user_id)
                user_data['balance'] = user_data.get('balance', 0) + winnings
                user_data['total_win'] = user_data.get('total_win', 0) + (winnings - self.bet)
                add_exp(self.user_id, 15)
                save_db()
                
                embed = self.msg.embeds[0]
                embed.title = f"✅ 成功退出!"
                embed.color = 0x2ecc71
                embed.set_field_at(0, name="退出倍数", value=f"{self.game.multiplier:.2f}x")
                embed.set_field_at(1, name="赢得", value=f"￥{winnings}")
                await self.msg.edit(embed=embed, view=None)
                self.stop()
    
    view = CrashView(game, interaction.user.id, amount)
    msg = await interaction.followup.send(embed=embed, view=view)
    view.msg = msg
    
    while not game.crashed and not game.players[interaction.user.id]['cashed_out']:
        await asyncio.sleep(0.5)
        game.update()
        embed.set_field_at(0, name="倍数", value=f"{game.multiplier:.2f}x")
        try:
            await msg.edit(embed=embed)
        except:
            break
    
    if game.crashed and not game.players[interaction.user.id]['cashed_out']:
        user_data = get_user(interaction.user.id)
        user_data['total_loss'] = user_data.get('total_loss', 0) + amount
        check_blacklist(user_data)
        save_db()
        
        embed.title = "💥 崩盘了!"
        embed.color = 0xe74c3c
        embed.set_field_at(0, name="崩盘点", value=f"{game.crash_point:.2f}x")
        embed.set_field_at(1, name="损失", value=f"￥{amount}")
        await msg.edit(embed=embed, view=None)

@bot.tree.command(name="horserace", description="赛马")
async def horserace(interaction: discord.Interaction):
    if interaction.channel.id in active_horse_races:
        return await interaction.response.send_message("本频道已有进行中的赛马", ephemeral=True)
    
    race = HorseRace(interaction.channel.id)
    active_horse_races[interaction.channel.id] = race
    
    embed = discord.Embed(title="🐴 赛马投注", description="选择一匹马进行投注!", color=0x8b4513)
    for horse_id, horse in race.horses.items():
        embed.add_field(
            name=f"{horse_id}号 - {horse['name']}",
            value=f"速度: {horse['speed']}/100",
            inline=True
        )
    
    class HorseRaceView(discord.ui.View):
        def __init__(self, race):
            super().__init__(timeout=60)
            self.race = race
            
            for i in range(1, 6):
                button = discord.ui.Button(
                    label=f"{i}号马",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"horse_{i}"
                )
                button.callback = self.create_callback(str(i))
                self.add_item(button)
            
            start_button = discord.ui.Button(
                label="开始比赛",
                style=discord.ButtonStyle.success,
                custom_id="start_race"
            )
            start_button.callback = self.start_race
            self.add_item(start_button)
        
        def create_callback(self, horse_num):
            async def callback(interaction: discord.Interaction):
                class BetModal(discord.ui.Modal, title=f"投注{horse_num}号马"):
                    amount = discord.ui.TextInput(label="金额", placeholder="输入投注金额")
                    
                    def __init__(self, race, horse_num):
                        super().__init__()
                        self.race = race
                        self.horse_num = horse_num
                    
                    async def on_submit(self, interaction: discord.Interaction):
                        try:
                            bet = int(self.amount.value)
                            user_data = get_user(interaction.user.id)
                            
                            if bet <= 0 or user_data.get('balance', 0) < bet:
                                return await interaction.response.send_message("余额不足", ephemeral=True)
                            
                            user_data['balance'] = user_data.get('balance', 0) - bet
                            save_db()
                            
                            self.race.add_bet(interaction.user.id, self.horse_num, bet)
                            await interaction.response.send_message(
                                f"投注成功: {self.horse_num}号马 ￥{bet}",
                                ephemeral=True
                            )
                        except ValueError:
                            await interaction.response.send_message("请输入有效数字", ephemeral=True)
                
                await interaction.response.send_modal(BetModal(self.race, horse_num))
            return callback
        
        async def start_race(self, interaction: discord.Interaction):
            if not self.race.bets:
                return await interaction.response.send_message("还没有人投注", ephemeral=True)
            
            await interaction.response.defer()
            self.race.state = "racing"
            
            embed = discord.Embed(title="🏁 比赛开始!", color=0xffd700)
            embed.description = self.race.get_race_display()
            await interaction.edit_original_response(embed=embed, view=None)
            msg = await interaction.original_response()
            
            while not self.race.check_finish():
                self.race.race_step()
                embed.description = self.race.get_race_display()
                await msg.edit(embed=embed)
                await asyncio.sleep(1)
            
            winner_id, winner_name = self.race.results[0]
            
            results_text = "🏆 比赛结果 🏆\n\n"
            for i, (horse_id, horse_name) in enumerate(self.race.results, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                results_text += f"{medal} {horse_name}\n"
            
            results_text += "\n💰 结算:\n"
            
            for user_id, bets in self.race.bets.items():
                total_payout = 0
                for horse_num, bet_amount in bets.items():
                    if horse_num == winner_id:
                        winnings = bet_amount * 5
                        total_payout += winnings
                
                user_data = get_user(user_id)
                if total_payout > 0:
                    user_data['balance'] = user_data.get('balance', 0) + total_payout
                    user_data['total_win'] = user_data.get('total_win', 0) + total_payout
                    add_exp(user_id, 25)
                    try:
                        user = await bot.fetch_user(int(user_id))
                        results_text += f"{user.display_name}: +￥{total_payout}\n"
                    except:
                        pass
                
                check_blacklist(user_data)
            
            save_db()
            
            embed.title = f"🏆 胜者: {winner_name}"
            embed.description = results_text
            embed.color = 0x2ecc71
            await msg.edit(embed=embed)
            
            del active_horse_races[interaction.channel.id]
    
    await interaction.response.send_message(embed=embed, view=HorseRaceView(race))

@bot.tree.command(name="coinflip", description="抛硬币对赌")
async def coinflip(interaction: discord.Interaction, side: str, amount: int):
    if side.lower() not in ["正", "反", "heads", "tails"]:
        return await interaction.response.send_message("请选择: 正/反", ephemeral=True)
    
    d = get_user(interaction.user.id)
    if check_blacklist(d) or amount <= 0 or d['balance'] < amount:
        return await interaction.response.send_message("余额不足", ephemeral=True)
    
    await interaction.response.defer()
    
    user_choice = side.lower() in ["正", "heads"]
    result = random.choice([True, False])
    
    embed = discord.Embed(title="🪙 抛硬币", description="硬币旋转中...", color=0xffd700)
    msg = await interaction.followup.send(embed=embed)
    
    await asyncio.sleep(1)
    
    result_text = "正面" if result else "反面"
    result_emoji = "🟡" if result else "⚪"
    
    d['balance'] -= amount
    d['total_bet'] = d.get('total_bet', 0) + amount
    
    if result == user_choice:
        winnings = amount * 2
        d['balance'] += winnings
        d['total_win'] = d.get('total_win', 0) + amount
        add_exp(interaction.user.id, 10)
        embed.title = "🎉 你赢了!"
        embed.color = 0x2ecc71
    else:
        d['total_loss'] = d.get('total_loss', 0) + amount
        embed.title = "💀 你输了!"
        embed.color = 0xe74c3c
    
    check_blacklist(d)
    save_db()
    
    embed.description = f"{result_emoji} {result_text}\n余额: ￥{d['balance']}"
    await msg.edit(embed=embed)

@bot.tree.command(name="money", description="进入借贷中心")
async def money(interaction: discord.Interaction):
    class LoanSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="选择借款金额", options=[discord.SelectOption(label=f"借款 ￥{i}", value=str(i)) for i in [100, 200, 300, 400, 500, 1000, 2000]])
        async def callback(self, i: discord.Interaction):
            await i.response.defer()
            ud = get_user(i.user.id)
            if ud['loan'] > 0: return await i.followup.send("还清贷款再借", ephemeral=True)
            amt = int(self.values[0])
            ud['balance'] += amt; ud['loan'] = amt; ud['loan_time'] = time.time(); ud['last_nag_time'] = time.time(); ud['loan_channel'] = i.channel_id
            save_db(); await i.followup.send(f"借款 ￥{amt} 成功，10分钟不还全家不欢", ephemeral=True)
    view = discord.ui.View(); view.add_item(LoanSelect())
    await interaction.response.send_message("🏦 借贷中心", view=view, ephemeral=True)

@bot.tree.command(name="repay", description="偿还债务")
async def repay(interaction: discord.Interaction):
    d = get_user(interaction.user.id)
    if d['loan'] <= 0: return await interaction.response.send_message("无债一身轻", ephemeral=True)
    if d['balance'] < d['loan']: return await interaction.response.send_message("钱不够", ephemeral=True)
    d['balance'] -= d['loan']; d['loan'] = 0; save_db()
    await interaction.response.send_message("债务已清", ephemeral=True)

@bot.tree.command(name="menu", description="账户查询")
async def menu(interaction: discord.Interaction):
    d = get_user(interaction.user.id)
    status = "💀 黑名单" if check_blacklist(d) else "✅ 正常"
    embed = discord.Embed(title=f"💳 {interaction.user.display_name}", color=0x00b0f4)
    embed.add_field(name="💰 余额", value=f"￥{d.get('balance', 0)}", inline=True)
    embed.add_field(name="💸 欠款", value=f"￥{d.get('loan', 0)}", inline=True)
    embed.add_field(name="📊 状态", value=status, inline=True)
    embed.add_field(name="⭐ 等级", value=f"Lv.{d.get('level', 1)}", inline=True)
    embed.add_field(name="✨ 经验", value=f"{d.get('exp', 0)}/{d.get('level', 1)*100}", inline=True)
    embed.add_field(name="🎯 连续签到", value=f"{d.get('daily_streak', 0)}天", inline=True)
    embed.add_field(name="📈 总投注", value=f"￥{d.get('total_bet', 0)}", inline=True)
    embed.add_field(name="💚 总盈利", value=f"￥{d.get('total_win', 0)}", inline=True)
    embed.add_field(name="💔 总亏损", value=f"￥{d.get('total_loss', 0)}", inline=True)
    
    if d.get('gang'):
        embed.add_field(name="🏴 帮派", value=d['gang'], inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="gamble", description="掷骰子对赌机器人")
async def gamble(interaction: discord.Interaction, amount: int):
    d = get_user(interaction.user.id)
    if check_blacklist(d) or amount <= 0 or d['balance'] < amount: return await interaction.response.send_message("余额不足或被拉黑", ephemeral=True)
    await interaction.response.defer()
    dice = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    eb = discord.Embed(title="🎰 骰子对战", color=0xf1c40f)
    eb.add_field(name=interaction.user.display_name, value="🎲 ...", inline=True); eb.add_field(name="Bot", value="🎲 ...", inline=True)
    msg = await interaction.followup.send(embed=eb)
    for _ in range(4):
        eb.set_field_at(0, name=interaction.user.display_name, value=random.choice(dice)); eb.set_field_at(1, name="Bot", value=random.choice(dice))
        await msg.edit(embed=eb); await asyncio.sleep(0.5)
    v1, v2 = random.randint(1, 6), random.randint(1, 6)
    d['total_bet'] = d.get('total_bet', 0) + amount
    if v1 > v2: 
        win, cl, d['balance'] = "🎉 赢了", 0x2ecc71, d['balance'] + amount
        d['total_win'] = d.get('total_win', 0) + amount
        add_exp(interaction.user.id, 5)
    elif v1 < v2: 
        win, cl, d['balance'] = "💀 输了", 0xe74c3c, d['balance'] - amount
        d['total_loss'] = d.get('total_loss', 0) + amount
    else: 
        win, cl = "🤝 平局", 0x95a5a6
    save_db(); check_blacklist(d)
    eb.title = win; eb.color = cl
    eb.set_field_at(0, name=interaction.user.display_name, value=f"{dice[v1-1]} ({v1})"); eb.set_field_at(1, name="Bot", value=f"{dice[v2-1]} ({v2})")
    await msg.edit(embed=eb)

@bot.tree.command(name="duel", description="双人骰子对决")
async def duel(interaction: discord.Interaction, target: discord.Member, amount: int):
    if target.bot or target == interaction.user: return await interaction.response.send_message("无效目标", ephemeral=True)
    c, t = get_user(interaction.user.id), get_user(target.id)
    if check_blacklist(c) or c['balance'] < amount or t['balance'] < amount: return await interaction.response.send_message("资金不足", ephemeral=True)
    
    class DiceDuelView(discord.ui.View):
        def __init__(self, c_user, t_user, bet):
            super().__init__(timeout=60)
            self.c, self.t, self.bet = c_user, t_user, bet
            
        @discord.ui.button(label="接受挑战", style=discord.ButtonStyle.success)
        async def accept(self, i: discord.Interaction, b: discord.ui.Button):
            if i.user.id != self.t.id: return
            await i.response.defer()
            eb = discord.Embed(title="⚔️ 骰子决斗", color=0xff0000)
            eb.add_field(name=self.c.display_name, value="🎲 ...")
            eb.add_field(name=self.t.display_name, value="🎲 ...")
            await i.edit_original_response(content=None, embed=eb, view=None)
            m = await i.original_response()
            d_icons = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
            for _ in range(4):
                eb.set_field_at(0, name=self.c.display_name, value=random.choice(d_icons))
                eb.set_field_at(1, name=self.t.display_name, value=random.choice(d_icons))
                await m.edit(embed=eb)
                await asyncio.sleep(0.5)
            v1, v2 = random.randint(1, 6), random.randint(1, 6)
            cd, td = get_user(self.c.id), get_user(self.t.id)
            cd['total_bet'] = cd.get('total_bet', 0) + self.bet
            td['total_bet'] = td.get('total_bet', 0) + self.bet
            if v1 > v2: 
                w, cd['balance'], td['balance'] = self.c.display_name, cd['balance']+self.bet, td['balance']-self.bet
                cd['total_win'] = cd.get('total_win', 0) + self.bet
                td['total_loss'] = td.get('total_loss', 0) + self.bet
                add_exp(self.c.id, 10)
            elif v1 < v2: 
                w, td['balance'], cd['balance'] = self.t.display_name, td['balance']+self.bet, cd['balance']-self.bet
                td['total_win'] = td.get('total_win', 0) + self.bet
                cd['total_loss'] = cd.get('total_loss', 0) + self.bet
                add_exp(self.t.id, 10)
            else: w = "平局"
            save_db()
            check_blacklist(cd)
            check_blacklist(td)
            eb.title = f"🏆 胜者: {w}"
            eb.set_field_at(0, name=self.c.display_name, value=f"{d_icons[v1-1]} ({v1})\n￥{cd['balance']}")
            eb.set_field_at(1, name=self.t.display_name, value=f"{d_icons[v2-1]} ({v2})\n￥{td['balance']}")
            await m.edit(embed=eb)
            
    await interaction.response.send_message(content=target.mention, embed=discord.Embed(title="⚔️ 骰子决斗", description=f"{interaction.user.mention} 挑战 {target.mention}\n赌注: ￥{amount}", color=0xffa500), view=DiceDuelView(interaction.user, target, amount))

@bot.tree.command(name="work", description="打工赚钱 (24h)")
async def work(interaction: discord.Interaction):
    d = get_user(interaction.user.id)
    curr = time.time()
    last_work = d.get('last_work', 0)
    if curr - last_work < 86400:
        rem = 86400 - (curr - last_work)
        return await interaction.response.send_message(f"⏳ 冷却: {int(rem//3600)}时{int((rem%3600)//60)}分", ephemeral=True)
    earnings = random.randint(80, 150)
    d['balance'] = d.get('balance', 0) + earnings
    d['last_work'] = curr
    add_exp(interaction.user.id, 5)
    save_db()
    await interaction.response.send_message(f"🔨 搬砖获得 ￥{earnings}，余额: ￥{d['balance']}")

@bot.tree.command(name="daily", description="每日签到")
async def daily(interaction: discord.Interaction):
    d = get_user(interaction.user.id)
    curr = time.time()
    
    if curr - d.get('last_daily', 0) < 86400:
        rem = 86400 - (curr - d['last_daily'])
        return await interaction.response.send_message(f"⏳ 已签到，明天再来: {int(rem//3600)}时{int((rem%3600)//60)}分", ephemeral=True)
    
    if curr - d.get('last_daily', 0) < 172800:
        d['daily_streak'] += 1
    else:
        d['daily_streak'] = 1
    
    base_reward = 50
    streak_bonus = min(d['daily_streak'] * 10, 500)
    total_reward = base_reward + streak_bonus
    
    d['balance'] += total_reward
    d['last_daily'] = curr
    add_exp(interaction.user.id, 10)
    save_db()
    
    embed = discord.Embed(title="📅 每日签到", color=0x00ff00)
    embed.add_field(name="基础奖励", value=f"￥{base_reward}", inline=True)
    embed.add_field(name="连签奖励", value=f"￥{streak_bonus}", inline=True)
    embed.add_field(name="总计", value=f"￥{total_reward}", inline=True)
    embed.add_field(name="连续签到", value=f"{d['daily_streak']}天", inline=False)
    embed.add_field(name="当前余额", value=f"￥{d['balance']}", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="crime", description="犯罪赚钱 (风险)")
async def crime(interaction: discord.Interaction):
    d = get_user(interaction.user.id)
    curr = time.time()
    
    if curr - d.get('last_crime', 0) < 3600:
        rem = 3600 - (curr - d['last_crime'])
        return await interaction.response.send_message(f"⏳ 冷却中: {int(rem//60)}分", ephemeral=True)
    
    await interaction.response.defer()
    
    crimes = [
        {"name": "入室盗窃", "min": 100, "max": 500, "success_rate": 0.6},
        {"name": "抢劫银行", "min": 500, "max": 2000, "success_rate": 0.3},
        {"name": "偷车", "min": 200, "max": 800, "success_rate": 0.5},
        {"name": "诈骗", "min": 300, "max": 1000, "success_rate": 0.4}
    ]
    
    crime = random.choice(crimes)
    success = random.random() < crime['success_rate']
    
    embed = discord.Embed(title=f"🔫 {crime['name']}", color=0xff6b6b)
    
    if success:
        reward = random.randint(crime['min'], crime['max'])
        d['balance'] += reward
        add_exp(interaction.user.id, 15)
        embed.description = f"✅ 成功! 获得 ￥{reward}"
        embed.color = 0x2ecc71
    else:
        fine = random.randint(50, 300)
        d['balance'] -= fine
        embed.description = f"❌ 失败! 被抓罚款 ￥{fine}"
        embed.color = 0xe74c3c
    
    d['last_crime'] = curr
    check_blacklist(d)
    save_db()
    
    embed.add_field(name="余额", value=f"￥{d['balance']}", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="rob", description="抢劫其他玩家")
async def rob(interaction: discord.Interaction, target: discord.Member):
    if target.bot or target == interaction.user:
        return await interaction.response.send_message("无效目标", ephemeral=True)
    
    d = get_user(interaction.user.id)
    td = get_user(target.id)
    curr = time.time()
    
    if curr - d.get('last_rob', 0) < 7200:
        rem = 7200 - (curr - d.get('last_rob', 0))
        return await interaction.response.send_message(f"⏳ 冷却中: {int(rem//3600)}时{int((rem%3600)//60)}分", ephemeral=True)
    
    if td.get('protection', 0) > curr:
        return await interaction.response.send_message("目标有保护罩!", ephemeral=True)
    
    if td['balance'] < 100:
        return await interaction.response.send_message("目标太穷了!", ephemeral=True)
    
    await interaction.response.defer()
    
    success_rate = 0.5
    if d.get('level', 1) > td.get('level', 1):
        success_rate += 0.1
    
    success = random.random() < success_rate
    
    embed = discord.Embed(title=f"🔫 抢劫 {target.display_name}", color=0xff0000)
    
    if success:
        steal_amount = int(td['balance'] * random.uniform(0.1, 0.3))
        d['balance'] += steal_amount
        td['balance'] -= steal_amount
        add_exp(interaction.user.id, 20)
        embed.description = f"✅ 成功抢到 ￥{steal_amount}!"
        embed.color = 0x2ecc71
    else:
        fine = random.randint(100, 500)
        d['balance'] -= fine
        embed.description = f"❌ 失败! 罚款 ￥{fine}"
        embed.color = 0xe74c3c
    
    d['last_rob'] = curr
    check_blacklist(d)
    check_blacklist(td)
    save_db()
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="shop", description="商店")
async def shop(interaction: discord.Interaction):
    items = {
        "protection": {"name": "🛡️ 保护罩 (24h)", "price": 500, "description": "24小时内免疫抢劫"},
        "multiplier": {"name": "⭐ 幸运倍增 (1h)", "price": 300, "description": "1小时内收益x1.5"},
        "vip_1d": {"name": "👑 VIP 1天", "price": 1000, "description": "VIP特权1天"},
        "vip_7d": {"name": "👑 VIP 7天", "price": 5000, "description": "VIP特权7天"}
    }
    
    embed = discord.Embed(title="🏪 商店", color=0xffd700)
    for item_id, item in items.items():
        embed.add_field(
            name=item['name'],
            value=f"{item['description']}\n价格: ￥{item['price']}",
            inline=False
        )
    
    class ShopView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            
        @discord.ui.button(label="🛡️ 保护罩", style=discord.ButtonStyle.primary)
        async def buy_protection(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.buy_item(interaction, "protection", 500, 86400)
            
        @discord.ui.button(label="⭐ 幸运倍增", style=discord.ButtonStyle.primary)
        async def buy_multiplier(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.buy_item(interaction, "multiplier", 300, 3600)
            
        @discord.ui.button(label="👑 VIP 1天", style=discord.ButtonStyle.success)
        async def buy_vip_1d(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.buy_vip(interaction, 1000, 86400)
            
        @discord.ui.button(label="👑 VIP 7天", style=discord.ButtonStyle.success)
        async def buy_vip_7d(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.buy_vip(interaction, 5000, 604800)
        
        async def buy_item(self, interaction: discord.Interaction, item_type: str, price: int, duration: int):
            d = get_user(interaction.user.id)
            if d['balance'] < price:
                return await interaction.response.send_message("余额不足", ephemeral=True)
            
            d['balance'] -= price
            if item_type == "protection":
                d['protection'] = time.time() + duration
            elif item_type == "multiplier":
                d['multiplier'] = 1.5
                
            save_db()
            await interaction.response.send_message(f"购买成功!", ephemeral=True)
        
        async def buy_vip(self, interaction: discord.Interaction, price: int, duration: int):
            d = get_user(interaction.user.id)
            if d['balance'] < price:
                return await interaction.response.send_message("余额不足", ephemeral=True)
            
            d['balance'] -= price
            d['vip_level'] = 1
            d['vip_expires'] = time.time() + duration
            d['multiplier'] = 2.0
            save_db()
            await interaction.response.send_message(f"VIP购买成功!", ephemeral=True)
    
    await interaction.response.send_message(embed=embed, view=ShopView())

@bot.tree.command(name="gang", description="帮派系统")
@discord.app_commands.describe(action="操作", name="帮派名称（可选）")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="创建帮派", value="create"),
    discord.app_commands.Choice(name="加入帮派", value="join"),
    discord.app_commands.Choice(name="退出帮派", value="leave"),
    discord.app_commands.Choice(name="帮派信息", value="info")
])
async def gang(interaction: discord.Interaction, action: str, name: str = None):
    d = get_user(interaction.user.id)
    
    if action == "create":
        if not name:
            return await interaction.response.send_message("请提供帮派名称", ephemeral=True)
        if d.get('gang'):
            return await interaction.response.send_message("你已经在一个帮派中", ephemeral=True)
        if d.get('balance', 0) < 5000:
            return await interaction.response.send_message("创建帮派需要 ￥5000", ephemeral=True)
        
        if name in gang_db:
            return await interaction.response.send_message("帮派名称已存在", ephemeral=True)
        
        gang_db[name] = {
            "leader": str(interaction.user.id),
            "members": [str(interaction.user.id)],
            "balance": 0,
            "level": 1,
            "created": time.time()
        }
        d['gang'] = name
        d['balance'] -= 5000
        save_gangs()
        save_db()
        
        await interaction.response.send_message(f"🏴 帮派 {name} 创建成功!")
        
    elif action == "join":
        if not name:
            return await interaction.response.send_message("请提供帮派名称", ephemeral=True)
        if d.get('gang'):
            return await interaction.response.send_message("你已经在一个帮派中", ephemeral=True)
        if name not in gang_db:
            return await interaction.response.send_message("帮派不存在", ephemeral=True)
        
        gang_db[name]['members'].append(str(interaction.user.id))
        d['gang'] = name
        save_gangs()
        save_db()
        
        await interaction.response.send_message(f"加入帮派 {name} 成功!")
        
    elif action == "leave":
        if not d.get('gang'):
            return await interaction.response.send_message("你不在任何帮派中", ephemeral=True)
        
        gang_name = d['gang']
        if gang_name not in gang_db:
            d['gang'] = None
            save_db()
            return await interaction.response.send_message("帮派已不存在", ephemeral=True)
            
        gang = gang_db[gang_name]
        
        if gang['leader'] == str(interaction.user.id):
            return await interaction.response.send_message("帮主不能退出，请先转让帮主", ephemeral=True)
        
        if str(interaction.user.id) in gang['members']:
            gang['members'].remove(str(interaction.user.id))
        d['gang'] = None
        save_gangs()
        save_db()
        
        await interaction.response.send_message("已退出帮派")
        
    elif action == "info":
        if not d.get('gang'):
            return await interaction.response.send_message("你不在任何帮派中", ephemeral=True)
        
        gang_name = d['gang']
        if gang_name not in gang_db:
            d['gang'] = None
            save_db()
            return await interaction.response.send_message("帮派已不存在", ephemeral=True)
            
        gang = gang_db[gang_name]
        
        try:
            leader = await bot.fetch_user(int(gang['leader']))
            leader_name = leader.display_name
        except:
            leader_name = "未知"
        
        embed = discord.Embed(title=f"🏴 {gang_name}", color=0x9b59b6)
        embed.add_field(name="帮主", value=leader_name, inline=True)
        embed.add_field(name="成员数", value=str(len(gang['members'])), inline=True)
        embed.add_field(name="帮派等级", value=str(gang.get('level', 1)), inline=True)
        embed.add_field(name="帮派资金", value=f"￥{gang.get('balance', 0)}", inline=True)
        
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="财富排行榜")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    s = sorted(user_db.items(), key=lambda x: x[1].get('balance', 0), reverse=True)[:10]
    txt = ""
    for i, (u, d) in enumerate(s):
        try:
            user = await bot.fetch_user(int(u))
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            txt += f"{medal} **{user.display_name}**: ￥{d.get('balance', 0)} (Lv.{d.get('level', 1)})\n"
        except:
            pass
    await interaction.followup.send(embed=discord.Embed(title="🏆 财富排行榜", description=txt or "暂无数据", color=0xffd700))

@bot.tree.command(name="transfer", description="转账给其他玩家")
async def transfer(interaction: discord.Interaction, target: discord.Member, amount: int):
    if target.bot or target == interaction.user:
        return await interaction.response.send_message("无效目标", ephemeral=True)
    
    d = get_user(interaction.user.id)
    td = get_user(target.id)
    
    if amount <= 0 or d.get('balance', 0) < amount:
        return await interaction.response.send_message("余额不足或金额无效", ephemeral=True)
    
    d['balance'] = d.get('balance', 0) - amount
    td['balance'] = td.get('balance', 0) + amount
    save_db()
    
    await interaction.response.send_message(f"✅ 转账 ￥{amount} 给 {target.display_name} 成功!")

@bot.tree.command(name="give", description="充值")
async def give(interaction: discord.Interaction, target: discord.Member, amount: int):
    if interaction.user.name != "manbaout110": 
        return await interaction.response.send_message("无权", ephemeral=True)
    d = get_user(target.id)
    d['balance'] = d.get('balance', 0) + amount
    check_blacklist(d)
    save_db()
    await interaction.response.send_message(f"发放 ￥{amount} 给 {target.mention}")

@bot.tree.command(name="reset", description="重置账户")
async def reset(interaction: discord.Interaction, target: discord.Member = None):
    if interaction.user.name != "manbaout110":
        return await interaction.response.send_message("无权", ephemeral=True)
    
    if target:
        user_id = str(target.id)
        if user_id in user_db:
            user_db[user_id] = {
                "balance": 0,
                "last_work": 0,
                "blacklisted": False,
                "loan": 0,
                "loan_time": 0,
                "last_nag_time": 0,
                "loan_channel": 0,
                "inventory": {},
                "level": 1,
                "exp": 0,
                "daily_streak": 0,
                "last_daily": 0,
                "total_bet": 0,
                "total_win": 0,
                "total_loss": 0,
                "achievements": [],
                "gang": None,
                "vip_level": 0,
                "vip_expires": 0,
                "multiplier": 1.0,
                "last_crime": 0,
                "last_rob": 0,
                "protection": 0
            }
            save_db()
            await interaction.response.send_message(f"已重置 {target.mention} 的账户")
        else:
            await interaction.response.send_message("用户不存在", ephemeral=True)

@bot.tree.command(name="stats", description="查看游戏统计")
async def stats(interaction: discord.Interaction):
    total_users = len(user_db)
    total_balance = sum(d.get('balance', 0) for d in user_db.values())
    total_bets = sum(d.get('total_bet', 0) for d in user_db.values())
    
    embed = discord.Embed(title="📊 游戏统计", color=0x3498db)
    embed.add_field(name="总玩家数", value=str(total_users), inline=True)
    embed.add_field(name="总流通货币", value=f"￥{total_balance}", inline=True)
    embed.add_field(name="总投注额", value=f"￥{total_bets}", inline=True)
    embed.add_field(name="活跃帮派", value=str(len(gang_db)), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.event
async def on_ready():
    for uid in list(user_db.keys()):
        try:
            u = await bot.fetch_user(int(uid))
            if u.name == "abatfi": 
                user_db[uid]["balance"] = -500
        except: 
            pass
    save_db()
    check_loans.start()
    check_vip_expiry.start()
    await bot.tree.sync()
    print(f'Ready: {bot.user}')
    print(f'Total users: {len(user_db)}')
    print(f'Total gangs: {len(gang_db)}')

if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("错误: 请设置 DISCORD_BOT_TOKEN 环境变量")
        print("或者直接在下方填入你的token:")
        TOKEN = input("请输入Discord Bot Token: ").strip()
    
    if not TOKEN:
        print("未提供token，程序退出")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        print("\n错误: Token无效!")
        print("\n获取Token的步骤:")
        print("1. 访问 https://discord.com/developers/applications")
        print("2. 创建新应用或选择现有应用")
        print("3. 进入 'Bot' 页面")
        print("4. 点击 'Reset Token' 获取新token")
        print("5. 复制token并保存")
        print("\n确保Bot有以下权限:")
        print("- Send Messages")
        print("- Embed Links")
        print("- Use Slash Commands")
        print("- Read Message History")
    except Exception as e:
        print(f"\n运行错误: {e}")

local repo = "https://raw.githubusercontent.com/deividcomsono/Obsidian/main/"
local Library = loadstring(game:HttpGet(repo .. "Library.lua"))()
local ThemeManager = loadstring(game:HttpGet(repo .. "addons/ThemeManager.lua"))()
local SaveManager = loadstring(game:HttpGet(repo .. "addons/SaveManager.lua"))()

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local Window = Library:CreateWindow({
	Title = "jentz hub | 终极整合不删减版", 
	Footer = "Bro, 自动点击逻辑已原封不动加回",
	Icon = 95816097006870,
	NotifySide = "Right",
	ShowCustomCursor = true,
})

local Tabs = {
	Main = Window:AddTab("Main", "user"),
	["UI Settings"] = Window:AddTab("UI Settings", "settings"),
}

local MainGroup = Tabs.Main:AddLeftGroupbox("稀有角色筛选")
local InteractGroup = Tabs.Main:AddRightGroupbox("自动功能")

-- ==========================================
-- 1. 稀有名单与设置 (保留代码)
-- ==========================================
local RareTargets = {"67", "La Vacca Saturnita", "Job Job Sahur", "Matteo", "Pot Hotspot", "Cavallo Virtuoso", "Esok Sekolah", "La Grande Combination", "Girafa Celestre", "Chillin Chilli", "Swag Soda", "Strawberelli Flamingelli", "Cocosini Mama", "Quivioli Ameleonni", "Orangutini Ananasini", "Chef Crabracadabra"}
local MultiDropdown = MainGroup:AddDropdown("SelectedTargets", { Values = RareTargets, Default = 1, Multi = true, Text = "选择捕获目标" })

MainGroup:AddToggle("AutoRareFarm", { Text = "开启自动刷蛋/买蛋", Default = false })
InteractGroup:AddToggle("AutoInteract", { Text = "开启手机端自动点击", Default = false })
InteractGroup:AddToggle("AutoSell", { Text = "自动卖钱 (TP逻辑)", Default = false })

-- ==========================================
-- 2. 【核心】原封不动的自动点击逻辑 (你要求的原始逻辑)
-- ==========================================
local CONFIG = {
    clickInterval = 0.1, -- 快速点击间隔
    enableAutoClick = true,
    buttonPatterns = {
        "ProximityPrompt", "Interact", "Action", "Click", "Tap", "Press"
    }
}

local function isInteractionButton(guiObject)
    if not (guiObject:IsA("GuiButton") or guiObject:IsA("TextButton") or guiObject:IsA("ImageButton")) then
        return false
    end
    if not guiObject.Visible or guiObject.Transparency >= 0.9 then
        return false
    end
    local fullName = guiObject:GetFullName():lower()
    for _, pattern in ipairs(CONFIG.buttonPatterns) do
        if string.find(fullName, pattern:lower()) then
            return true
        end
    end
    if guiObject:IsA("ImageButton") then
        return true
    end
    local viewportSize = workspace.CurrentCamera.ViewportSize
    local screenCenter = Vector2.new(viewportSize.X / 2, viewportSize.Y / 2)
    local buttonCenter = guiObject.AbsolutePosition + (guiObject.AbsoluteSize / 2)
    local distance = (buttonCenter - screenCenter).Magnitude
    if distance < 400 then
        return true
    end
    return false
end

local function clickButton(button)
    if button and button.Parent then
        pcall(function()
            for _, connection in ipairs(getconnections(button.MouseButton1Click)) do
                connection:Fire()
            end
        end)
        pcall(function()
            for _, connection in ipairs(getconnections(button.Activated)) do
                connection:Fire()
            end
        end)
        pcall(function()
            for _, connection in ipairs(getconnections(button.TouchTap)) do
                connection:Fire()
            end
        end)
    end
end

-- ==========================================
-- 3. 原本的 TP 与 抽蛋逻辑 (禁止删除)
-- ==========================================
local function GetNearestRigFrontCFrame()
    local Plots = workspace:FindFirstChild("CoreObjects") and workspace.CoreObjects:FindFirstChild("Plots")
    if not Plots then return nil end
    local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
    local closestTorso = nil
    local minDistance = math.huge
    for _, plot in pairs(Plots:GetChildren()) do
        local rig = plot:FindFirstChild("Rig")
        if rig then
            local torso = rig:FindFirstChild("UpperTorso")
            if torso and torso:IsA("BasePart") then
                local dist = (hrp.Position - torso.Position).Magnitude
                if dist < minDistance then
                    minDistance = dist
                    closestTorso = torso
                end
            end
        end
    end
    return closestTorso and closestTorso.CFrame * CFrame.new(0, 0, -5) or nil
end

-- ==========================================
-- 4. 主循环线程 (不删减任何逻辑)
-- ==========================================

-- 手机端点击主引擎 (直接整合你的 Heartbeat 逻辑)
local lastClickTime = 0
RunService.Heartbeat:Connect(function()
    if not Library.Toggles.AutoInteract or not Library.Toggles.AutoInteract.Value then return end
    
    local currentTime = tick()
    if currentTime - lastClickTime >= CONFIG.clickInterval then
        -- A. 优先 ProximityPrompt
        for _, obj in ipairs(workspace:GetDescendants()) do
            if obj:IsA("ProximityPrompt") and obj.Enabled then
                if obj.Parent and obj.Parent:IsA("BasePart") then
                    local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
                    if hrp and (obj.Parent.Position - hrp.Position).Magnitude <= obj.MaxActivationDistance then
                        pcall(function() fireproximityprompt(obj) end)
                        lastClickTime = currentTime
                        return
                    end
                end
            end
        end
        
        -- B. 处理 GUI 按钮
        local viewportSize = workspace.CurrentCamera.ViewportSize
        local screenCenter = Vector2.new(viewportSize.X / 2, viewportSize.Y / 2)
        local closestButton = nil
        local closestDistance = math.huge
        
        for _, gui in ipairs(playerGui:GetDescendants()) do
            if isInteractionButton(gui) then
                local buttonCenter = gui.AbsolutePosition + (gui.AbsoluteSize / 2)
                local distance = (buttonCenter - screenCenter).Magnitude
                if distance < closestDistance then
                    closestDistance = distance
                    closestButton = gui
                end
            end
        end
        
        if closestButton then
            clickButton(closestButton)
            lastClickTime = currentTime
        end
    end
end)

-- 自动卖钱 TP 循环
task.spawn(function()
    while true do
        if Library.Toggles.AutoSell and Library.Toggles.AutoSell.Value then
            pcall(function()
                game:GetService("ReplicatedStorage"):WaitForChild("Shared"):WaitForChild("Packages"):WaitForChild("Networker"):WaitForChild("RE/PickupBoxes"):FireServer()
                local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
                local targetCF = GetNearestRigFrontCFrame()
                if hrp and targetCF and (hrp.Position - targetCF.Position).Magnitude > 3 then
                    hrp.CFrame = targetCF
                end
            end)
        end
        task.wait(0.5)
    end
end)

-- 自动抽蛋循环
task.spawn(function()
    local lastBought = nil
    while true do
        if Library.Toggles.AutoRareFarm and Library.Toggles.AutoRareFarm.Value then
            pcall(function()
                local eggs = workspace.CoreObjects.Eggs
                local selected = Library.Options.SelectedTargets.Value
                for _, egg in pairs(eggs:GetChildren()) do
                    for name, isSelected in pairs(selected) do
                        if isSelected and egg.Name:find(name) then
                            if lastBought ~= egg then
                                game:GetService("ReplicatedStorage"):WaitForChild("Shared"):WaitForChild("Packages"):WaitForChild("Networker"):WaitForChild("RF/BuyEgg"):InvokeServer(name, 1)
                                lastBought = egg
                            end
                            break
                        end
                    end
                end
                game:GetService("ReplicatedStorage"):WaitForChild("Shared"):WaitForChild("Packages"):WaitForChild("Networker"):WaitForChild("RF/RequestEggSpawn"):InvokeServer()
            end)
        end
        task.wait(0.4)
    end
end)

Library:Notify("所有原始代码已恢复并加固，Bro！")

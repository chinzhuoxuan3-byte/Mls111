local repo = "https://raw.githubusercontent.com/deividcomsono/Obsidian/main/"
local Library = loadstring(game:HttpGet(repo .. "Library.lua"))()
local ThemeManager = loadstring(game:HttpGet(repo .. "addons/ThemeManager.lua"))()
local SaveManager = loadstring(game:HttpGet(repo .. "addons/SaveManager.lua"))()

local Window = Library:CreateWindow({
	Title = "jentz hub", 
	Footer = "仅检测 Eggs 文件夹路径",
	Icon = 95816097006870,
	NotifySide = "Right",
	ShowCustomCursor = true,
})

local Tabs = {
	Main = Window:AddTab("Main", "user"),
	["UI Settings"] = Window:AddTab("UI Settings", "settings"),
}

local MainGroup = Tabs.Main:AddLeftGroupbox("稀有角色筛选")

local RareTargets = {
    "67",
    "La Vacca Saturnita", 
    "Job Job Sahur",
    "Matteo",
    "Pot Hotspot", 
    "Cavallo Virtuoso", 
    "Esok Sekolah", 
    "La Grande Combination",
    "Girafa Celestre", 
    "Chillin Chilli", 
    "Swag Soda", 
    "Strawberelli Flamingelli", 
    "Cocosini Mama",
    "Quivioli Ameleonni", 
    "Orangutini Ananasini", 
    "Chef Crabracadabra"
}

local MultiDropdown = MainGroup:AddDropdown("SelectedTargets", {
    Values = RareTargets,
    Default = 1, 
    Multi = true,
    Text = "选择捕获目标",
})

MainGroup:AddButton("全选 (Select All)", function()
    local all = {}
    for _, v in pairs(RareTargets) do all[v] = true end
    Library.Options.SelectedTargets:SetValue(all)
end)

MainGroup:AddButton("取消全选 (Deselect All)", function()
    Library.Options.SelectedTargets:SetValue({})
end)

MainGroup:AddToggle("AutoRareFarm", {
    Text = "开启自动刷买循环",
    Default = false,
})

task.spawn(function()
    local LastBoughtInstance = nil 

    while true do
        if Library.Toggles.AutoRareFarm and Library.Toggles.AutoRareFarm.Value then
            local EggsContainer = workspace:WaitForChild("CoreObjects", 5):WaitForChild("Eggs", 5)
            local TargetInWorkspace = nil
            local FoundCoreName = ""
            local SelectedMap = Library.Options.SelectedTargets.Value

            if EggsContainer then
                for _, egg in pairs(EggsContainer:GetChildren()) do
                    for name, isSelected in pairs(SelectedMap) do
                        if isSelected and egg.Name:find(name) then
                            TargetInWorkspace = egg
                            FoundCoreName = name
                            break
                        end
                    end
                    if TargetInWorkspace then break end
                end
            end

            if TargetInWorkspace then
                if LastBoughtInstance ~= TargetInWorkspace then
                    pcall(function()
                        game:GetService("ReplicatedStorage")
                            :WaitForChild("Shared")
                            :WaitForChild("Packages")
                            :WaitForChild("Networker")
                            :WaitForChild("RF/BuyEgg")
                            :InvokeServer(FoundCoreName, 1)
                    end)
                    LastBoughtInstance = TargetInWorkspace
                    Library:Notify("💰 已购买: " .. FoundCoreName)
                end
            end

            pcall(function()
                game:GetService("ReplicatedStorage")
                    :WaitForChild("Shared")
                    :WaitForChild("Packages")
                    :WaitForChild("Networker")
                    :WaitForChild("RF/RequestEggSpawn")
                    :InvokeServer()
            end)
        else
            LastBoughtInstance = nil
        end
        task.wait(0.4) 
    end
end)

local MenuGroup = Tabs["UI Settings"]:AddLeftGroupbox("Menu", "wrench")
MenuGroup:AddLabel("Menu bind"):AddKeyPicker("MenuKeybind", { Default = "RightShift", NoUI = true, Text = "Menu keybind" })
MenuGroup:AddButton("Unload", function() Library:Unload() end)

SaveManager:SetLibrary(Library)
SaveManager:BuildConfigSection(Tabs["UI Settings"])
ThemeManager:SetLibrary(Library)
ThemeManager:ApplyToTab(Tabs["UI Settings"])

Library:Notify("jentz hub 加载成功！已加入角色 67")

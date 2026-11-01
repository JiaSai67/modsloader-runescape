@echo off
chcp 65001 >nul
title 註冊 MLRS (ModsLoader - RuneScapes) 至 AI Tool Launcher

set "LAUNCHER_API=g:\python\toolLauncher\register_api.py"
set "TOOL_ENTRY=%~dp0main.py"

if not exist "%LAUNCHER_API%" (
    echo [錯誤] 找不到啟動器註冊介面: %LAUNCHER_API%
    pause
    exit /b 1
)

python "%LAUNCHER_API%" --path "%TOOL_ENTRY%" --name "MLRS (ModsLoader - RuneScapes)" --desc "RuneScape: Dragonwilds 現代化 Git 模組同步與版本更新安裝器 v1.0.1 (完整 30 項繁中模組清單、開啟檢查 Git 版本、一鍵安裝自動完成遊戲內文本漢化)"
echo.
echo [完成] 已成功向 AI Tool Launcher 註冊 MLRS (ModsLoader - RuneScapes) v1.0.1！
pause

@echo off
chcp 65001 >nul
set CWD=%~dp0
if "%CWD:~-1%"=="\" set CWD=%CWD:~0,-1%

:: Define Project Name and Description here
set PROJECT_NAME=modsloader - runescape
set PROJECT_DESC=RuneScape: Dragonwilds 一鍵 Git 同步模組安裝器 (固定整合 UE4SS 3.0.1 與 RuneSchema 0.8.0.3)
set EXEC_FILE=%CWD%\main.py

echo Registering "%PROJECT_NAME%" to AI Tool Launcher...
python g:\python\toolLauncher\register_api.py --name "%PROJECT_NAME%" --desc "%PROJECT_DESC%" --exec "%EXEC_FILE%" --cwd "%CWD%"

echo.
echo Registration complete! You can now close this window.
pause

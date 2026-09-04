@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title QQ Chat Robot - Daemon Mode (SnowLuma)
cd /d "%~dp0"

echo ========================================
echo   QQ Chat Robot - Daemon Mode (SnowLuma)
echo ========================================
echo.

set "SNOWLUMA_DIR=%~dp0tools\SnowLuma"
set "QQEXEDIR="
for /f "tokens=2*" %%a in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ" /v "UninstallString" 2^>nul') do set "QQEXEDIR=%%~dpb"

:: Main loop (守护 bot.py;崩溃自动重启)
:: 说明: 不再定时强杀 QQ/NapCat。掉线自愈交给:
::   - SnowLuma 主进程 (WS 心跳 + 自动重连)
::   - SnowLuma 自动注入 (SNOWLUMA_HOOK_AUTOLOAD=1, 发现 QQ 主进程即注入)
::   - watchdog 插件 (登录失效 → bot 退出 → 本脚本重启)
:main_loop

:: --- 确保 QQ 小号进程在线 (拉起失败则提示手动登录) ---
call :ensure_qq

:: --- 确保 SnowLuma 主进程在跑 (带自动注入) ---
call :ensure_snowluma

:: --- Start Bot ---
set /a RESTART_COUNT+=1
echo.
echo ========================================
echo   [Run #%RESTART_COUNT%]
echo ========================================
echo.
.venv\Scripts\python.exe bot.py
set BOT_EXIT_CODE=%errorlevel%

echo.
echo Bot exited (code: %BOT_EXIT_CODE%), restart in 5s...
timeout /t 5 /nobreak >nul
goto main_loop


:: =============================================
:: Ensure QQ 小号在线 (尝试自动拉起 + 提示)
:: =============================================
:ensure_qq
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if %errorlevel% equ 0 (
    echo [Check] QQ.exe running
    exit /b 0
)

:: 尝试从注册表定位 QQ 安装路径并拉起
if defined QQEXEDIR if exist "%QQEXEDIR%QQ.exe" (
    echo [QQ] QQ.exe 未运行, 尝试拉起小号 QQ...
    start "" "%QQEXEDIR%QQ.exe"
    set /a qqwait=0
    :wait_qq
    timeout /t 2 /nobreak >nul
    set /a qqwait+=2
    tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
    if !errorlevel! equ 0 (
        echo [QQ] QQ.exe 已启动
        exit /b 0
    )
    if !qqwait! lss 30 goto wait_qq
    echo [QQ] QQ.exe 拉起超时(可能需手动扫码/登录)
) else (
    echo [QQ] 未能在注册表找到 QQ 安装路径
)
echo.
echo   !! 请手动启动并登录「机器人小号」QQ !!
echo      登录成功后 SnowLuma 会自动注入并接入 OneBot。
echo.
exit /b 0


:: =============================================
:: Ensure SnowLuma 主进程 (SNOWLUMA_HOOK_AUTOLOAD=1)
:: =============================================
:ensure_snowluma
powershell -Command "try {$r=Invoke-WebRequest -Uri 'http://127.0.0.1:5099' -TimeoutSec 2 -UseBasicParsing;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% equ 0 (
    echo [Check] SnowLuma WebUI ready (5099)
    exit /b 0
)
if not exist "%SNOWLUMA_DIR%\node.exe" (
    echo [ERROR] 未找到 SnowLuma: %SNOWLUMA_DIR%
    exit /b 0
)
echo [SnowLuma] 启动主进程 (自动注入开启)...
start "SnowLuma" /D "%SNOWLUMA_DIR%" cmd /k "set SNOWLUMA_HOOK_AUTOLOAD=1 && node.exe index.mjs"

:: 等待 WebUI 就绪
set /a webwait=0
:wait_webui
timeout /t 2 /nobreak >nul
set /a webwait+=2
powershell -Command "try {$r=Invoke-WebRequest -Uri 'http://127.0.0.1:5099' -TimeoutSec 2 -UseBasicParsing;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% equ 0 (
    echo [SnowLuma] WebUI ready
    exit /b 0
)
if %webwait% lss 60 goto wait_webui
echo [SnowLuma] WebUI 启动超时, 请检查 tools\SnowLuma 日志
exit /b 0

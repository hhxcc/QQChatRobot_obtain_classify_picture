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
set "SNOWLUMA_NODE=%SNOWLUMA_DIR%\node.exe"
set "SNOWLUMA_ENTRY=%SNOWLUMA_DIR%\index.mjs"
set "QQEXEDIR="
set RESTART_COUNT=0
for /f "tokens=2*" %%a in ('reg query "HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ" /v "UninstallString" 2^>nul') do set "QQEXEDIR=%%~dpb"

:: Main loop (守护 bot.py;崩溃自动重启)
:: 说明: 不再定时强杀 QQ。掉线自愈交给:
::   - SnowLuma 主进程 (WS 心跳 + 自动重连)
::   - SnowLuma 自动注入 (SNOWLUMA_HOOK_AUTOLOAD=1)
::   - watchdog 插件 (登录失效 → bot 退出 → 本脚本重启)
:main_loop

:: --- 确保 QQ 进程在线 (可拉起;失败则提示) ---
call :ensure_qq

:: --- 确保 SnowLuma 主进程 (带自动注入) ---
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
:: Ensure QQ 在线
:: =============================================
:ensure_qq
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if errorlevel 1 goto qq_absent
echo [Check] QQ.exe running
exit /b 0

:qq_absent
if not defined QQEXEDIR goto qq_no_path
if not exist "%QQEXEDIR%QQ.exe" goto qq_no_path
echo [QQ] QQ.exe 未运行, 尝试拉起...
start "" "%QQEXEDIR%QQ.exe"
set /a qqwait=0

:wait_qq
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if not errorlevel 1 goto qq_started
set /a qqwait+=2
if %qqwait% lss 30 goto wait_qq
echo [QQ] 拉起超时, 请手动启动并登录机器人小号 QQ
exit /b 0

:qq_started
echo [QQ] QQ.exe 已启动
exit /b 0

:qq_no_path
echo [QQ] 未找到 QQ 安装路径, 请手动启动并登录机器人小号 QQ
exit /b 0


:: =============================================
:: Ensure SnowLuma 主进程 (SNOWLUMA_HOOK_AUTOLOAD=1)
:: =============================================
:ensure_snowluma
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5099' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto snowluma_ready
if not exist "%SNOWLUMA_NODE%" goto snowluma_missing
if not exist "%SNOWLUMA_ENTRY%" goto snowluma_missing

echo [SnowLuma] 启动主进程 (自动注入开启)...
set SNOWLUMA_HOOK_AUTOLOAD=1
start "SnowLuma" /D "%SNOWLUMA_DIR%" "%SNOWLUMA_NODE%" "%SNOWLUMA_ENTRY%"

set /a webwait=0
:wait_webui
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5099' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto snowluma_ready
set /a webwait+=2
if %webwait% lss 60 goto wait_webui
echo [SnowLuma] WebUI 启动超时, 请检查 tools\SnowLuma
exit /b 0

:snowluma_ready
echo [Check] SnowLuma WebUI ready
exit /b 0

:snowluma_missing
echo [ERROR] 未找到 SnowLuma: %SNOWLUMA_DIR%
exit /b 0

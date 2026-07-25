@echo off
chcp 65001 >nul
title QQ Chat Robot - 动漫图片分类 (守护模式)
cd /d "%~dp0"

echo ========================================
echo   QQ Chat Robot - 守护进程模式
echo   动漫图片自动采集分类
echo ========================================
echo.

set NAPCAT_DIR=%~dp0tools\NapCatQQ
set RESTART_COUNT=0
set NAPCAT_RESTART_COUNT=0

:: ── 主循环 ──
:main_loop

:: 检查并启动 NapCatQQ
call :check_napcat

:: 启动 Bot
set /a RESTART_COUNT+=1
echo.
echo ========================================
echo   [第 %RESTART_COUNT% 次运行 Bot]
echo ========================================
echo.
.venv\Scripts\python.exe bot.py
set BOT_EXIT_CODE=%errorlevel%

echo.
echo Bot 退出 (退出码: %BOT_EXIT_CODE%)，5 秒后重启...
timeout /t 5 /nobreak >nul
goto main_loop


:: ── 检查 NapCatQQ 是否存活 ──
:check_napcat
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if %errorlevel% neq 0 goto napcat_restart
echo [检查] QQ.exe 运行中
echo [检查] NapCatQQ 已就绪
exit /b 0

:napcat_restart
set /a NAPCAT_RESTART_COUNT+=1
echo [NapCat 第 %NAPCAT_RESTART_COUNT% 次启动] QQ.exe 未运行，正在启动...
start "NapCatQQ" /D "%NAPCAT_DIR%" /MIN launcher-user.bat
echo   等待 NapCatQQ 就绪（最多 60 秒）...
set /a count=0

:wait_napcat
timeout /t 2 /nobreak >nul
set /a count+=2
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:6099' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 (
    echo [检查] NapCatQQ 已就绪
    exit /b 0
)
if %count% lss 60 goto wait_napcat
echo   ⚠ NapCatQQ 启动超时，继续尝试...
exit /b 0

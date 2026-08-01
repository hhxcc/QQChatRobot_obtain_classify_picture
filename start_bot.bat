@echo off
setlocal enabledelayedexpansion
title QQ Chat Robot - Daemon Mode
cd /d "%~dp0"

echo ========================================
echo   QQ Chat Robot - Daemon Mode
echo ========================================
echo.

set NAPCAT_DIR=%~dp0tools\NapCatQQ
set RESTART_COUNT=0
set NAPCAT_RESTART_COUNT=0
set NAPCAT_MAX_UPTIME=180

:: Main loop
:main_loop

:: --- Clean up stale timer processes ---
taskkill /FI "WINDOWTITLE eq NapCatTimer" /F >nul 2>&1

:: --- Check and start NapCatQQ ---
call :ensure_napcat

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
:: Ensure NapCatQQ is running (with retry)
:: =============================================
:ensure_napcat
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if %errorlevel% equ 0 (
    echo [Check] QQ.exe running
    exit /b 0
)

:: QQ.exe not found, start NapCat
set /a NAPCAT_RESTART_COUNT+=1
echo [NapCat #%NAPCAT_RESTART_COUNT%] Starting NapCatQQ...

:: Launch NapCat in its own directory
start "NapCatQQ" /D "%NAPCAT_DIR%" cmd /c launcher-user.bat

:: Wait for QQ.exe to appear (poll process list)
set /a count=0
:wait_qq
timeout /t 2 /nobreak >nul
set /a count+=2
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if %errorlevel% equ 0 goto napcat_ok
if %count% lss 30 goto wait_qq

:: QQ.exe didn't appear, retry once
echo   Retrying NapCatQQ launch...
taskkill /FI "WINDOWTITLE eq NapCatQQ" /F >nul 2>&1
start "NapCatQQ" /D "%NAPCAT_DIR%" cmd /c launcher-user.bat
set /a count=0
:wait_qq2
timeout /t 2 /nobreak >nul
set /a count+=2
tasklist /FI "IMAGENAME eq QQ.exe" 2>NUL | find /I "QQ.exe" >NUL
if %errorlevel% equ 0 goto napcat_ok
if %count% lss 30 goto wait_qq2
echo   WARNING: NapCatQQ failed to start
exit /b 0

:napcat_ok
:: Wait for WebUI to be ready
echo   Waiting for NapCatQQ WebUI...
set /a count=0
:wait_webui
timeout /t 2 /nobreak >nul
set /a count+=2
powershell -Command "try {$r=Invoke-WebRequest -Uri 'http://127.0.0.1:6099' -TimeoutSec 2 -UseBasicParsing;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% equ 0 goto napcat_ready
if %count% lss 60 goto wait_webui
echo   WARNING: NapCatQQ WebUI timeout
exit /b 0

:napcat_ready
echo [Check] NapCatQQ ready

:: Start the proactive restart timer
set /a TIMER_SEC=%NAPCAT_MAX_UPTIME%*60
start "NapCatTimer" /MIN powershell -WindowStyle Hidden -NoProfile -Command "Start-Sleep %TIMER_SEC%; taskkill /F /IM QQ.exe 2>$null"
echo [Timer] Will restart NapCat in %NAPCAT_MAX_UPTIME% min
exit /b 0

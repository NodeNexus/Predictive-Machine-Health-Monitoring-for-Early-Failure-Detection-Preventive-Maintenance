@echo off
setlocal enabledelayedexpansion
title Multimodal Machine Health Monitoring and Anomaly Detection - start all

rem ============================================================
rem Multimodal Machine Health Monitoring and Anomaly Detection - one file to run everything (Windows).
rem   1. creates the backend virtual environment if it is missing
rem   2. installs backend packages if they are missing
rem   3. checks the frontend packages
rem   4. starts the backend (port 8000) and frontend (port 5173)
rem   5. opens the dashboard in your browser
rem Servers that are already running are reused, not started twice.
rem To stop: close the "Multimodal Machine Health Monitoring and Anomaly Detection - BACKEND" and "Multimodal Machine Health Monitoring and Anomaly Detection - FRONTEND" windows.
rem ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "PYEXE=%ROOT%\backend\.venv\Scripts\python.exe"
set "BACKEND_URL=http://127.0.0.1:8000/api/health"
set "FRONTEND_URL=http://127.0.0.1:5173"

echo ============================================================
echo                       Multimodal Machine Health Monitoring and Anomaly Detection
echo ============================================================
echo Project root: %ROOT%
echo.

rem ---------- 1. backend virtual environment ----------
echo [1/5] Python environment...
if not exist "%PYEXE%" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found on PATH. Install Python 3.12 from https://www.python.org/ and run this file again.
        goto :fail
    )
    echo Creating backend\.venv ...
    python -m venv "%ROOT%\backend\.venv"
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        goto :fail
    )
)

rem ---------- 2. backend packages ----------
"%PYEXE%" -c "import fastapi, uvicorn, numpy, scipy, sklearn" >nul 2>&1
if errorlevel 1 (
    echo Installing backend packages ^(first run only, this can take several minutes^)...
    "%PYEXE%" -m pip install -r "%ROOT%\backend\requirements-dev.txt"
    if errorlevel 1 (
        echo [ERROR] Backend package install failed. Check your internet connection and the messages above.
        goto :fail
    )
)
echo [OK] Backend environment ready.
echo.

rem ---------- 3. frontend tooling ----------
echo [2/5] Frontend tooling...
set "FRONTEND_CMD=npm run dev"
call npm --version >nul 2>&1
if errorlevel 1 (
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Neither npm nor node was found on PATH. Install Node.js from https://nodejs.org/ and run this file again.
        goto :fail
    )
    if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
        echo [ERROR] npm is missing and the frontend packages are not installed. Install Node.js from https://nodejs.org/ and run this file again.
        goto :fail
    )
    set "FRONTEND_CMD=node node_modules\vite\bin\vite.js"
    echo [WARNING] npm was not found - using node directly.
) else (
    if not exist "%ROOT%\frontend\node_modules" (
        echo Installing frontend packages ^(first run only^)...
        pushd "%ROOT%\frontend"
        call npm install
        set "NPM_RESULT=!errorlevel!"
        popd
        if not "!NPM_RESULT!"=="0" (
            echo [ERROR] npm install failed.
            goto :fail
        )
    )
)
echo [OK] Frontend ready ^(%FRONTEND_CMD%^).
echo.

rem ---------- 4. dataset registry ----------
echo [3/5] Refreshing dataset registry...
if exist "%ROOT%\scripts\scan_datasets.py" (
    "%PYEXE%" "%ROOT%\scripts\scan_datasets.py" >nul 2>&1
    if errorlevel 1 (echo [WARNING] Dataset scan failed - continuing.) else (echo [OK] Dataset registry updated.)
) else (
    echo [WARNING] scripts\scan_datasets.py not found - skipping.
)
echo.

rem ---------- 5. start servers ----------
echo [4/5] Starting servers...
call :is_up "%BACKEND_URL%"
if "!UP!"=="1" (
    echo [OK] Backend is already running on port 8000.
) else (
    set "BUSY_PID="
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do set "BUSY_PID=%%p"
    if defined BUSY_PID (
        echo [ERROR] Port 8000 is held by process !BUSY_PID!, which is not answering as the Multimodal Machine Health Monitoring and Anomaly Detection backend.
        echo         It is often an old backend left running after its window was closed. To end it run:
        echo             taskkill /PID !BUSY_PID! /F
        echo         then run start_all.bat again.
        goto :fail
    )
    start "Multimodal Machine Health Monitoring and Anomaly Detection - BACKEND" /D "%ROOT%\backend" cmd /k ""%PYEXE%" -m uvicorn app.main:app --port 8000"
    echo Backend starting in its own window...
)
call :is_up "%FRONTEND_URL%"
if "!UP!"=="1" (
    echo [OK] Frontend is already running on port 5173.
) else (
    start "Multimodal Machine Health Monitoring and Anomaly Detection - FRONTEND" /D "%ROOT%\frontend" cmd /k "%FRONTEND_CMD%"
    echo Frontend starting in its own window...
)
echo.

call :wait_for "%BACKEND_URL%" "Backend"
call :wait_for "%FRONTEND_URL%" "Frontend"

echo.
echo [5/5] Opening the dashboard...
start "" "%FRONTEND_URL%"

echo.
echo ============================================================
echo   Multimodal Machine Health Monitoring and Anomaly Detection is running
echo   Dashboard: %FRONTEND_URL%
echo   Backend:   http://127.0.0.1:8000  ^(API only, docs at /docs^)
echo   To stop: close the BACKEND and FRONTEND windows.
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo Setup stopped. Fix the problem above and run start_all.bat again.
pause
exit /b 1

rem ---------- helpers ----------
:is_up
rem sets UP=1 if the URL answers, else UP=0
set "UP=0"
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set "UP=1"
goto :eof

:wait_for
rem waits up to ~60 seconds for a URL to answer
set "TRIES=0"
:wait_loop
set /a TRIES+=1
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%~1' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] %~2 is responding.
    goto :eof
)
if !TRIES! GEQ 30 (
    echo [WARNING] %~2 did not respond in time. Check its window for errors.
    goto :eof
)
ping -n 3 127.0.0.1 >nul
goto :wait_loop

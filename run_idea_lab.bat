@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem Multimodal Machine Health Monitoring and Anomaly Detection - one-click Windows startup launcher
rem This script only automates starting the existing backend and
rem frontend. It does not modify application logic, ports, or
rem configuration.
rem ============================================================

rem --- Resolve project root from this script's own location, ---
rem --- regardless of the caller's current directory.          ---
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYEXE=%ROOT%\backend\.venv\Scripts\python.exe"

echo ============================================================
echo                   Multimodal Machine Health Monitoring and Anomaly Detection
echo              MACHINE HEALTH PLATFORM
echo ============================================================
echo.
echo Project root: %ROOT%
echo.

echo [1/6] Checking project...

if not exist "%ROOT%\backend" (
    echo [ERROR] "backend" folder not found at "%ROOT%\backend"
    echo Make sure run_idea_lab.bat is in the Multimodal Machine Health Monitoring and Anomaly Detection project root.
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\frontend" (
    echo [ERROR] "frontend" folder not found at "%ROOT%\frontend"
    echo Make sure run_idea_lab.bat is in the Multimodal Machine Health Monitoring and Anomaly Detection project root.
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\scripts" (
    echo [WARNING] "scripts" folder not found - dataset scanning will be skipped.
)

if not exist "%ROOT%\DATASET" (
    echo [WARNING] "DATASET" folder not found - DEMO MODE vibration/acoustic
    echo           sources will be unavailable until it is added.
)

if not exist "%ROOT%\VIDEO" (
    echo [WARNING] "VIDEO" folder not found - DEMO MODE thermal sources
    echo           will be unavailable until it is added.
)

echo [OK] Project structure looks correct.
echo.

echo [2/6] Checking Python environment...

if not exist "%PYEXE%" (
    echo [ERROR] Multimodal Machine Health Monitoring and Anomaly Detection backend virtual environment was not found.
    echo.
    echo Expected: %PYEXE%
    echo.
    echo Please set up the backend environment first ^(see README.md^):
    echo   cd backend
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    echo.
    pause
    exit /b 1
)

echo [OK] Found backend virtual environment.
echo.

echo [3/6] Checking Node/npm...

set "FRONTEND_CMD=npm run dev"
call npm --version >nul 2>&1
if errorlevel 1 (
    rem npm is missing. If node and the installed Vite are available, run Vite through node directly.
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Neither npm nor node was found on PATH.
        echo Please install Node.js from https://nodejs.org/ and try again.
        echo.
        pause
        exit /b 1
    )
    if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
        echo [ERROR] npm was not found on PATH and Vite is not installed in frontend\node_modules.
        echo Please install Node.js from https://nodejs.org/ and run npm install in frontend.
        echo.
        pause
        exit /b 1
    )
    set "FRONTEND_CMD=node node_modules\vite\bin\vite.js"
    echo [WARNING] npm was not found on PATH - starting the frontend with node directly.
)

if not exist "%ROOT%\frontend\node_modules" (
    echo [ERROR] Frontend dependencies are not installed.
    echo Run:
    echo   cd frontend
    echo   npm install
    echo.
    pause
    exit /b 1
)

echo [OK] Frontend tooling and dependencies found ^(%FRONTEND_CMD%^).
echo.

echo [4/6] Scanning datasets...

if exist "%ROOT%\scripts\scan_datasets.py" (
    "%PYEXE%" "%ROOT%\scripts\scan_datasets.py"
    if errorlevel 1 (
        echo [WARNING] Dataset scan failed. Multimodal Machine Health Monitoring and Anomaly Detection can still start, but the
        echo           dataset registry may be incomplete.
    ) else (
        echo [OK] Dataset scan completed.
    )
) else (
    echo [WARNING] scripts\scan_datasets.py not found - skipping dataset scan.
)
echo.

echo [5/6] Starting backend...

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARNING] Port 8000 is already in use - the backend may already be running.
)

start "Multimodal Machine Health Monitoring and Anomaly Detection - BACKEND" /D "%ROOT%\backend" cmd /k ""%PYEXE%" -m uvicorn app.main:app --reload --port 8000"

echo [OK] Backend launch requested in its own window.
echo.

echo [6/6] Starting frontend...

netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARNING] Port 5173 is already in use - the frontend may already be running.
)

start "Multimodal Machine Health Monitoring and Anomaly Detection - FRONTEND" /D "%ROOT%\frontend" cmd /k "%FRONTEND_CMD%"

echo [OK] Frontend launch requested in its own window.
echo.

echo Waiting for services to become ready...
echo.

call :wait_for_url "http://127.0.0.1:8000/api/health" "Backend"
call :wait_for_url "http://127.0.0.1:5173" "Frontend"

start "" "http://127.0.0.1:5173"

echo.
echo ============================================================
echo                   Multimodal Machine Health Monitoring and Anomaly Detection READY
echo ============================================================
echo.
echo Dashboard:
echo   http://127.0.0.1:5173
echo.
echo Backend:
echo   http://127.0.0.1:8000
echo.
echo Health:
echo   http://127.0.0.1:8000/api/health
echo.
echo ============================================================
echo.
echo Backend and frontend are running in their own windows
echo ^(titled "Multimodal Machine Health Monitoring and Anomaly Detection - BACKEND" and "Multimodal Machine Health Monitoring and Anomaly Detection - FRONTEND"^).
echo Closing THIS window will NOT stop them.
echo To stop Multimodal Machine Health Monitoring and Anomaly Detection, close those two windows directly.
echo.
pause >nul
exit /b 0

rem ============================================================
rem :wait_for_url <url> <label>
rem Polls a URL with PowerShell (built into Windows, no curl
rem dependency) for up to ~15 seconds. Prints OK or a warning and
rem continues either way - never blocks startup indefinitely.
rem ============================================================
:wait_for_url
setlocal enabledelayedexpansion
set "URL=%~1"
set "LABEL=%~2"
set "TRIES=0"

:wait_for_url_loop
set /a TRIES+=1
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [OK] %LABEL% is responding at %URL%
    endlocal
    goto :eof
)

if !TRIES! GEQ 15 (
    echo [WARNING] %LABEL% did not respond within the expected time.
    echo           It may still be starting - check its window for details.
    endlocal
    goto :eof
)

timeout /t 1 /nobreak >nul
goto wait_for_url_loop

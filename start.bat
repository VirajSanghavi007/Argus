@echo off
title Argus AML Platform
cd /d "%~dp0"

echo.
echo  ========================================
echo   Argus - AML Intelligence Platform
echo  ========================================
echo.

:: ── Find Python ──────────────────────────────────────────────────────────
set PYTHON=
where python >nul 2>&1
if %errorlevel%==0 (set PYTHON=python) else (
    where py >nul 2>&1
    if %errorlevel%==0 (set PYTHON=py) else (
        echo [ERROR] Python not found. Install Python 3.11+ and add to PATH.
        pause & exit /b 1
    )
)
echo [OK] Python found.

:: ── Virtual Environment ──────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    %PYTHON% -m venv venv
    if not exist "venv\Scripts\activate.bat" (
        echo [ERROR] Failed to create venv.
        pause & exit /b 1
    )
    call venv\Scripts\activate.bat
    echo [SETUP] Installing dependencies...
    pip install -r config\requirements.txt -q
    echo [OK] Dependencies installed.
) else (
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment ready.
)

:: ── Pre-flight ───────────────────────────────────────────────────────────
if not exist "data" mkdir data
if not exist "logs" mkdir logs

if exist "data\multignn_model.pt" (
    echo [OK] Model file found.
) else (
    echo [WARN] No model file - app runs in degraded mode.
)

:: ── Launch ───────────────────────────────────────────────────────────────
echo.
echo [START] Starting Argus...
set PYTHONPATH=src
start "Argus" cmd /k "cd /d "%~dp0" && call venv\Scripts\activate.bat && set PYTHONPATH=src && python scripts\serve.py"

:: ── Wait for backend then open browser ───────────────────────────────────
echo [WAIT] Waiting for server...
set /a COUNT=0
:loop
if %COUNT% geq 120 (
    echo [ERROR] Server didn't start in 120s. Check the Argus window.
    pause & exit /b 1
)
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try{Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 2;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto :ready
set /a COUNT=%COUNT%+1
goto :loop

:ready
start "" http://localhost:8000
echo.
echo  ========================================
echo   Dashboard: http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo  ========================================
echo.
echo  [Close the Argus window to stop the server]
exit /b 0

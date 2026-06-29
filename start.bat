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
        goto :fail
    )
)
echo [OK] Found %PYTHON%

:: ── Virtual Environment ──────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Creating virtual environment...
    %PYTHON% -m venv venv
    if not exist "venv\Scripts\activate.bat" (
        echo [ERROR] Failed to create virtual environment.
        goto :fail
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment found.
)

call venv\Scripts\activate.bat

:: ── Dependencies ─────────────────────────────────────────────────────────
echo.
echo [SETUP] Installing dependencies...
pip install -r config\requirements.txt -q
echo [OK] Dependencies installed.

:: ── Pre-flight ───────────────────────────────────────────────────────────
echo.
if not exist "data" mkdir data
if not exist "logs" mkdir logs

if exist "data\multignn_model.pt" (
    echo [OK] Model file found.
) else (
    echo [WARN] No model file. App will run in degraded mode.
)

:: ── Start Backend ────────────────────────────────────────────────────────
echo.
echo [START] Launching backend...
set PYTHONPATH=src
start "Argus Backend" /min cmd /k "cd /d "%~dp0" && venv\Scripts\activate.bat && set PYTHONPATH=src && python scripts\serve.py"

:: ── Wait for Health ──────────────────────────────────────────────────────
echo [WAIT] Waiting for backend...

set /a COUNT=0

:loop
if %COUNT% geq 120 (
    echo.
    echo [ERROR] Backend did not start in 120 seconds.
    echo         Check the minimized "Argus Backend" window for errors.
    goto :fail
)

timeout /t 1 /nobreak >nul

powershell -NoProfile -Command "try{Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 2;exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto :ready

set /a COUNT=%COUNT%+1
goto :loop

:ready
echo.
echo [OK] Backend is running!
echo.
echo [START] Opening dashboard...
timeout /t 1 /nobreak >nul
start "" http://localhost:8000

echo.
echo  ========================================
echo   Dashboard: http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo  ========================================
echo.
echo  Close this window to stop.
pause >nul
goto :eof

:fail
echo.
pause
exit /b 1

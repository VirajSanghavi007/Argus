@echo off
setlocal enabledelayedexpansion
title Argus AML Platform
cd /d "%~dp0"

echo.
echo  ========================================
echo   Argus - AML Intelligence Platform
echo  ========================================
echo.

:: ── Find Python ──────────────────────────────────────────────────────────
set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if not defined PYTHON (
    where py >nul 2>&1 && set PYTHON=py
)
if not defined PYTHON (
    where python3 >nul 2>&1 && set PYTHON=python3
)
if not defined PYTHON (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    echo         Make sure "Add Python to PATH" is checked during installation.
    pause
    exit /b 1
)

:: Verify Python version (need 3.11+)
for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
echo [OK] Found Python %PYVER%

:: ── Virtual Environment ──────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo [SETUP] Creating virtual environment...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment found.
)

call venv\Scripts\activate.bat

:: ── Dependencies ─────────────────────────────────────────────────────────
echo.
echo [SETUP] Installing dependencies (this may take a few minutes on first run)...
pip install -r config\requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [WARN] Some packages may have failed. Trying again with verbose output...
    pip install -r config\requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies installed.

:: ── Pre-flight Checks ───────────────────────────────────────────────────
echo.
if not exist "data" mkdir data
if not exist "logs" mkdir logs

if exist "data\multignn_model.pt" (
    echo [OK] Model file found.
) else (
    echo [WARN] Model file not found at data\multignn_model.pt
    echo        App will start in degraded mode (no ML inference).
    echo        Train the model with: python scripts\train.py --epochs 8
)

:: ── Start Backend ────────────────────────────────────────────────────────
echo.
echo [START] Launching backend server...

:: Kill any existing process on port 8000
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /PID %%p /F >nul 2>&1
)

set PYTHONPATH=src
start /b "" python scripts\serve.py > nul 2>&1

:: ── Wait for Backend Health ──────────────────────────────────────────────
echo [WAIT] Waiting for backend to start...
set RETRIES=0
set MAX_RETRIES=30

:healthcheck
if !RETRIES! geq %MAX_RETRIES% (
    echo.
    echo [ERROR] Backend failed to start after 30 seconds.
    echo         Check logs\error_logs\errors.log for details.
    echo         Or try running manually: python scripts\serve.py
    pause
    exit /b 1
)

timeout /t 1 /nobreak >nul
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1

if errorlevel 1 (
    set /a RETRIES+=1
    set /a DOTS=RETRIES %% 4
    <nul set /p ="."
    goto healthcheck
)

echo.
echo [OK] Backend is running at http://localhost:8000

:: ── Open Frontend ────────────────────────────────────────────────────────
echo.
echo [START] Opening dashboard in browser...
start "" "http://localhost:8000"

echo.
echo  ========================================
echo   Argus is running!
echo   Dashboard: http://localhost:8000
echo   API docs:  http://localhost:8000/docs
echo  ========================================
echo.
echo  Press Ctrl+C or close this window to stop.
echo.

:: Keep window open so the background server stays alive
:keepalive
timeout /t 5 /nobreak >nul
tasklist /fi "imagename eq python.exe" 2>nul | findstr /i "python" >nul
if errorlevel 1 (
    echo.
    echo [STOP] Server process ended.
    pause
    exit /b 0
)
goto keepalive

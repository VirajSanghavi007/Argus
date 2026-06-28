@echo off
REM ============================================================================
REM  Argus AML — Full Startup
REM  Starts the FastAPI backend + opens the frontend in your default browser.
REM  Usage: start.bat [--train] [--autotune] [--epochs N] [--max-rows N]
REM         --train    : Train the model before starting the server
REM         --autotune : Enable hyperparameter grid search (implies --train)
REM ============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "DO_TRAIN="
set "TRAIN_ARGS="

:parse
if "%~1"=="" goto done_parse
if "%~1"=="--train" (
    set "DO_TRAIN=1"
    shift
    goto parse
)
if "%~1"=="--autotune" (
    set "DO_TRAIN=1"
    set "TRAIN_ARGS=!TRAIN_ARGS! --autotune"
    shift
    goto parse
)
if "%~1"=="--epochs" (
    set "TRAIN_ARGS=!TRAIN_ARGS! --epochs %~2"
    shift
    shift
    goto parse
)
if "%~1"=="--max-rows" (
    set "TRAIN_ARGS=!TRAIN_ARGS! --max-rows %~2"
    shift
    shift
    goto parse
)
shift
goto parse
:done_parse

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║            ARGUS AML — Intelligence Platform        ║
echo  ╠══════════════════════════════════════════════════════╣
echo  ║  Backend:  FastAPI + Multi-GNN Pipeline             ║
echo  ║  Frontend: http://localhost:8000                    ║
echo  ║                                                     ║
echo  ║  Auth:  Any Company ID / Name / Password (4+ chars) ║
echo  ║         Any 6-digit 2FA code                        ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python and add to PATH.
    exit /b 1
)

REM Activate venv if it exists
if exist "venv\Scripts\activate.bat" (
    echo  Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Optional: train model first
if defined DO_TRAIN (
    echo.
    echo  ── Training Multi-GNN ──
    call train_multi_gnn.bat %TRAIN_ARGS%
    if errorlevel 1 (
        echo  WARNING: Training failed, starting server with existing model.
    )
    echo.
)

REM Check if model exists
if not exist "data\multignn_model.pt" (
    echo  WARNING: No trained model found at data\multignn_model.pt
    echo           Run 'start.bat --train' or 'train_multi_gnn.bat' first.
    echo           Starting server anyway — pipeline will fail on inference.
    echo.
)

echo  Starting server on http://localhost:8000 ...
echo  Press Ctrl+C to stop.
echo.

REM Open browser after a short delay (non-blocking)
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"

REM Start the server (blocking — keeps window open)
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

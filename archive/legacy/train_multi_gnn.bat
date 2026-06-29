@echo off
REM Multi-GNN training orchestrator for multiple datasets with hyperparameter tuning
REM Usage: train_multi_gnn.bat [--autotune] [--epochs N] [--max-rows N]

setlocal enabledelayedexpansion

cd /d "%~dp0"

set "AUTOTUNE="
set "EPOCHS=8"
set "MAX_ROWS="

:parse_args
if "%~1"=="" goto done_args
if "%~1"=="--autotune" (
    set "AUTOTUNE=--autotune"
    shift
    goto parse_args
)
if "%~1"=="--epochs" (
    set "EPOCHS=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--max-rows" (
    set "MAX_ROWS=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args
:done_args

echo.
echo ============================================================================
echo  Multi-GNN Training on Multiple Datasets
echo ============================================================================
echo.
echo Configuration:
echo   Epochs: %EPOCHS%
if defined MAX_ROWS echo   Max rows per dataset: %MAX_ROWS%
if defined AUTOTUNE (
    echo   Autotune: ENABLED
) else (
    echo   Autotune: disabled
)
echo.
echo Available datasets:
if exist "data\IBM\HI-Small_Trans.csv" echo   - IBM HI-Small: data\IBM\HI-Small_Trans.csv
if exist "data\IBM\LI-Small_Trans.csv" echo   - IBM LI-Small: data\IBM\LI-Small_Trans.csv
if exist "data\TransXion\data\tx.csv" echo   - TransXion:    data\TransXion\data\tx.csv
if exist "data\SAML-D\SAML-D.csv" echo   - SAML-D:       data\SAML-D\SAML-D.csv
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python and add to PATH.
    exit /b 1
)

echo Starting training...
echo.

set "CMD=python backend/multignn_model.py --epochs %EPOCHS% --batch-size 4096 --pos-weight 7.1 --datasets data/IBM/LI-Small_Trans.csv data/TransXion/data/tx.csv"

if defined AUTOTUNE set "CMD=!CMD! --autotune"
if defined MAX_ROWS set "CMD=!CMD! --max-rows %MAX_ROWS%"

echo Command: !CMD!
echo.

!CMD!

if errorlevel 1 (
    echo.
    echo ERROR: Training failed with exit code %errorlevel%
    exit /b 1
)

echo.
echo ============================================================================
echo  Training Complete!
echo ============================================================================
echo.
echo Model saved to: data\multignn_model.pt
echo Metadata saved to: data\multignn_meta.json
echo.
echo Next steps:
echo   1. Review metrics in data\multignn_meta.json
echo   2. Run the FastAPI server: python -m uvicorn backend.main:app --reload
echo   3. Open http://localhost:8000 in your browser
echo.
pause

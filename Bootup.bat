@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "FRONTEND_FILE=%PROJECT_DIR%frontend\index.html"
set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please download it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Create venv if it doesn't exist
if not exist "%PYTHON_EXE%" (
    echo Virtual environment not found. Creating it now...
    python -m venv venv
    echo Installing dependencies...
    venv\Scripts\python -m pip install -r backend\requirements.txt
    echo Setup complete!
    echo.
)

echo Starting AML Backend...
start "AML Backend" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn main:app --host 0.0.0.0 --port 8000"

echo Waiting for backend to be ready...
:WAIT_LOOP
timeout /t 3 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health 2>nul | findstr "200" >nul
if errorlevel 1 goto WAIT_LOOP

echo.
echo AML System is running. Backend: http://localhost:8000
echo Opening frontend...
echo.

start "" "%FRONTEND_FILE%"
endlocal
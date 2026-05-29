@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "BACKEND_DIR=%PROJECT_DIR%backend"
set "FRONTEND_FILE=%PROJECT_DIR%frontend\index.html"
set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"

echo Starting AML Backend...

if not exist "%PYTHON_EXE%" (
    echo ERROR: Python virtual environment not found at:
    echo %PYTHON_EXE%
    echo.
    echo Please create it with:
    echo python -m venv venv
    echo venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

start "AML Backend" /D "%BACKEND_DIR%" cmd /k ""%PYTHON_EXE%" -m uvicorn main:app --host 0.0.0.0 --port 8000"

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

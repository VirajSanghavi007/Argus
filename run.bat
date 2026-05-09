@echo off
cd /d "C:\Users\viraj.DEEPA-S-LAPTOP\Downloads\Projects\Personal\IdeaHackathon\aml-prototype"

echo Starting AML Backend...
start "AML Backend" cmd /k "cd /d C:\Users\viraj.DEEPA-S-LAPTOP\Downloads\Projects\Personal\IdeaHackathon\aml-prototype\backend && ..\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"

echo Waiting for backend to be ready...

:WAIT_LOOP
timeout /t 3 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health 2>nul | findstr "200" >nul
if errorlevel 1 goto WAIT_LOOP

echo.
echo AML System is running. Backend: http://localhost:8000 ^| Frontend opening in browser...
echo.

start "" "%~dp0frontend\index.html"

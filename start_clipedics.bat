@echo off
title Clipedics Launcher
echo ========================================================
echo        Starting Clipedics (Option 1: Web UI)
echo ========================================================
echo.

cd /d "%~dp0"

:: Check Redis
echo Checking Redis service...
sc query Redis | find "RUNNING" >nul
if %ERRORLEVEL% neq 0 (
    echo Starting Redis service...
    net start Redis
) else (
    echo Redis service is running.
)

:: Set UTF-8 and PYTHONPATH
set PYTHONUTF8=1
set PYTHONPATH=%~dp0

:: Start FastAPI Backend
echo Starting Backend API (Port 8000)...
start "Clipedics - FastAPI Backend" cmd /k "cd /d %~dp0 && set PYTHONUTF8=1 && set PYTHONPATH=%~dp0 && .venv\Scripts\uvicorn.exe api.main:app --reload --port 8000"

:: Start Celery Worker
echo Starting Celery Worker...
start "Clipedics - Celery Worker" cmd /k "cd /d %~dp0 && set PYTHONUTF8=1 && set PYTHONPATH=%~dp0 && .venv\Scripts\celery.exe -A workers.celery_app worker --loglevel=info --pool=solo"

:: Start Next.js Frontend
echo Starting Next.js Frontend (Port 3000)...
start "Clipedics - Next.js Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo All services launched!
echo Opening http://localhost:3000 in your browser...
timeout /t 3 >nul
start http://localhost:3000

echo ========================================================
echo Clipedics is running!
echo Frontend: http://localhost:3000
echo API Docs: http://localhost:8000/docs
echo ========================================================


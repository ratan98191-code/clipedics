@echo off
title Stop Clipedics
echo Stopping Clipedics services...

taskkill /f /im uvicorn.exe 2>nul
taskkill /f /im celery.exe 2>nul
taskkill /f /im node.exe 2>nul

echo All Clipedics services stopped.
pause


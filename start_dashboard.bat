@echo off
echo ==========================================
echo    Starting Quickmeal CAPI Server...
echo ==========================================
echo.

:: Open the default web browser to the dashboard (it will load as soon as the server is ready)
start http://localhost:5000

:: Start the Python server in the foreground so closing this window stops the server
"%~dp0venv\Scripts\python.exe" "%~dp0app.py"

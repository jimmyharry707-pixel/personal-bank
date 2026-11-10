@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo PersonalBank is not installed yet. Run install_windows.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m personalbank
if errorlevel 1 (
    echo.
    echo PersonalBank exited with an error.
    pause
)

@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher was not found. Install Python 3.10 or newer first.
    pause
    exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo PersonalBank is installed. Run run_windows.bat to start it.
pause
exit /b 0
:error
echo.
echo Installation failed. Review the error above.
pause
exit /b 1

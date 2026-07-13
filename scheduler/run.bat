@echo off
REM Windows wrapper: activate the venv and run the scout.
REM Logging is handled by the app itself (state\scout.log, rotated).
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [%date% %time%] ERROR: .venv is missing. Run:  python setup.py
    exit /b 1
)

call .venv\Scripts\activate.bat
python run.py
exit /b %errorlevel%

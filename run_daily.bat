@echo off
cd /d "%~dp0"
chcp 65001 > nul
cls

echo =========================================================
echo    [A-Share Daily Radar] Starting Quantitative Scan...
echo =========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in .venv!
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py

echo.
echo =========================================================
echo  [Finished] Analysis report has been opened in browser!
echo  Press any key to close this window...
echo =========================================================
pause > nul

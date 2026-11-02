@echo off
title A-Share Daily Quant Radar V3.0
cd /d "D:\stock analysis"
cls
echo =========================================================
echo    [Daily Quant Radar V3.0] Running Market Scan...
echo =========================================================
echo.
if not exist "D:\stock analysis\.venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found!
    pause
    exit /b 1
)
"D:\stock analysis\.venv\Scripts\python.exe" -u "D:\stock analysis\main.py"
echo.
echo [Finished] Report updated on Desktop! Press any key to close...
pause > nul

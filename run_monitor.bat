@echo off
title A-Share Realtime Portfolio Monitor V3.0
cd /d "D:\stock analysis"
cls
echo =========================================================
echo    [Real-Time Monitor V3.0] Starting Portfolio Guard...
echo =========================================================
echo.
if not exist "D:\stock analysis\.venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found!
    pause
    exit /b 1
)
"D:\stock analysis\.venv\Scripts\python.exe" -u "D:\stock analysis\realtime_monitor.py" --force
echo.
echo [Finished] Press any key to close...
pause > nul

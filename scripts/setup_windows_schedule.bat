@echo off
REM Setup Windows Task Scheduler for algo loaders (MON-FRI)
REM Mimics AWS EventBridge schedule: 2 AM ET (morning) + 4:05 PM ET (afternoon)

setlocal enabledelayedexpansion
set ALGO_PATH=C:\Users\arger\code\algo
set PYTHON_CMD=python

echo.
echo Setting up Windows Task Scheduler for algo data loaders...
echo ================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python not found. Ensure python.exe is in PATH.
    exit /b 1
)
echo [OK] Python is available

REM Task 1: Morning pipeline (2:00 AM ET, MON-FRI)
echo.
echo Task 1: Morning Pipeline (2:00 AM ET, MON-FRI)
echo   - Loads prices, technical indicators, market status

REM Delete existing task if it exists
schtasks /delete /tn "algo\morning-pipeline" /f >nul 2>&1

REM Create new task (weekly, every weekday)
schtasks /create ^
    /tn "algo\morning-pipeline" ^
    /tr "python %ALGO_PATH%\scripts\run_local_orchestrator.py --morning" ^
    /sc weekly /d MON,TUE,WED,THU,FRI /st 02:00 ^
    /f

if errorlevel 1 (
    echo [FAIL] Failed to create morning task
    exit /b 1
)
echo [OK] Morning task scheduled for 2:00 AM ET (MON-FRI)

REM Task 2: Afternoon pipeline (4:05 PM ET, MON-FRI)
echo.
echo Task 2: Afternoon Pipeline (4:05 PM ET, MON-FRI)
echo   - Loads quality/growth/value scores, signals, risk metrics

REM Delete existing task if it exists
schtasks /delete /tn "algo\afternoon-pipeline" /f >nul 2>&1

REM Create new task (weekly, every weekday)
schtasks /create ^
    /tn "algo\afternoon-pipeline" ^
    /tr "python %ALGO_PATH%\scripts\run_local_orchestrator.py --afternoon" ^
    /sc weekly /d MON,TUE,WED,THU,FRI /st 16:05 ^
    /f

if errorlevel 1 (
    echo [FAIL] Failed to create afternoon task
    exit /b 1
)
echo [OK] Afternoon task scheduled for 4:05 PM ET (MON-FRI)

REM List created tasks
echo.
echo ================================
echo Scheduled Tasks Created:
schtasks /query /tn "algo" /fo table /v 2>nul | findstr /i "algo"

echo.
echo [SUCCESS] Task Scheduler setup complete!
echo The loaders will run automatically on MON-FRI at 2:00 AM and 4:05 PM ET
echo.
echo To view/manage tasks, open Task Scheduler (Win+R ^> taskschd.msc)
echo Tasks are under: Task Scheduler Library ^> algo
echo.

endlocal

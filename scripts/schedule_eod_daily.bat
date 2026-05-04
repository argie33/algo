@echo off
REM Schedule End-of-Day Loader Pipeline on Windows Task Scheduler
REM Run this script ONCE to register the daily job
REM
REM Usage:
REM   Run as Administrator: scripts\schedule_eod_daily.bat
REM
REM What it does:
REM   - Creates a Task Scheduler job "algo-eod-daily"
REM   - Runs every day at 5:30 PM (17:30) ET
REM   - Executes: scripts\eod_loader_wrapper.bat
REM   - Logs to: C:\algo-logs\

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Must run as Administrator
    echo Right-click this script and select "Run as administrator"
    pause
    exit /b 1
)

cd /d "%~dp0.."

echo.
echo === TASK SCHEDULER REGISTRATION ===
echo Task name: algo-eod-daily
echo Schedule: Daily at 5:30 PM (17:30)
echo Action: %CD%\scripts\eod_loader_wrapper.bat
echo.

REM Create the scheduled task
REM Syntax: schtasks /create /tn <TaskName> /tr <TaskRun> /sc <Schedule> /st <StartTime> /f
schtasks /create /tn "algo-eod-daily" ^
    /tr "%CD%\scripts\eod_loader_wrapper.bat" ^
    /sc daily /st 17:30 ^
    /f

if %errorLevel% neq 0 (
    echo.
    echo ERROR: Failed to create task. Check syntax or admin rights.
    pause
    exit /b 1
)

echo.
echo SUCCESS: Task scheduled.
echo.
echo Next steps:
echo   1. Verify in Task Scheduler (taskschd.msc)
echo   2. Right-click "algo-eod-daily" ^> Properties to adjust settings
echo   3. Set "Run with highest privileges" if needed
echo   4. Check C:\algo-logs for first run log
echo.
echo To manually run (test):
echo   schtasks /run /tn "algo-eod-daily"
echo.
echo To remove (if needed):
echo   schtasks /delete /tn "algo-eod-daily" /f
echo.
pause

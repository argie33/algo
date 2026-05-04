@echo off
REM Wrapper invoked by Windows Task Scheduler for AlgoOrchestrator.
REM Runs after patrol completes to evaluate trading conditions.

cd /d "%~dp0"

if not exist "%USERPROFILE%\algo_logs" mkdir "%USERPROFILE%\algo_logs"

set LOG=%USERPROFILE%\algo_logs\orchestrator-%date:~10,4%-%date:~4,2%-%date:~7,2%.log

echo === ORCHESTRATOR START %date% %time% === >> "%LOG%"
"C:\Program Files\Git\bin\bash.exe" -l -c "cd /c/Users/arger/code/algo && python3 algo_orchestrator.py" >> "%LOG%" 2>&1
echo === ORCHESTRATOR END %date% %time% (exit %errorlevel%) === >> "%LOG%"

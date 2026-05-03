@echo off
REM Wrapper invoked by Windows Task Scheduler for AlgoPatrolMorning.

cd /d "%~dp0"

if not exist "%USERPROFILE%\algo_logs" mkdir "%USERPROFILE%\algo_logs"

set LOG=%USERPROFILE%\algo_logs\patrol-%date:~10,4%-%date:~4,2%-%date:~7,2%.log

echo === PATROL START %date% %time% === >> "%LOG%"
"C:\Program Files\Git\bin\bash.exe" -l -c "cd /c/Users/arger/code/algo && python3 algo_data_patrol.py --quick" >> "%LOG%" 2>&1
echo === PATROL END %date% %time% (exit %errorlevel%) === >> "%LOG%"

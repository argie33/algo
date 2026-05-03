@echo off
REM Wrapper invoked by Windows Task Scheduler for AlgoEODPipeline.
REM Logs are timestamped in %USERPROFILE%\algo_logs.

cd /d "%~dp0"

if not exist "%USERPROFILE%\algo_logs" mkdir "%USERPROFILE%\algo_logs"

set LOG=%USERPROFILE%\algo_logs\eod-%date:~10,4%-%date:~4,2%-%date:~7,2%.log

echo === EOD PIPELINE START %date% %time% === >> "%LOG%"
"C:\Program Files\Git\bin\bash.exe" -l -c "cd /c/Users/arger/code/algo && bash run_eod_loaders.sh" >> "%LOG%" 2>&1
echo === EOD PIPELINE END %date% %time% (exit %errorlevel%) === >> "%LOG%"

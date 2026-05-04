@echo off
REM End-of-Day Loader Pipeline Wrapper
REM Runs the EOD loader script and logs output
REM Called by Windows Task Scheduler at 5:30 PM ET daily

REM Setup
cd /d "%~dp0.."
set LOG_DIR=C:\algo-logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set LOG_FILE=%LOG_DIR%\eod-%date:~-4%-%date:~-10,2%-%date:~-7,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%.log
set LOG_FILE=%LOG_FILE: =0%

REM Timestamp
echo [%date% %time%] === EOD LOADER PIPELINE STARTED === >> "%LOG_FILE%"

REM Run the actual loader script (bash via Git Bash or WSL)
REM Using bash.exe from Git for Windows
set BASH_PATH=C:\Program Files\Git\bin\bash.exe
if not exist "%BASH_PATH%" (
    echo [%date% %time%] ERROR: Git Bash not found at %BASH_PATH% >> "%LOG_FILE%"
    exit /b 1
)

"%BASH_PATH%" -l -i -c "cd '%CD%' && bash run_eod_loaders.sh" >> "%LOG_FILE%" 2>&1
set EXIT_CODE=%ERRORLEVEL%

REM Log completion
echo [%date% %time%] === EOD LOADER PIPELINE COMPLETED (exit code %EXIT_CODE%) === >> "%LOG_FILE%"

REM Notify on failure (optional - requires mail setup)
if %EXIT_CODE% neq 0 (
    echo [%date% %time%] ALERT: EOD pipeline failed. Check logs at %LOG_FILE% >> "%LOG_FILE%"
)

exit /b %EXIT_CODE%

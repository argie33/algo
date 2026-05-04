@echo off
REM Manual EOD Pipeline Trigger
REM Use this to manually run the EOD loaders (testing, recovery, etc.)
REM
REM Usage:
REM   scripts\eod_manual_trigger.bat

cd /d "%~dp0.."

echo.
echo === MANUAL EOD LOADER TRIGGER ===
echo Starting at %date% %time%
echo.

REM Run the actual bash script via Git Bash
set BASH_PATH=C:\Program Files\Git\bin\bash.exe
if not exist "%BASH_PATH%" (
    echo ERROR: Git Bash not found at %BASH_PATH%
    echo Please install Git for Windows or adjust BASH_PATH
    pause
    exit /b 1
)

REM Run with output visible (not logged to file like the scheduled version)
"%BASH_PATH%" -l -i -c "cd '%CD%' && bash run_eod_loaders.sh"
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% equ 0 (
    echo SUCCESS: EOD pipeline completed
) else (
    echo FAILED: EOD pipeline exited with code %EXIT_CODE%
)
echo.
pause

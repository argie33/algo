@echo off
REM ================================================================
REM ALGO TRADING SYSTEM - PostgreSQL Setup
REM Double-click this file to run setup as Administrator
REM ================================================================

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This batch file must be run as Administrator!
    echo.
    echo SOLUTION:
    echo   1. Right-click this file (SETUP-POSTGRESQL.bat)
    echo   2. Select "Run as administrator"
    echo.
    pause
    exit /b 1
)

cls
echo ================================================
echo ALGO TRADING SYSTEM - PostgreSQL Setup
echo ================================================
echo.

REM Run PowerShell setup script as admin
echo Running PostgreSQL installation...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "& 'C:\Users\arger\code\algo\install-and-setup-local.ps1'"

if %errorLevel% equ 0 (
    echo.
    echo ================================================
    echo Setup completed successfully!
    echo ================================================
    echo.
    echo Your system is ready. Next steps:
    echo   1. Edit .env.local with your Alpaca API keys
    echo   2. Run: npm start
    echo   3. Access: http://localhost:3001
    echo.
) else (
    echo.
    echo ================================================
    echo Setup encountered an error (exit code: %errorLevel%)
    echo ================================================
    echo.
    echo Check the log above for details.
    echo.
)

pause

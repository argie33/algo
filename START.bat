@echo off
REM ================================================================
REM ALGO TRADING SYSTEM - Start Application
REM ================================================================

cls
echo ================================================
echo ALGO TRADING SYSTEM - Starting Application
echo ================================================
echo.

REM Check if .env.local exists
if not exist ".env.local" (
    echo ERROR: .env.local not found!
    echo.
    echo SOLUTION: Copy .env.local.example to .env.local
    echo   Copy-Item .env.local.example -Destination .env.local
    echo.
    pause
    exit /b 1
)

REM Check if node_modules exists
if not exist "node_modules" (
    echo WARNING: node_modules not found. Installing dependencies...
    call npm install
    if %errorLevel% neq 0 (
        echo ERROR: npm install failed
        pause
        exit /b 1
    )
)

REM Start the application
echo.
echo Starting Express server on http://localhost:3001...
echo Press Ctrl+C to stop
echo.

npm start

pause

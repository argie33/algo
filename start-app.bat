@echo off
REM Start the Algo Trading System

color 0A
cls

echo ================================================
echo Algo Trading System - Starting Application
echo ================================================
echo.

REM Check if PostgreSQL is running
echo Checking PostgreSQL connection...
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost -c "SELECT 1;" >nul 2>&1

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Cannot connect to PostgreSQL database
    echo.
    echo Make sure:
    echo   1. PostgreSQL is installed
    echo   2. PostgreSQL service is running
    echo   3. Database 'stocks' exists with user 'stocks'
    echo.
    echo See POSTGRES_SETUP.md for detailed instructions
    echo.
    pause
    exit /b 1
)

echo PostgreSQL: Connected
echo.

REM Start the Node.js server
echo Starting Node.js server on http://localhost:3001
echo.
echo Press Ctrl+C to stop the server
echo.

npm start

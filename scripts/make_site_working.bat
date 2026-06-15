@echo off
REM Quick script to make your trading site fully working on Windows
REM Requires: Python 3.11+, PostgreSQL access (local, Docker, or cloud)

setlocal enabledelayedexpansion

cls
echo.
echo ============================================================
echo  MAKE YOUR TRADING SITE FULLY WORKING WITH REAL DATA
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ first.
    pause
    exit /b 1
)
echo [OK] Python found

REM Get database config from user
echo.
echo Database Configuration:
echo (Use localhost for local PostgreSQL or Docker)
echo (Use your RDS endpoint for AWS)
echo.

set /p DB_HOST="Database host (default: localhost): "
if "!DB_HOST!"=="" set DB_HOST=localhost

set /p DB_USER="Database user (default: postgres): "
if "!DB_USER!"=="" set DB_USER=postgres

set /p DB_PASSWORD="Database password: "
if "!DB_PASSWORD!"=="" (
    echo ERROR: Password required
    pause
    exit /b 1
)

set /p DB_NAME="Database name (default: algo): "
if "!DB_NAME!"=="" set DB_NAME=algo

echo.
echo Symbols to load (default: SPY,QQQ,IWM for quick test):
set /p SYMBOLS="Enter symbols or press Enter for defaults: "
if "!SYMBOLS!"=="" set SYMBOLS=SPY,QQQ,IWM

echo.
echo ============================================================
echo Starting the system...
echo ============================================================
echo.
echo Database: !DB_HOST!:5432/!DB_NAME!
echo Symbols: !SYMBOLS!
echo.
echo This will:
echo 1. Load real price data from yfinance
echo 2. Compute technical indicators
echo 3. Generate trading signals
echo Expected time: 10-20 minutes
echo.
pause

REM Run the system
set DB_HOST=!DB_HOST!
set DB_PORT=5432
set DB_USER=!DB_USER!
set DB_PASSWORD=!DB_PASSWORD!
set DB_NAME=!DB_NAME!

python run_local_system.py ^
  --host !DB_HOST! ^
  --port 5432 ^
  --user !DB_USER! ^
  --password !DB_PASSWORD! ^
  --database !DB_NAME! ^
  --symbols !SYMBOLS!

if errorlevel 1 (
    echo.
    echo ERROR: Failed to load data. Check your database connection.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo SUCCESS - YOUR SITE IS FULLY WORKING
echo ============================================================
echo.
echo NEXT: Start the API and Frontend
echo.
echo Option 1 - Command Line:
echo   Terminal 1: python lambda/api/lambda_function.py
echo   Terminal 2: cd webapp/frontend && npm run dev
echo   Browser: http://localhost:5173
echo.
echo Option 2 - PowerShell (Recommended):
echo   Copy-paste this into a new PowerShell window:
echo.
echo   $job = Start-Job { cd C:\Users\arger\code\algo; python lambda/api/lambda_function.py }
echo   Start-Sleep 3
echo   cd C:\Users\arger\code\algo\webapp\frontend
echo   npm run dev
echo.
echo Your site will be fully operational with REAL trading signals.
echo.
pause

@echo off
REM Verify the complete setup is working

setlocal enabledelayedexpansion
color 0A
cls

echo ================================================
echo Algo Trading System - Setup Verification
echo ================================================
echo.

set ERRORS=0

REM Check 1: Node.js
echo [1/5] Checking Node.js installation...
node --version >nul 2>&1
if %errorLevel% equ 0 (
    echo   [OK] Node.js installed
    node --version
) else (
    echo   [ERROR] Node.js not found
    set /a ERRORS+=1
)
echo.

REM Check 2: npm
echo [2/5] Checking npm installation...
npm --version >nul 2>&1
if %errorLevel% equ 0 (
    echo   [OK] npm installed
    npm --version
) else (
    echo   [ERROR] npm not found
    set /a ERRORS+=1
)
echo.

REM Check 3: npm dependencies
echo [3/5] Checking npm dependencies...
if exist "node_modules\express\package.json" (
    echo   [OK] express installed
) else (
    echo   [ERROR] express not installed
    set /a ERRORS+=1
)

if exist "node_modules\pg\package.json" (
    echo   [OK] pg (PostgreSQL driver) installed
) else (
    echo   [ERROR] pg not installed
    set /a ERRORS+=1
)

if exist "node_modules\cors\package.json" (
    echo   [OK] cors installed
) else (
    echo   [ERROR] cors not installed
    set /a ERRORS+=1
)
echo.

REM Check 4: PostgreSQL
echo [4/5] Checking PostgreSQL installation...
set PSQL_FOUND=0
for %%P in (
    "C:\Program Files\PostgreSQL\16\bin\psql.exe"
    "C:\Program Files\PostgreSQL\15\bin\psql.exe"
    "C:\Program Files\PostgreSQL\14\bin\psql.exe"
) do (
    if exist %%P (
        echo   [OK] PostgreSQL found: %%P
        %%P --version
        set PSQL_FOUND=1
    )
)

if %PSQL_FOUND% equ 0 (
    echo   [WARNING] PostgreSQL not installed
    echo   Download from: https://www.postgresql.org/download/windows/
    echo   Then run: setup-database.bat
    set /a ERRORS+=1
)
echo.

REM Check 5: PostgreSQL Service
echo [5/5] Checking PostgreSQL service...
sc query postgresql-x64-16 2>nul | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo   [OK] PostgreSQL service is running
) else (
    sc query postgresql-x64-16 2>nul | find "STOPPED" >nul
    if %errorLevel% equ 0 (
        echo   [WARNING] PostgreSQL service is installed but stopped
        echo   Run: net start postgresql-x64-16
    ) else (
        echo   [INFO] PostgreSQL service not found (not installed yet)
    )
)
echo.

REM Summary
echo ================================================
echo Setup Status
echo ================================================
echo.

if %ERRORS% equ 0 (
    echo Status: READY TO GO!
    echo.
    echo Next steps:
    echo   1. If PostgreSQL not installed:
    echo      - Download from https://www.postgresql.org/download/windows/
    echo      - Run installer with port 5432
    echo      - Run setup-database.bat
    echo.
    echo   2. Start the application:
    echo      npm start
    echo      OR double-click: start-app.bat
    echo.
    echo   3. Open browser:
    echo      http://localhost:3001
) else (
    echo Status: ISSUES FOUND
    echo.
    echo Please fix the errors listed above, then run this verification again.
    echo.
    echo For help, see:
    echo   - README_QUICK_START.txt
    echo   - SETUP_SUMMARY.md
    echo   - POSTGRES_SETUP.md
)

echo.
pause

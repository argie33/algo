@echo off
REM Setup stocks database - Run this AFTER PostgreSQL is installed

setlocal enabledelayedexpansion
color 0A
cls

echo ================================================
echo Database Setup for Algo Trading System
echo ================================================
echo.

REM Find PostgreSQL installation
echo Finding PostgreSQL installation...
set PSQL_FOUND=0
set PSQL_PATH=

for %%P in (
    "C:\Program Files\PostgreSQL\16\bin\psql.exe"
    "C:\Program Files\PostgreSQL\15\bin\psql.exe"
    "C:\Program Files\PostgreSQL\14\bin\psql.exe"
) do (
    if exist %%P (
        set PSQL_PATH=%%P
        set PSQL_FOUND=1
        goto :found_psql
    )
)

:found_psql
if %PSQL_FOUND% equ 0 (
    echo ERROR: PostgreSQL not found!
    echo.
    echo Please install PostgreSQL first from:
    echo https://www.postgresql.org/download/windows/
    echo.
    echo Then run this script again.
    echo.
    pause
    exit /b 1
)

echo Found PostgreSQL at: %PSQL_PATH%
echo.

REM Check if service is running
echo Checking PostgreSQL service status...
sc query postgresql-x64-16 | find "RUNNING" >nul 2>&1

if %errorLevel% neq 0 (
    echo Starting PostgreSQL service...
    net start postgresql-x64-16 >nul 2>&1
    if %errorLevel% neq 0 (
        echo ERROR: Could not start PostgreSQL service
        echo.
        echo Try starting it manually from Services (services.msc)
        echo.
        pause
        exit /b 1
    )
    timeout /t 3 /nobreak
)

echo PostgreSQL service is running
echo.

REM Create SQL setup script
echo Creating database setup script...
set "SQL_FILE=%temp%\setup_db.sql"

(
    echo -- Create stocks user
    echo DO $$ BEGIN
    echo     IF NOT EXISTS ^(SELECT FROM pg_user WHERE usename = 'stocks'^) THEN
    echo         CREATE USER stocks WITH PASSWORD 'bed0elAn';
    echo     END IF;
    echo END $$;
    echo.
    echo -- Create stocks database
    echo DO $$ BEGIN
    echo     IF NOT EXISTS ^(SELECT FROM pg_database WHERE datname = 'stocks'^) THEN
    echo         CREATE DATABASE stocks OWNER stocks;
    echo     END IF;
    echo END $$;
    echo.
    echo -- Grant privileges
    echo GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
    echo ALTER ROLE stocks WITH CREATEDB;
) > %SQL_FILE%

echo Executing database setup...
set PGPASSWORD=postgres
%PSQL_PATH% -U postgres -h localhost -f %SQL_FILE% >nul 2>&1
set PGPASSWORD=
del /q %SQL_FILE% 2>nul

if %errorLevel% equ 0 (
    echo Database setup successful!
) else (
    echo WARNING: Database setup may have encountered issues
)

echo.

REM Test connection
echo Testing database connection...
set PGPASSWORD=bed0elAn
%PSQL_PATH% -U stocks -d stocks -h localhost -c "SELECT NOW();" >nul 2>&1
set PGPASSWORD=

if %errorLevel% equ 0 (
    echo Connected successfully to stocks database!
    echo.
    echo ================================================
    echo Setup Complete!
    echo ================================================
    echo.
    echo You can now start the application:
    echo   npm start
    echo.
    echo Or double-click: start-app.bat
    echo.
) else (
    echo WARNING: Could not connect to database
    echo Please check:
    echo   1. PostgreSQL service is running
    echo   2. postgres superuser password is correct
    echo   See POSTGRES_SETUP.md for troubleshooting
    echo.
)

pause

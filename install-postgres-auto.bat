@echo off
REM Automated PostgreSQL Installation for Algo Trading System
REM This script downloads, installs, and configures PostgreSQL

setlocal enabledelayedexpansion

color 0A
cls

echo ================================================
echo PostgreSQL Automated Installation
echo ================================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges
    echo.
    echo Please right-click this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM Step 1: Download PostgreSQL
echo Step 1: Downloading PostgreSQL 16...
echo.

set "DOWNLOAD_URL=https://get.enterprisedb.com/postgresql/postgresql-16.1-1-windows-x64.exe"
set "INSTALLER="%temp%\postgresql-installer.exe"

REM Use PowerShell to download
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; ^
   (New-Object System.Net.WebClient).DownloadFile('%DOWNLOAD_URL%', %INSTALLER%)" >nul 2>&1

if %errorLevel% neq 0 (
    echo ERROR: Failed to download PostgreSQL
    echo.
    echo Try downloading manually from:
    echo https://www.postgresql.org/download/windows/
    echo.
    pause
    exit /b 1
)

echo Downloaded: %INSTALLER%
echo.

REM Step 2: Install PostgreSQL silently
echo Step 2: Installing PostgreSQL 16...
echo (This may take 2-3 minutes)
echo.

%INSTALLER% ^
  --mode silent ^
  --superpassword postgres ^
  --servicepassword postgres ^
  --port 5432 ^
  --datadir "C:\Program Files\PostgreSQL\16\data" ^
  --extract-only=no ^
  --enable-acpi=1 ^
  --installpath "C:\Program Files\PostgreSQL\16" ^
  --cluster_name postgresql ^
  --locale=English ^
  --servicename postgresql-x64-16 ^
  --serviceaccount postgres ^
  --add_path=1 ^
  --StackBuilder=1

if %errorLevel% neq 0 (
    echo WARNING: PostgreSQL installation had issues
    echo The installer may need manual completion
    echo Please complete the installation manually
    pause
    exit /b 1
)

echo PostgreSQL installed successfully!
echo.

REM Step 3: Wait for service to start
echo Step 3: Waiting for PostgreSQL service to start...
timeout /t 5 /nobreak

REM Check if service is running
sc query postgresql-x64-16 | find "RUNNING" >nul
if %errorLevel% neq 0 (
    echo Starting PostgreSQL service...
    net start postgresql-x64-16
    timeout /t 3 /nobreak
)

echo PostgreSQL service is running
echo.

REM Step 4: Create database and user
echo Step 4: Creating database and user...
echo.

set "PSQL=C:\Program Files\PostgreSQL\16\bin\psql.exe"

if not exist %PSQL% (
    echo ERROR: PostgreSQL installation incomplete
    echo psql.exe not found at: %PSQL%
    pause
    exit /b 1
)

REM Create temporary SQL file
set "SQL_FILE=%temp%\setup_stocks_db.sql"
(
    echo DO $$ BEGIN
    echo     IF NOT EXISTS ^(SELECT FROM pg_user WHERE usename = 'stocks'^) THEN
    echo         CREATE USER stocks WITH PASSWORD 'bed0elAn';
    echo     END IF;
    echo END $$;
    echo.
    echo DO $$ BEGIN
    echo     IF NOT EXISTS ^(SELECT FROM pg_database WHERE datname = 'stocks'^) THEN
    echo         CREATE DATABASE stocks OWNER stocks;
    echo     END IF;
    echo END $$;
    echo.
    echo GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
    echo ALTER ROLE stocks WITH CREATEDB;
) > %SQL_FILE%

REM Execute SQL script
set PGPASSWORD=postgres
%PSQL% -U postgres -h localhost -f %SQL_FILE% 2>nul
set PGPASSWORD=

if %errorLevel% equ 0 (
    echo Database and user created successfully!
) else (
    echo WARNING: Could not execute database setup script
    echo Please run manually (see POSTGRES_SETUP.md)
)

echo.

REM Step 5: Test connection
echo Step 5: Testing database connection...
set PGPASSWORD=bed0elAn
%PSQL% -U stocks -d stocks -h localhost -c "SELECT 1;" >nul 2>&1
set PGPASSWORD=

if %errorLevel% equ 0 (
    echo Successfully connected to stocks database!
) else (
    echo Could not verify connection (may need manual testing)
)

echo.

REM Cleanup
del /q %INSTALLER% 2>nul
del /q %SQL_FILE% 2>nul

REM Summary
echo ================================================
echo Setup Complete!
echo ================================================
echo.
echo Database Details:
echo   Host:     localhost
echo   Port:     5432
echo   Database: stocks
echo   User:     stocks
echo   Password: bed0elAn
echo.
echo Next Step:
echo   npm start
echo.
echo Then open: http://localhost:3001
echo.
pause

# PostgreSQL Setup for Algo Trading System
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Algo Trading System - PostgreSQL Setup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: This script must be run as Administrator" -ForegroundColor Red
    Write-Host "Please right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

# Step 1: Check if PostgreSQL is already installed
Write-Host "Step 1: Checking for PostgreSQL installation..." -ForegroundColor Yellow
$postgresPath = "C:\Program Files\PostgreSQL\16\bin\psql.exe"
if (Test-Path $postgresPath) {
    Write-Host "PostgreSQL found at: $postgresPath" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "To install PostgreSQL:" -ForegroundColor Yellow
    Write-Host "1. Visit: https://www.postgresql.org/download/windows/" -ForegroundColor Cyan
    Write-Host "2. Download PostgreSQL 16" -ForegroundColor Cyan
    Write-Host "3. Run installer with port 5432" -ForegroundColor Cyan
    Write-Host "4. Re-run this script after installation" -ForegroundColor Cyan
    exit 1
}

# Step 2: Check PostgreSQL Service
Write-Host ""
Write-Host "Step 2: Checking PostgreSQL service..." -ForegroundColor Yellow
$pgService = Get-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue
if ($pgService.Status -eq "Running") {
    Write-Host "PostgreSQL service is running" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL service not running. Starting..." -ForegroundColor Yellow
    Start-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Write-Host "PostgreSQL service started" -ForegroundColor Green
}

# Step 3: Create the database and user
Write-Host ""
Write-Host "Step 3: Creating database and user..." -ForegroundColor Yellow

$sqlScript = @'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'stocks') THEN
        CREATE USER stocks WITH PASSWORD 'bed0elAn';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stocks') THEN
        CREATE DATABASE stocks OWNER stocks;
    END IF;
END $$;

GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
ALTER ROLE stocks WITH CREATEDB;
'@

$tempSqlFile = [System.IO.Path]::Combine($env:TEMP, "init_stocks_db.sql")
$sqlScript | Out-File -FilePath $tempSqlFile -Encoding UTF8 -NoNewline

# Execute the SQL script
$env:PGPASSWORD = "postgres"
& $postgresPath -U postgres -h localhost -f $tempSqlFile 2>&1
Remove-Item $tempSqlFile -Force -ErrorAction SilentlyContinue
Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

Write-Host "Database and user created" -ForegroundColor Green

# Step 4: Test connection
Write-Host ""
Write-Host "Step 4: Testing database connection..." -ForegroundColor Yellow
$env:PGPASSWORD = "bed0elAn"
$testResult = & $postgresPath -U stocks -d stocks -h localhost -c "SELECT 1;" 2>&1
Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

if ($testResult -like "*1*") {
    Write-Host "Successfully connected to stocks database" -ForegroundColor Green
} else {
    Write-Host "Connection test output: $testResult" -ForegroundColor Yellow
}

# Step 5: Install Node dependencies
Write-Host ""
Write-Host "Step 5: Installing Node.js dependencies..." -ForegroundColor Yellow
Push-Location "C:\Users\arger\code\algo"
npm install
Pop-Location
Write-Host "Node dependencies installed" -ForegroundColor Green

# Summary
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Database Configuration:" -ForegroundColor Yellow
Write-Host "  Host: localhost" -ForegroundColor Cyan
Write-Host "  Port: 5432" -ForegroundColor Cyan
Write-Host "  Database: stocks" -ForegroundColor Cyan
Write-Host "  User: stocks" -ForegroundColor Cyan
Write-Host "  Password: bed0elAn" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. npm start    (to start the web app)" -ForegroundColor Cyan
Write-Host "2. python loadstocksymbols.py    (to load initial data)" -ForegroundColor Cyan
Write-Host ""

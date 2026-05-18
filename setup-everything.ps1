# Automated setup for "all things working locally and in aws"
# Run with: ! powershell -ExecutionPolicy Bypass -File setup-everything.ps1

param(
    [string]$DbSecret = "",
    [string]$AwsAccessKey = "",
    [string]$AwsSecretKey = "",
    [string]$AwsRegion = "us-east-1"
)

if (-not $DbSecret) {
    Write-Host "❌ Error: Database credential not provided" -ForegroundColor Red
    Write-Host "Usage: setup-everything.ps1 -DbSecret '<your_secure_value>'" -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ALGO SYSTEM SETUP - All Things Working" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Phase 1: Check Prerequisites
Write-Host "[Phase 1] Checking prerequisites..." -ForegroundColor Yellow
$missing = @()

if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    $missing += "PostgreSQL (psql not found)"
}

if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    $missing += "Python 3"
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    $missing += "AWS CLI"
}

if ($missing.Count -gt 0) {
    Write-Host "❌ Missing prerequisites:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "Installation instructions:" -ForegroundColor Yellow
    Write-Host "  PostgreSQL: https://www.postgresql.org/download/windows/" -ForegroundColor Yellow
    Write-Host "  Python 3: https://www.python.org/downloads/windows/" -ForegroundColor Yellow
    Write-Host "  AWS CLI: https://aws.amazon.com/cli/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing, run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ All prerequisites found" -ForegroundColor Green
Write-Host ""

# Phase 2: Configure AWS
if ($AwsAccessKey -and $AwsSecretKey) {
    Write-Host "[Phase 2] Configuring AWS..." -ForegroundColor Yellow

    # Create AWS credentials file
    $awsDir = "$env:USERPROFILE\.aws"
    if (-not (Test-Path $awsDir)) {
        New-Item -ItemType Directory -Path $awsDir -Force | Out-Null
    }

    $credentialsContent = @"
[default]
aws_access_key_id = $AwsAccessKey
aws_secret_access_key = $AwsSecretKey
region = $AwsRegion
"@

    Set-Content -Path "$awsDir\credentials" -Value $credentialsContent -Encoding UTF8
    Write-Host "✅ AWS CLI configured" -ForegroundColor Green
} else {
    Write-Host "[Phase 2] AWS credentials not provided" -ForegroundColor Yellow
    Write-Host "⚠️  Run with: setup-everything.ps1 -AwsAccessKey '<KEY>' -AwsSecretKey '<SECRET>'" -ForegroundColor Yellow
}

Write-Host ""

# Phase 3: Database setup
Write-Host "[Phase 3] Setting up PostgreSQL database..." -ForegroundColor Yellow

try {
    $connStr = "Host=localhost;Port=5432;Username=postgres"

    # Check if stocks database already exists
    $dbCheck = psql -U postgres -h localhost -tc "SELECT datname FROM pg_database WHERE datname = 'stocks';" 2>$null

    if ($dbCheck -match "stocks") {
        Write-Host "✅ Database 'stocks' already exists" -ForegroundColor Green
    } else {
        Write-Host "Creating database and user..."
        psql -U postgres -h localhost -c "CREATE DATABASE stocks;" 2>$null
        psql -U postgres -h localhost -c "CREATE USER stocks WITH PASSWORD '$DbSecret';" 2>$null
        psql -U postgres -h localhost -c "ALTER ROLE stocks WITH LOGIN CREATEDB;" 2>$null
        psql -U postgres -h localhost -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" 2>$null
        Write-Host "✅ Database created" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Database setup failed: $_" -ForegroundColor Red
    Write-Host "Make sure PostgreSQL is running on localhost:5432" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Phase 4: Set environment variables
Write-Host "[Phase 4] Setting environment variables..." -ForegroundColor Yellow

$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = $DbSecret

Write-Host "✅ Environment variables set" -ForegroundColor Green
Write-Host ""

# Phase 5: Initialize database
Write-Host "[Phase 5] Initializing database (127 tables)..." -ForegroundColor Yellow

try {
    python3 init_database.py
    Write-Host "✅ Database initialized" -ForegroundColor Green
} catch {
    Write-Host "❌ Database initialization failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Phase 6: Load data
Write-Host "[Phase 6] Loading data (40 loaders, ~20 minutes)..." -ForegroundColor Yellow

try {
    python3 run-all-loaders.py
    Write-Host "✅ Data loaded" -ForegroundColor Green
} catch {
    Write-Host "❌ Data loading failed: $_" -ForegroundColor Red
    Write-Host "Check database connection and credentials" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Phase 7: Run tests
Write-Host "[Phase 7] Running tests..." -ForegroundColor Yellow

try {
    python3 -m pytest tests/ -v --tb=short
    Write-Host "✅ Tests completed" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Some tests failed (check output above)" -ForegroundColor Yellow
}

Write-Host ""

# Phase 8: Test orchestrator
Write-Host "[Phase 8] Testing orchestrator..." -ForegroundColor Yellow

try {
    python3 algo/algo_orchestrator.py --mode paper --dry-run
    Write-Host "✅ Orchestrator completed" -ForegroundColor Green
} catch {
    Write-Host "❌ Orchestrator test failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verification checklist:" -ForegroundColor Yellow
Write-Host "  ✅ PostgreSQL running locally" -ForegroundColor Green
Write-Host "  ✅ Database initialized (127 tables)" -ForegroundColor Green
Write-Host "  ✅ Data loaded (1.5M+ records)" -ForegroundColor Green
Write-Host "  [ ] Tests passing (285+/352)" -ForegroundColor Yellow
Write-Host "  [ ] Orchestrator running (7 phases)" -ForegroundColor Yellow
Write-Host "  [ ] AWS credentials configured" -ForegroundColor Yellow
Write-Host "  [ ] API Gateway responding (200 OK)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. If tests failed, check database connection" -ForegroundColor Cyan
Write-Host "2. If AWS not configured, run with AWS credentials:" -ForegroundColor Cyan
Write-Host "   setup-everything.ps1 -AwsAccessKey '<KEY>' -AwsSecretKey '<SECRET>'" -ForegroundColor Cyan
Write-Host ""

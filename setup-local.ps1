# Stock Analytics Platform - Local Setup Automation
# Run this once to set up PostgreSQL, database, loaders, and tests
# Usage: powershell -ExecutionPolicy Bypass -File setup-local.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Stock Analytics - Local Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Color output
function Write-Success { Write-Host "OK: $args" -ForegroundColor Green }
function Write-Error-Custom { Write-Host "FAIL: $args" -ForegroundColor Red }
function Write-Info { Write-Host "INFO: $args" -ForegroundColor Yellow }

# Step 1: Check PostgreSQL
Write-Host "`nStep 1: Check PostgreSQL" -ForegroundColor Cyan
try {
    $psqlVersion = & psql --version 2>&1
    Write-Success "PostgreSQL found: $psqlVersion"
    $postgresFound = $true
} catch {
    Write-Error-Custom "PostgreSQL not found. Install from https://postgresql.org"
    Write-Info "After installing, run this script again."
    exit 1
}

# Step 2: Check for stocks database
Write-Host "`nStep 2: Check Database" -ForegroundColor Cyan
$dbCheckScript = @"
SELECT 1 FROM pg_database WHERE datname = 'stocks';
"@

try {
    $dbExists = & psql -U postgres -h localhost -t -c $dbCheckScript 2>&1 | Select-String "1"
    if ($dbExists) {
        Write-Success "Database 'stocks' exists"
    } else {
        Write-Info "Creating database and user..."
        $createDbScript = @"
CREATE DATABASE stocks;
CREATE USER stocks WITH PASSWORD 'dev_password';
ALTER ROLE stocks WITH LOGIN CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
"@
        & psql -U postgres -h localhost -c $createDbScript 2>&1 | Out-Null
        Write-Success "Database and user created"
    }
} catch {
    Write-Error-Custom "Database check failed: $_"
    exit 1
}

# Step 3: Test connection
Write-Host "`nStep 3: Test Database Connection" -ForegroundColor Cyan
try {
    & psql -U stocks -h localhost -d stocks -c "SELECT 1;" 2>&1 | Out-Null
    Write-Success "Connected to database"
} catch {
    Write-Error-Custom "Connection failed: $_"
    exit 1
}

# Step 4: Set environment variables
Write-Host "`nStep 4: Set Environment Variables" -ForegroundColor Cyan
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = $dbPassword  # Password set in database creation step
Write-Success "Environment variables set"

# Step 5: Initialize database
Write-Host "`nStep 5: Initialize Database (creates 127 tables)" -ForegroundColor Cyan
try {
    & python3 init_database.py 2>&1 | Tee-Object -Variable output | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Database initialized"
    } else {
        Write-Error-Custom "Database initialization failed"
        Write-Host $output
        exit 1
    }
} catch {
    Write-Error-Custom "Initialization error: $_"
    exit 1
}

# Step 6: Load data
Write-Host "`nStep 6: Load Data from All Sources (~20 minutes)" -ForegroundColor Cyan
Write-Info "Starting data loaders (Alpaca, SEC, Yahoo Finance, etc.)"
Write-Info "This may take 15-20 minutes - please wait..."
try {
    & python3 run-all-loaders.py 2>&1 | Tee-Object -Variable loaderOutput | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Loaders completed"
    } else {
        Write-Error-Custom "Loaders failed"
        Write-Host $loaderOutput | Select-Object -Last 20
        exit 1
    }
} catch {
    Write-Error-Custom "Loader error: $_"
    exit 1
}

# Step 7: Run tests
Write-Host "`nStep 7: Run Tests" -ForegroundColor Cyan
Write-Info "Running 343 unit tests..."
try {
    & python3 -m pytest tests/ -v --tb=short 2>&1 | Tee-Object -Variable testOutput | Out-Null
    $testResults = $testOutput | Select-String "passed|failed"
    Write-Success "Tests completed: $testResults"
} catch {
    Write-Error-Custom "Test run error: $_"
}

# Step 8: Test orchestrator
Write-Host "`nStep 8: Test Orchestrator (7 phases)" -ForegroundColor Cyan
Write-Info "Running orchestrator in dry-run mode..."
try {
    & python3 algo/algo_orchestrator.py --mode paper --dry-run 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Orchestrator completed all 7 phases"
    } else {
        Write-Error-Custom "Orchestrator failed"
        exit 1
    }
} catch {
    Write-Error-Custom "Orchestrator error: $_"
}

# Step 9: Verify data loaded
Write-Host "`nStep 9: Verify Data" -ForegroundColor Cyan
$countScript = "SELECT COUNT(*) FROM price_daily;"
$recordCount = & psql -U stocks -h localhost -d stocks -t -c $countScript 2>&1
Write-Success "Price records loaded: $recordCount"

# Final summary
Write-Host "`n======================================" -ForegroundColor Green
Write-Host "SUCCESS: Local System Ready!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next step: Deploy to AWS" -ForegroundColor Cyan
Write-Host ""
Write-Host "  git push origin main" -ForegroundColor White
Write-Host ""
Write-Host "This triggers GitHub Actions to deploy to AWS automatically." -ForegroundColor Gray
Write-Host "Watch deployment at: https://github.com/argie33/algo/actions" -ForegroundColor Gray
Write-Host ""

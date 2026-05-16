# ================================================================
# ALGO TRADING SYSTEM - COMPLETE LOCAL SETUP
# Run this script as Administrator to set up local development environment
# ================================================================

# Check if running as admin
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Please:" -ForegroundColor Yellow
    Write-Host "  1. Right-click PowerShell" -ForegroundColor Cyan
    Write-Host "  2. Select 'Run as Administrator'" -ForegroundColor Cyan
    Write-Host "  3. Run: Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process" -ForegroundColor Cyan
    Write-Host "  4. Run: C:\Users\arger\code\algo\install-and-setup-local.ps1" -ForegroundColor Cyan
    exit 1
}

$scriptPath = "C:\Users\arger\code\algo"
$postgresInstallerPath = "$env:TEMP\postgres-installer.exe"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "ALGO TRADING SYSTEM - LOCAL SETUP" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# =================================================================
# STEP 1: PostgreSQL Installation
# =================================================================
Write-Host "STEP 1: Installing PostgreSQL 17..." -ForegroundColor Yellow

if (Test-Path $postgresInstallerPath) {
    Write-Host "✓ PostgreSQL installer found (353 MB)" -ForegroundColor Green
    Write-Host "  Starting installation (this may take 2-3 minutes)..." -ForegroundColor Cyan
    Write-Host ""

    # Run installer with silent options
    $process = Start-Process -FilePath $postgresInstallerPath -ArgumentList @(
        '/S',
        '/VERYSILENT',
        '/NORESTART',
        '/D=C:\Program Files\PostgreSQL\17',
        '/CLUSERNAME=postgres',
        '/CLUSTERPASS=postgres'
    ) -PassThru -Wait

    Start-Sleep -Seconds 3

    if (Test-Path "C:\Program Files\PostgreSQL\17\bin\psql.exe") {
        Write-Host "✓ PostgreSQL 17 installed successfully!" -ForegroundColor Green
        $psqlExe = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
    } else {
        Write-Host "⚠ Installation may have completed but directory not found" -ForegroundColor Yellow
        Write-Host "  Checking alternative locations..." -ForegroundColor Cyan
        $psqlExe = Get-ChildItem "C:\Program Files\PostgreSQL" -Filter "psql.exe" -Recurse | Select-Object -ExpandProperty FullName -First 1
        if ($psqlExe) {
            Write-Host "✓ Found at: $psqlExe" -ForegroundColor Green
        }
    }
} else {
    Write-Host "✗ PostgreSQL installer not found at $postgresInstallerPath" -ForegroundColor Red
    Write-Host "  Download from: https://www.enterprisedb.com/downloads/postgres-postgresql-downloads" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# =================================================================
# STEP 2: Start PostgreSQL Service
# =================================================================
Write-Host "STEP 2: Starting PostgreSQL Service..." -ForegroundColor Yellow

$serviceNames = @("postgresql-x64-17", "postgresql-x64-16", "postgresql-x64-15")
$pgService = $null

foreach ($serviceName in $serviceNames) {
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc) {
        $pgService = $svc
        break
    }
}

if ($pgService) {
    if ($pgService.Status -ne "Running") {
        Write-Host "Starting service: $($pgService.Name)" -ForegroundColor Cyan
        Start-Service -Name $pgService.Name
        Start-Sleep -Seconds 3
    }
    Write-Host "✓ PostgreSQL service is running" -ForegroundColor Green
} else {
    Write-Host "⚠ PostgreSQL service not found. It may auto-start on next reboot." -ForegroundColor Yellow
}

Write-Host ""

# =================================================================
# STEP 3: Create Database and User
# =================================================================
Write-Host "STEP 3: Creating 'stocks' database and 'stocks' user..." -ForegroundColor Yellow

$sqlScript = @"
DO `$`$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'stocks') THEN
        CREATE USER stocks WITH PASSWORD 'bed0elAn';
    END IF;
END `$`$;

DO `$`$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stocks') THEN
        CREATE DATABASE stocks OWNER stocks;
    END IF;
END `$`$;

GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
ALTER ROLE stocks WITH CREATEDB;
"@

$tempSqlFile = [System.IO.Path]::Combine($env:TEMP, "init_stocks_db.sql")
$sqlScript | Out-File -FilePath $tempSqlFile -Encoding UTF8 -NoNewline

# Execute SQL
$env:PGPASSWORD = "postgres"
try {
    & $psqlExe -U postgres -h localhost -f $tempSqlFile 2>&1 | Write-Host
    Write-Host "✓ Database and user created" -ForegroundColor Green
} catch {
    Write-Host "⚠ Error creating database. Check PostgreSQL service is running." -ForegroundColor Yellow
    Write-Host "  Error: $_" -ForegroundColor Gray
}
finally {
    Remove-Item $tempSqlFile -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""

# =================================================================
# STEP 4: Test Database Connection
# =================================================================
Write-Host "STEP 4: Testing database connection..." -ForegroundColor Yellow

$env:PGPASSWORD = "bed0elAn"
$testResult = & $psqlExe -U stocks -d stocks -h localhost -c "SELECT 1;" 2>&1
Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

if ($testResult -like "*1*") {
    Write-Host "✓ Successfully connected to stocks database" -ForegroundColor Green
} else {
    Write-Host "⚠ Connection test output: $testResult" -ForegroundColor Yellow
}

Write-Host ""

# =================================================================
# STEP 5: Install Node Dependencies
# =================================================================
Write-Host "STEP 5: Installing Node.js dependencies..." -ForegroundColor Yellow

Push-Location $scriptPath
Write-Host "Running: npm install" -ForegroundColor Cyan
npm install

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Node dependencies installed" -ForegroundColor Green
} else {
    Write-Host "⚠ npm install completed with status: $LASTEXITCODE" -ForegroundColor Yellow
}
Pop-Location

Write-Host ""

# =================================================================
# STEP 6: Create .env.local File
# =================================================================
Write-Host "STEP 6: Creating .env.local configuration..." -ForegroundColor Yellow

$envLocalPath = Join-Path $scriptPath ".env.local"

if (-not (Test-Path $envLocalPath)) {
    $envContent = @"
# ================================================================
# LOCAL DEVELOPMENT ENVIRONMENT
# ================================================================

# DATABASE CONFIGURATION (Local PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=stocks
DB_PASSWORD=bed0elAn
DB_SSL=false

# Connection pool settings
DB_POOL_MAX=10
DB_POOL_MIN=2
DB_POOL_IDLE_TIMEOUT=30000
DB_CONNECT_TIMEOUT=5000
DB_STATEMENT_TIMEOUT=30000
DB_QUERY_TIMEOUT=25000

# ENVIRONMENT TYPE
ENVIRONMENT=local
NODE_ENV=development
PORT=3001

# TRADING ALGORITHM CONFIGURATION
EXECUTION_MODE=auto
ORCHESTRATOR_DRY_RUN=false
ORCHESTRATOR_LOG_LEVEL=debug
DATA_PATROL_ENABLED=true
DATA_PATROL_TIMEOUT_MS=30000

# ALPACA TRADING API (Paper Trading)
APCA_API_BASE_URL=https://paper-api.alpaca.markets
APCA_API_KEY_ID=<YOUR_ALPACA_API_KEY>
APCA_API_SECRET_KEY=<YOUR_ALPACA_SECRET_KEY>
ALPACA_PAPER_TRADING=true

# AWS CONFIGURATION
AWS_REGION=us-east-1

# FRONTEND & WEB
FRONTEND_URL=http://localhost:5173
WEBSITE_URL=http://localhost:5173
API_STAGE=dev

# AUTHENTICATION
LOCAL_DEV_MODE=true
ALLOW_DEV_BYPASS=true
JWT_SECRET=local-dev-secret-key-change-in-production
"@

    $envContent | Out-File -FilePath $envLocalPath -Encoding UTF8
    Write-Host "✓ Created .env.local" -ForegroundColor Green
    Write-Host "  Edit with your Alpaca credentials: $envLocalPath" -ForegroundColor Cyan
} else {
    Write-Host "✓ .env.local already exists" -ForegroundColor Green
}

Write-Host ""

# =================================================================
# SETUP COMPLETE
# =================================================================
Write-Host "================================================" -ForegroundColor Green
Write-Host "✓ SETUP COMPLETE!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Database Configuration:" -ForegroundColor Cyan
Write-Host "  Host: localhost" -ForegroundColor White
Write-Host "  Port: 5432" -ForegroundColor White
Write-Host "  Database: stocks" -ForegroundColor White
Write-Host "  User: stocks" -ForegroundColor White
Write-Host "  Password: bed0elAn" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env.local and add your Alpaca API credentials" -ForegroundColor Cyan
Write-Host "  2. Run: npm start" -ForegroundColor Cyan
Write-Host "  3. Load initial data: python loadstocksymbols.py" -ForegroundColor Cyan
Write-Host "  4. Check http://localhost:3001" -ForegroundColor Cyan
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Yellow
Write-Host "  psql -h localhost -U stocks -d stocks    # Connect to database" -ForegroundColor Cyan
Write-Host "  npm start                                  # Start application" -ForegroundColor Cyan
Write-Host "  npm test                                   # Run tests" -ForegroundColor Cyan
Write-Host ""

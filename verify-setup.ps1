# ================================================================
# VERIFY SETUP STATUS
# Run anytime to check your local environment
# No admin required!
# ================================================================

$scriptPath = "C:\Users\arger\code\algo"
$env:PATH = "C:\tools\bin;$env:PATH"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "ALGO TRADING SYSTEM - SETUP VERIFICATION" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Checking your local environment..." -ForegroundColor Yellow
Write-Host ""

# =================================================================
# Git
# =================================================================
Write-Host "📦 GIT" -ForegroundColor Cyan
try {
    $gitVersion = C:\tools\bin\git.exe --version
    Write-Host "  ✓ Installed: $gitVersion" -ForegroundColor Green

    # Check repo status
    Push-Location $scriptPath
    $status = C:\tools\bin\git.exe status --short
    $branch = C:\tools\bin\git.exe rev-parse --abbrev-ref HEAD
    Write-Host "  ✓ Repository: $branch ($(if ($status) { 'modified' } else { 'clean' }))" -ForegroundColor Green
    Pop-Location
} catch {
    Write-Host "  ✗ Git not available" -ForegroundColor Red
}

# =================================================================
# Node.js & npm
# =================================================================
Write-Host ""
Write-Host "📦 NODE.JS & NPM" -ForegroundColor Cyan
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "  ✓ Node.js: $nodeVersion" -ForegroundColor Green
    Write-Host "  ✓ npm: $npmVersion" -ForegroundColor Green

    # Check node_modules
    $modulesPath = Join-Path $scriptPath "node_modules"
    if (Test-Path $modulesPath) {
        $moduleCount = (Get-ChildItem $modulesPath -Directory).Count
        Write-Host "  ✓ Dependencies: $moduleCount packages installed" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Dependencies: Not installed (run 'npm install')" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ Node.js/npm not available" -ForegroundColor Red
}

# =================================================================
# Python
# =================================================================
Write-Host ""
Write-Host "📦 PYTHON" -ForegroundColor Cyan
try {
    $pythonVersion = python --version
    Write-Host "  ✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python not available" -ForegroundColor Red
}

# =================================================================
# PostgreSQL
# =================================================================
Write-Host ""
Write-Host "🗄️  POSTGRESQL" -ForegroundColor Cyan

$psqlPaths = @(
    "C:\Program Files\PostgreSQL\17\bin\psql.exe",
    "C:\Program Files\PostgreSQL\16\bin\psql.exe",
    "C:\Program Files\PostgreSQL\15\bin\psql.exe"
)

$psqlFound = $false
foreach ($path in $psqlPaths) {
    if (Test-Path $path) {
        try {
            $pgVersion = & $path --version
            Write-Host "  ✓ Installed: $pgVersion" -ForegroundColor Green
            $psqlFound = $true

            # Test connection
            $env:PGPASSWORD = "bed0elAn"
            $testResult = & $path -U stocks -d stocks -h localhost -c "SELECT 1;" 2>&1
            if ($testResult -like "*1*") {
                Write-Host "  + Connection: stocks@localhost (OK)" -ForegroundColor Green
            } else {
                Write-Host "  ~ Connection: Failed (PostgreSQL service might not be running)" -ForegroundColor Yellow
            }
            Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        } catch {
            Write-Host "  ⚠ PostgreSQL found but connection failed" -ForegroundColor Yellow
        }
        break
    }
}

if (-not $psqlFound) {
    Write-Host "  ⚠ Not installed (run 'install-and-setup-local.ps1' as Administrator)" -ForegroundColor Yellow
}

# =================================================================
# Configuration Files
# =================================================================
Write-Host ""
Write-Host "⚙️  CONFIGURATION" -ForegroundColor Cyan

$envLocalPath = Join-Path $scriptPath ".env.local"
if (Test-Path $envLocalPath) {
    Write-Host "  ✓ .env.local exists" -ForegroundColor Green

    # Check if Alpaca credentials are set
    $envContent = Get-Content $envLocalPath -Raw
    if ($envContent -match "APCA_API_KEY_ID=.*YOUR|APCA_API_KEY_ID=<") {
        Write-Host "  ⚠ .env.local: Alpaca credentials not configured" -ForegroundColor Yellow
    } elseif ($envContent -match "APCA_API_KEY_ID=\$|APCA_API_KEY_ID=$") {
        Write-Host "  ⚠ .env.local: Alpaca credentials not set" -ForegroundColor Yellow
    } else {
        Write-Host "  ✓ .env.local: Alpaca credentials configured" -ForegroundColor Green
    }
} else {
    Write-Host "  ⚠ .env.local not found (will be created by setup script)" -ForegroundColor Yellow
}

# =================================================================
# Key Files
# =================================================================
Write-Host ""
Write-Host "📄 KEY PROJECT FILES" -ForegroundColor Cyan

$keyFiles = @(
    "package.json",
    "webpack.config.js",
    "setup-postgres.ps1",
    "install-and-setup-local.ps1",
    "LOCAL_SETUP_STATUS.md",
    "AWS_SETUP_CHECKLIST.md"
)

foreach ($file in $keyFiles) {
    $filePath = Join-Path $scriptPath $file
    if (Test-Path $filePath) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $file (missing)" -ForegroundColor Yellow
    }
}

# =================================================================
# AWS Tools (optional)
# =================================================================
Write-Host ""
Write-Host "☁️  AWS TOOLS (Optional)" -ForegroundColor Cyan

if (Get-Command aws -ErrorAction SilentlyContinue) {
    $awsVersion = aws --version
    Write-Host "  ✓ AWS CLI: $awsVersion" -ForegroundColor Green

    # Check credentials
    try {
        $identity = aws sts get-caller-identity 2>&1
        if ($identity -match "Account") {
            Write-Host "  ✓ AWS Credentials: Configured" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠ AWS Credentials: Not configured (run 'aws configure')" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠ AWS CLI: Not installed (optional, needed for AWS deployment)" -ForegroundColor Yellow
}

if (Get-Command terraform -ErrorAction SilentlyContinue) {
    $tfVersion = terraform --version | Select-Object -First 1
    Write-Host "  ✓ Terraform: $tfVersion" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Terraform: Not installed (optional, needed for AWS deployment)" -ForegroundColor Yellow
}

# =================================================================
# Summary
# =================================================================
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $psqlFound) {
    Write-Host "1. Install PostgreSQL:" -ForegroundColor Yellow
    Write-Host "   → Right-click PowerShell → Run as Administrator" -ForegroundColor Cyan
    Write-Host "   → Run: install-and-setup-local.ps1" -ForegroundColor Cyan
    Write-Host ""
}

Write-Host "2. Configure your credentials:" -ForegroundColor Yellow
Write-Host "   → Edit .env.local" -ForegroundColor Cyan
Write-Host "   → Add your Alpaca API keys" -ForegroundColor Cyan
Write-Host ""

Write-Host "3. Start the application:" -ForegroundColor Yellow
Write-Host "   → Run: npm start" -ForegroundColor Cyan
Write-Host "   → Access: http://localhost:3001" -ForegroundColor Cyan
Write-Host ""

Write-Host "4. Review documentation:" -ForegroundColor Yellow
Write-Host "   → Read: LOCAL_SETUP_STATUS.md (for local development)" -ForegroundColor Cyan
Write-Host "   → Read: AWS_SETUP_CHECKLIST.md (for AWS deployment)" -ForegroundColor Cyan
Write-Host ""

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "For help, run this script anytime: .\verify-setup.ps1" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan

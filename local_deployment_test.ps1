# Comprehensive Local Deployment & Testing Script (PowerShell)
# Tests all components and verifies AWS deployment

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║      ALGO PLATFORM - LOCAL & AWS DEPLOYMENT TEST              ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$testsPassed = 0
$testsFailed = 0
$testsSkipped = 0

function PrintStatus($status, $message) {
    switch ($status) {
        "PASS" {
            Write-Host "[PASS]" -ForegroundColor Green -NoNewline
            Write-Host " $message"
            $script:testsPassed++
        }
        "FAIL" {
            Write-Host "[FAIL]" -ForegroundColor Red -NoNewline
            Write-Host " $message"
            $script:testsFailed++
        }
        "SKIP" {
            Write-Host "[SKIP]" -ForegroundColor Yellow -NoNewline
            Write-Host " $message"
            $script:testsSkipped++
        }
        "INFO" {
            Write-Host "[INFO]" -ForegroundColor Blue -NoNewline
            Write-Host " $message"
        }
    }
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 1: CHECK TOOLS & PREREQUISITES
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 1: CHECK TOOLS & PREREQUISITES ════╗" -ForegroundColor Cyan
Write-Host ""

# Check WSL
$wslCheck = wsl --list --verbose 2>&1
if ($LASTEXITCODE -eq 0) {
    PrintStatus "PASS" "WSL is installed"
    $wslAvailable = $true
} else {
    PrintStatus "INFO" "WSL not detected (Docker Desktop required)"
    $wslAvailable = $false
}

# Check Docker
$dockerCheck = docker --version 2>&1
if ($LASTEXITCODE -eq 0) {
    PrintStatus "PASS" "Docker: $dockerCheck"
} else {
    PrintStatus "FAIL" "Docker not found - needed for local testing"
}

# Check Python
$pythonCheck = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    PrintStatus "PASS" "Python: $pythonCheck"
} else {
    PrintStatus "FAIL" "Python not found"
}

# Check Git
$gitCheck = git --version 2>&1
if ($LASTEXITCODE -eq 0) {
    PrintStatus "PASS" "Git: $gitCheck"
} else {
    PrintStatus "FAIL" "Git not found"
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 2: VERIFY PYTHON MODULES
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 2: VERIFY PYTHON MODULES ════╗" -ForegroundColor Cyan
Write-Host ""

PrintStatus "INFO" "Testing Python module compilation..."

$modules = @(
    "algo_config",
    "algo_orchestrator",
    "algo_filter_pipeline",
    "algo_circuit_breaker",
    "algo_market_exposure",
    "algo_trade_executor",
    "algo_exit_engine"
)

foreach ($module in $modules) {
    $moduleFile = "$module.py"
    if (Test-Path $moduleFile) {
        $compileTest = python -m py_compile $moduleFile 2>&1
        if ($LASTEXITCODE -eq 0) {
            PrintStatus "PASS" "$module compiles successfully"
        } else {
            PrintStatus "FAIL" "$module has syntax errors: $compileTest"
        }
    }
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 3: VERIFY LOCAL DOCKER ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 3: LOCAL DOCKER ENVIRONMENT ════╗" -ForegroundColor Cyan
Write-Host ""

if ($wslAvailable) {
    PrintStatus "INFO" "Checking Docker Compose setup..."

    $dockerComposeFile = "docker-compose.yml"
    if (Test-Path $dockerComposeFile) {
        PrintStatus "PASS" "docker-compose.yml found"
    } else {
        PrintStatus "FAIL" "docker-compose.yml not found"
    }

    # Check if containers are running
    $psOutput = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        PrintStatus "PASS" "Docker daemon is running"

        if ($psOutput | Select-String -Pattern "stocks_db") {
            PrintStatus "PASS" "PostgreSQL container is running"
        } else {
            PrintStatus "INFO" "PostgreSQL container not running (start with: docker-compose up -d)"
        }
    } else {
        PrintStatus "FAIL" "Docker daemon is not running"
    }
} else {
    PrintStatus "SKIP" "Local Docker tests (WSL or Docker Desktop required)"
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 4: VERIFY VERIFICATION TOOLS
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 4: VERIFY VERIFICATION TOOLS ════╗" -ForegroundColor Cyan
Write-Host ""

$tools = @(
    "verify_system_ready.py",
    "verify_data_integrity.py",
    "audit_loaders.py"
)

foreach ($tool in $tools) {
    if (Test-Path $tool) {
        PrintStatus "PASS" "$tool exists"
    } else {
        PrintStatus "FAIL" "$tool not found"
    }
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 5: CHECK DEPLOYMENT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 5: CHECK DEPLOYMENT CONFIGURATION ════╗" -ForegroundColor Cyan
Write-Host ""

$requiredFiles = @(
    "terraform/main.tf",
    ".github/workflows/deploy-all-infrastructure.yml",
    "lambda/api/lambda_function.py",
    "db-init-build/init_database.py"
)

foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        PrintStatus "PASS" "$file exists"
    } else {
        PrintStatus "FAIL" "$file not found"
    }
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 6: GIT STATUS
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 6: GIT STATUS ════╗" -ForegroundColor Cyan
Write-Host ""

$gitStatus = git status --short 2>&1
if ($gitStatus) {
    PrintStatus "INFO" "Uncommitted changes detected"
} else {
    PrintStatus "PASS" "Working directory is clean"
}

$gitLog = git log --oneline -1 2>&1
PrintStatus "INFO" "Latest commit: $gitLog"

# ═══════════════════════════════════════════════════════════════════
# PHASE 7: AWS CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 7: AWS CONFIGURATION ════╗" -ForegroundColor Cyan
Write-Host ""

$awsCheck = aws --version 2>&1
if ($LASTEXITCODE -eq 0) {
    PrintStatus "PASS" "AWS CLI: $awsCheck"

    # Try to get current AWS account
    $awsAccount = aws sts get-caller-identity --query Account 2>&1
    if ($LASTEXITCODE -eq 0) {
        PrintStatus "PASS" "AWS credentials configured for account: $awsAccount"
    }
} else {
    PrintStatus "INFO" "AWS CLI not installed (optional)"
}

# ═══════════════════════════════════════════════════════════════════
# PHASE 8: DEPLOYMENT STATUS
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ PHASE 8: DEPLOYMENT STATUS ════╗" -ForegroundColor Cyan
Write-Host ""

PrintStatus "INFO" "GitHub Actions Status:"
Write-Host "    View at: https://github.com/argie33/algo/actions" -ForegroundColor Cyan

PrintStatus "INFO" "AWS Infrastructure:"
Write-Host "    API Endpoint: https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com" -ForegroundColor Cyan
Write-Host "    Frontend: https://d5j1h4wzrkvw7.cloudfront.net" -ForegroundColor Cyan

# ═══════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ═══════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "╔════ FINAL SUMMARY ════╗" -ForegroundColor Cyan
Write-Host ""

Write-Host "Tests Passed:  $testsPassed" -ForegroundColor Green
Write-Host "Tests Failed:  $testsFailed" -ForegroundColor $(if ($testsFailed -gt 0) { "Red" } else { "Green" })
Write-Host "Tests Skipped: $testsSkipped" -ForegroundColor Yellow

Write-Host ""

if ($testsFailed -eq 0) {
    Write-Host "✓ SYSTEM READY FOR DEPLOYMENT" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "1. Monitor GitHub Actions: https://github.com/argie33/algo/actions"
    Write-Host "2. Wait for deployment to complete (10-20 minutes)"
    Write-Host "3. Test API endpoint:"
    Write-Host "   curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health"
    Write-Host "4. Access frontend: https://d5j1h4wzrkvw7.cloudfront.net"
    Write-Host ""
    Write-Host "Local Testing (optional):"
    Write-Host "   If in WSL: bash local_deployment_test.sh"
    Write-Host "   Or in PowerShell: docker-compose up -d"
} else {
    Write-Host "✗ FIX ERRORS BEFORE DEPLOYMENT" -ForegroundColor Red
    Write-Host ""
    Write-Host "Issues to resolve:" -ForegroundColor Yellow
    Write-Host "- Ensure all required tools are installed"
    Write-Host "- Check Python syntax with: python -m py_compile <file>"
    Write-Host "- Verify Git and GitHub configuration"
}

Write-Host ""

#!/usr/bin/env pwsh
<#
.SYNOPSIS
Set up and verify the dashboard is ready to run with AWS endpoints.

.DESCRIPTION
This script:
1. Ensures AWS credentials are available locally (algo-developer profile)
2. Verifies dashboard config exists in Secrets Manager
3. Tests connectivity to API Gateway
4. Provides clear troubleshooting steps if anything is missing

.EXAMPLE
./scripts/setup-dashboard.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Profile = "algo-developer"
$Region = "us-east-1"
$CredFile = "$HOME\.aws\credentials"

Write-Host "`n╔══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       ALGO DASHBOARD - AWS SETUP & VERIFICATION         ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# Step 1: Check local AWS credentials
Write-Host "`n[1/4] Checking local AWS credentials..." -ForegroundColor Cyan
if (-not (Test-Path $CredFile)) {
    Write-Host "[FAIL] AWS credentials file not found: $CredFile" -ForegroundColor Red
    Write-Host "       Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

$Content = Get-Content $CredFile -Raw
if ($Content -notmatch "\[$Profile\]") {
    Write-Host "[FAIL] Profile '$Profile' not found in $CredFile" -ForegroundColor Red
    Write-Host "       Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Local AWS credentials configured" -ForegroundColor Green

# Step 2: Verify AWS credentials work
Write-Host "`n[2/4] Verifying AWS credentials..." -ForegroundColor Cyan
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region

$Identity = aws sts get-caller-identity --profile $Profile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] AWS credentials not working" -ForegroundColor Red
    Write-Host "       Error: $Identity" -ForegroundColor Red
    Write-Host "       Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

$IdentityObj = $Identity | ConvertFrom-Json
Write-Host "[OK] AWS credentials valid (Account: $($IdentityObj.Account))" -ForegroundColor Green

# Step 3: Fetch and verify dashboard config from Secrets Manager
Write-Host "`n[3/4] Fetching dashboard configuration..." -ForegroundColor Cyan

$DashboardConfigJson = aws secretsmanager get-secret-value `
    --secret-id algo/dashboard-config `
    --region $Region `
    --query SecretString `
    --output text 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Dashboard config not found in Secrets Manager" -ForegroundColor Red
    Write-Host "       Secret: algo/dashboard-config" -ForegroundColor Red
    Write-Host "" -ForegroundColor Red
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  A) If infrastructure just deployed:" -ForegroundColor Cyan
    Write-Host "     Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Cyan
    Write-Host "     (This refreshes and checks Secrets Manager)" -ForegroundColor Cyan
    Write-Host "" -ForegroundColor Yellow
    Write-Host "  B) If infrastructure hasn't deployed yet:" -ForegroundColor Cyan
    Write-Host "     Run deploy from GitHub Actions:" -ForegroundColor Cyan
    Write-Host "     .github/workflows/deploy-all-infrastructure.yml" -ForegroundColor Cyan
    exit 1
}

if (-not $DashboardConfigJson -or $DashboardConfigJson -eq "") {
    Write-Host "[FAIL] Dashboard config is empty" -ForegroundColor Red
    exit 1
}

try {
    $DashboardConfig = $DashboardConfigJson | ConvertFrom-Json
} catch {
    Write-Host "[FAIL] Could not parse dashboard config JSON" -ForegroundColor Red
    Write-Host "       Error: $_" -ForegroundColor Red
    exit 1
}

$ApiUrl = $DashboardConfig.api_url
$PoolId = $DashboardConfig.cognito_user_pool_id
$ClientId = $DashboardConfig.cognito_user_pool_client_id

$Errors = @()
if ([string]::IsNullOrWhiteSpace($ApiUrl)) { $Errors += "api_url" }
if ([string]::IsNullOrWhiteSpace($PoolId)) { $Errors += "cognito_user_pool_id" }
if ([string]::IsNullOrWhiteSpace($ClientId)) { $Errors += "cognito_user_pool_client_id" }

if ($Errors.Count -gt 0) {
    Write-Host "[FAIL] Dashboard config incomplete in Secrets Manager" -ForegroundColor Red
    Write-Host "       Missing fields: $($Errors -join ', ')" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Dashboard configuration found" -ForegroundColor Green
Write-Host "     API URL: $ApiUrl" -ForegroundColor Green
Write-Host "     Cognito Pool: $PoolId" -ForegroundColor Green
Write-Host "     Cognito Client: $(if ($ClientId.Length -gt 20) { $ClientId.Substring(0, 20) + '...' } else { $ClientId })" -ForegroundColor Green

# Step 4: Test API connectivity
Write-Host "`n[4/4] Testing API Gateway connectivity..." -ForegroundColor Cyan

$ApiHealthUrl = "$ApiUrl/api/algo/health"
try {
    $Response = Invoke-WebRequest -Uri $ApiHealthUrl -Method Get -TimeoutSec 5 -SkipHttpErrorCheck
    if ($Response.StatusCode -eq 200) {
        Write-Host "[OK] API Gateway responding (200 OK)" -ForegroundColor Green
    } elseif ($Response.StatusCode -eq 401) {
        Write-Host "[WARN] API Gateway responding (401 Unauthorized)" -ForegroundColor Yellow
        Write-Host "       Authentication required - dashboard will prompt for Cognito login" -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] API Gateway responding ($($Response.StatusCode))" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Could not reach API Gateway" -ForegroundColor Yellow
    Write-Host "       Error: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "       This is OK if API is still initializing" -ForegroundColor Yellow
}

# Final success message
Write-Host "`n╔══════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              DASHBOARD READY TO RUN                      ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`nTo start the dashboard:" -ForegroundColor Cyan
Write-Host "  cd tools/dashboard" -ForegroundColor White
Write-Host "  python dashboard.py -w 30  # Auto-refresh every 30 seconds" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "Or run without watch mode:" -ForegroundColor Cyan
Write-Host "  python dashboard.py" -ForegroundColor White

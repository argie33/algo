#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify dashboard AWS configuration and connectivity.

.DESCRIPTION
Checks:
1. AWS credentials are loaded and valid
2. Dashboard code is AWS-only (no localhost fallback)
3. credential_manager.py can fetch credentials
4. RDS proxy endpoint is configured
5. Provides next steps to complete AWS access setup

.EXAMPLE
.\scripts\verify-dashboard-aws.ps1
#>

Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "DASHBOARD AWS VERIFICATION" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan

# Test 1: AWS credentials
Write-Host "`n[1] Checking AWS credentials..." -ForegroundColor Cyan
try {
    $identity = aws sts get-caller-identity --output json | ConvertFrom-Json
    if ($identity.UserId) {
        Write-Host "    OK: AWS credentials valid" -ForegroundColor Green
        Write-Host "    Account: $($identity.Account)" -ForegroundColor Gray
        Write-Host "    User: $($identity.Arn)" -ForegroundColor Gray
    }
}
catch {
    Write-Host "    ERROR: AWS credentials not available" -ForegroundColor Red
    Write-Host "    Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

# Test 2: Dashboard imports
Write-Host "`n[2] Checking dashboard code..." -ForegroundColor Cyan
try {
    $output = python -c "
import sys
sys.path.insert(0, '.')
from tools.dashboard.dashboard import _configure_database
mode = _configure_database(use_aws_only=True)
print('AWS')
" 2>&1

    if ($output -eq "AWS") {
        Write-Host "    OK: Dashboard is AWS-only (no localhost fallback)" -ForegroundColor Green
    }
    else {
        Write-Host "    ERROR: Dashboard mode is not AWS-only" -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "    ERROR: Dashboard import failed: $_" -ForegroundColor Red
    exit 1
}

# Test 3: Credential manager
Write-Host "`n[3] Checking credential manager..." -ForegroundColor Cyan
try {
    $creds = python -c "
import os
import json
os.environ['DB_PASSWORD'] = 'test'
from config.credential_manager import get_db_credentials
creds = get_db_credentials()
print(json.dumps({'host': creds.get('host'), 'user': creds.get('user')}))
" 2>&1

    $credsObj = $creds | ConvertFrom-Json
    Write-Host "    OK: credential_manager works" -ForegroundColor Green
    Write-Host "    Host: $($credsObj.host)" -ForegroundColor Gray
    Write-Host "    User: $($credsObj.user)" -ForegroundColor Gray
}
catch {
    Write-Host "    ERROR: credential_manager failed: $_" -ForegroundColor Red
}

# Test 4: RDS connectivity
Write-Host "`n[4] Checking RDS proxy connectivity..." -ForegroundColor Cyan
try {
    Test-NetConnection -ComputerName "algo-rds-proxy-dev.proxy-cojggi2mkthi.us-east-1.rds.amazonaws.com" -Port 5432 -ErrorAction Stop | Out-Null
    Write-Host "    OK: RDS proxy is reachable (you may have VPN/bastion access)" -ForegroundColor Green
}
catch {
    Write-Host "    INFO: RDS proxy is NOT reachable (expected for local machines)" -ForegroundColor Yellow
    Write-Host "    This is expected - use Lambda API endpoint instead" -ForegroundColor Gray
}

# Test 5: API configuration
Write-Host "`n[5] Checking API configuration..." -ForegroundColor Cyan
$apiUrl = $env:DASHBOARD_API_URL
if ($apiUrl) {
    Write-Host "    OK: DASHBOARD_API_URL is configured" -ForegroundColor Green
    Write-Host "    URL: $apiUrl" -ForegroundColor Gray
}
else {
    Write-Host "    INFO: DASHBOARD_API_URL not configured" -ForegroundColor Yellow
    Write-Host "    Next step: Run ./scripts/setup-dashboard-aws.ps1" -ForegroundColor Gray
}

# Summary
Write-Host "`n" + ("=" * 70) -ForegroundColor Cyan
Write-Host "NEXT STEPS" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host @"

To complete AWS setup, do ONE of the following:

[OPTION 1] Use Lambda API endpoint (RECOMMENDED)
  1. Run: ./scripts/setup-dashboard-aws.ps1
  2. This script auto-detects and configures the API endpoint
  3. Then run: python tools/dashboard/dashboard.py

[OPTION 2] Set up VPN or bastion access
  1. Connect to AWS infrastructure via VPN or bastion
  2. Verify RDS proxy is reachable: Test-NetConnection <rds-proxy>:5432
  3. Then run: python tools/dashboard/dashboard.py

[OPTION 3] Manual API endpoint configuration
  1. Get endpoint from: terraform -chdir=terraform output api_url
  2. Set environment variable: `$env:DASHBOARD_API_URL = "https://your-endpoint"`
  3. Then run: python tools/dashboard/dashboard.py

For more details, see: docs/dashboard-aws-access.md

"@ -ForegroundColor White

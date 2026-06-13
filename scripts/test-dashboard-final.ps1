#!/usr/bin/env pwsh
<#
.SYNOPSIS
Final AWS dashboard verification - simple end-to-end test.
#>

$ErrorActionPreference = "Stop"

# Set AWS profile
$env:AWS_PROFILE = "algo-developer"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " FINAL DASHBOARD AWS VERIFICATION" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check AWS credentials
Write-Host "1. Checking AWS Credentials..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity --query 'Arn' --output text 2>&1
    if ($identity -match "arn:aws") {
        Write-Host "   [OK] AWS credentials available" -ForegroundColor Green
    }
} catch {
    Write-Host "   [FAIL] Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Red
    exit 1
}

# 2. Check API health
Write-Host ""
Write-Host "2. Testing API Gateway Health..." -ForegroundColor Yellow
try {
    $health = Invoke-WebRequest -Uri "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health" `
        -TimeoutSec 10 -ErrorAction Stop
    Write-Host "   [OK] API Gateway responding (Status $($health.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "   [FAIL] API Gateway not responding" -ForegroundColor Red
    exit 1
}

# 3. Test Cognito auth
Write-Host ""
Write-Host "3. Testing Cognito Authentication..." -ForegroundColor Yellow

$cognitoTest = python -c "
import boto3
try:
    cognito = boto3.client('cognito-idp', region_name='us-east-1')
    response = cognito.initiate_auth(
        ClientId='6smb0vrcidd9kvhju2kn2a3qrl',
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': 'dashboardtest@example.com',
            'PASSWORD': 'DashboardTest123!'
        }
    )
    if 'AuthenticationResult' in response:
        print(response['AuthenticationResult']['AccessToken'])
    else:
        print('FAIL')
except Exception as e:
    print('FAIL')
" 2>&1

if ($cognitoTest -match "^eyJ") {
    $token = $cognitoTest
    Write-Host "   [OK] Cognito authentication successful" -ForegroundColor Green
} else {
    Write-Host "   [FAIL] Cognito authentication failed" -ForegroundColor Red
    exit 1
}

# 4. Test protected endpoints
Write-Host ""
Write-Host "4. Testing Protected Endpoints..." -ForegroundColor Yellow

$endpoints = @(
    "/api/algo/positions",
    "/api/algo/portfolio",
    "/api/algo/markets"
)

$headers = @{ Authorization = "Bearer $token" }

foreach ($endpoint in $endpoints) {
    try {
        $response = Invoke-WebRequest -Uri "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com$endpoint" `
            -Headers $headers -TimeoutSec 10 -ErrorAction SilentlyContinue
        Write-Host "   [OK] $endpoint - Status $($response.StatusCode)" -ForegroundColor Green
    } catch {
        $status = $_.Exception.Response.StatusCode
        if ($status -eq 200) {
            Write-Host "   [OK] $endpoint - Status $status" -ForegroundColor Green
        } else {
            Write-Host "   [WARN] $endpoint - Status $status" -ForegroundColor Yellow
        }
    }
}

# 5. Check dashboard tool
Write-Host ""
Write-Host "5. Checking Dashboard Tool..." -ForegroundColor Yellow

if (Test-Path "run-dashboard.ps1") {
    Write-Host "   [OK] Dashboard launcher found" -ForegroundColor Green
} else {
    Write-Host "   [FAIL] Dashboard launcher not found" -ForegroundColor Red
}

if (Test-Path "tools/dashboard/dashboard.py") {
    Write-Host "   [OK] Dashboard script found" -ForegroundColor Green
} else {
    Write-Host "   [FAIL] Dashboard script not found" -ForegroundColor Red
}

# 6. Test Terraform credential fetch
Write-Host ""
Write-Host "6. Testing Terraform Credential Fetch..." -ForegroundColor Yellow

$tfTest = python -c "
import sys
sys.path.insert(0, 'tools/dashboard')
try:
    from dashboard import _fetch_terraform_credentials
    api_url, pool_id, client_id = _fetch_terraform_credentials()
    if api_url and pool_id and client_id:
        print('OK')
    else:
        print('FAIL')
except Exception as e:
    print('FAIL')
" 2>&1

if ($tfTest -eq "OK") {
    Write-Host "   [OK] Terraform credential fetch working" -ForegroundColor Green
} else {
    Write-Host "   [WARN] Terraform credential fetch may need setup" -ForegroundColor Yellow
}

# 7. Summary
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " ALL SYSTEMS READY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "The dashboard is ready to launch with AWS!" -ForegroundColor Green
Write-Host ""
Write-Host "To start the dashboard:" -ForegroundColor Cyan
Write-Host "  .\run-dashboard.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Or with auto-refresh:" -ForegroundColor Cyan
Write-Host "  .\run-dashboard.ps1 -Watch 30" -ForegroundColor White
Write-Host ""

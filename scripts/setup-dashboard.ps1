#!/usr/bin/env pwsh
<#
.SYNOPSIS
Setup Algo Dashboard for AWS mode with Cognito authentication

.DESCRIPTION
This script:
1. Retrieves Terraform outputs (API URL, Cognito Pool ID, Client ID)
2. Optionally creates/resets a test Cognito user
3. Sets environment variables for dashboard
4. Starts the dashboard in watch mode

.PARAMETER Interactive
If true, prompts for Cognito username/password to save for future runs
#>

param(
    [switch]$Interactive = $false,
    [string]$Username = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

Write-Host "`n=== Algo Dashboard Setup (AWS Mode) ===" -ForegroundColor Cyan

# Step 1: Verify AWS credentials
Write-Host "`n[1/4] Verifying AWS credentials..." -ForegroundColor Cyan
try {
    $identity = & aws sts get-caller-identity --query 'Arn' --output text 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ AWS credentials valid: $identity" -ForegroundColor Green
    } else {
        throw "AWS credentials not available"
    }
} catch {
    Write-Host "  ✗ AWS credentials required. Run:" -ForegroundColor Red
    Write-Host "    scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

# Step 2: Get Terraform outputs
Write-Host "`n[2/4] Fetching Terraform configuration..." -ForegroundColor Cyan
$env:AWS_PROFILE = 'algo-developer'
$terraformDir = Join-Path $PSScriptRoot "..\terraform"

if (!(Test-Path $terraformDir)) {
    Write-Host "  ✗ terraform/ directory not found" -ForegroundColor Red
    exit 1
}

$outputs = @{}
try {
    Push-Location $terraformDir
    foreach ($key in @('api_url', 'cognito_user_pool_id', 'cognito_user_pool_client_id')) {
        $value = & terraform output -raw $key 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to get $key from terraform output"
        }
        $outputs[$key] = $value
    }
    Pop-Location
} catch {
    Write-Host "  ✗ Terraform init failed: $_" -ForegroundColor Red
    Write-Host "    Try: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

$apiUrl = $outputs['api_url']
$poolId = $outputs['cognito_user_pool_id']
$clientId = $outputs['cognito_user_pool_client_id']

Write-Host "  ✓ Terraform outputs retrieved:" -ForegroundColor Green
Write-Host "    API: $apiUrl" -ForegroundColor DarkGray
Write-Host "    Pool: $poolId" -ForegroundColor DarkGray
Write-Host "    Client: $clientId" -ForegroundColor DarkGray

# Step 3: Setup/validate Cognito user
Write-Host "`n[3/4] Cognito authentication setup..." -ForegroundColor Cyan
$tokenFile = Join-Path $env:USERPROFILE ".algo\cognito_token.json"
$hasCachedToken = Test-Path $tokenFile

if ($Interactive -or (!$hasCachedToken -and !$Username -and !$Password)) {
    Write-Host "  No cached credentials found." -ForegroundColor Yellow
    $response = Read-Host "  Create/reset test user? (y/n)"
    if ($response -eq "y") {
        Write-Host "  Running: gh workflow run reset-cognito-test-user.yml" -ForegroundColor Cyan
        & gh workflow run reset-cognito-test-user.yml --ref main
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Workflow triggered. Check GitHub Actions for test user details." -ForegroundColor Green
            $Username = Read-Host "  Enter Cognito email (test user)"
            $securePass = Read-Host "  Enter Cognito password" -AsSecureString
            $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($securePass))
        }
    } else {
        Write-Host "  Using environment variables or cached token..." -ForegroundColor Cyan
    }
} elseif ($hasCachedToken) {
    Write-Host "  ✓ Cached credentials found at $tokenFile" -ForegroundColor Green
}

# Step 4: Set environment variables
Write-Host "`n[4/4] Setting environment variables..." -ForegroundColor Cyan
$env:DASHBOARD_API_URL = $apiUrl
$env:COGNITO_USER_POOL_ID = $poolId
$env:COGNITO_CLIENT_ID = $clientId

if ($Username -and $Password) {
    $env:COGNITO_USERNAME = $Username
    $env:COGNITO_PASSWORD = $Password
    Write-Host "  ✓ Username/password set" -ForegroundColor Green
}

Write-Host ""
Write-Host "Environment configured:" -ForegroundColor Green
Write-Host "  DASHBOARD_API_URL = $apiUrl" -ForegroundColor DarkGray
Write-Host "  COGNITO_USER_POOL_ID = $poolId" -ForegroundColor DarkGray
Write-Host "  COGNITO_CLIENT_ID = $clientId" -ForegroundColor DarkGray
if ($env:COGNITO_USERNAME) {
    Write-Host "  COGNITO_USERNAME = $($env:COGNITO_USERNAME)" -ForegroundColor DarkGray
}

# Step 5: Start dashboard
Write-Host "`nStarting dashboard..." -ForegroundColor Cyan
Write-Host "  Press 'q' or Ctrl+C to exit" -ForegroundColor DarkGray
Write-Host ""

$dashboardPath = Join-Path $PSScriptRoot "..\tools\dashboard\dashboard.py"
& python $dashboardPath -w 30

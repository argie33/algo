#!/usr/bin/env pwsh
<#
.SYNOPSIS
Run the Algo terminal dashboard with automatic Terraform credential fetching.

.DESCRIPTION
This script ensures AWS credentials are available and runs the dashboard tool.
It automatically fetches API URL and Cognito credentials from Terraform,
so no manual setup is required.

.EXAMPLE
.\run-dashboard.ps1
.\run-dashboard.ps1 -Watch 60
.\run-dashboard.ps1 --local
#>

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$DashboardArgs
)

$ErrorActionPreference = "Stop"

# Ensure we're in the repo root
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "=== Algo Terminal Dashboard ===" -ForegroundColor Cyan
Write-Host ""

# Check if AWS credentials are available
Write-Host "Checking AWS credentials..." -ForegroundColor Gray
$awsProfile = $env:AWS_PROFILE
if (-not $awsProfile) {
    $env:AWS_PROFILE = "algo-developer"
    Write-Host "Set AWS_PROFILE to: algo-developer" -ForegroundColor Yellow
}

# Verify credentials exist
try {
    $creds = Get-Content "$env:USERPROFILE\.aws\credentials" -ErrorAction Stop
    if ($creds -match "algo-developer") {
        Write-Host "Found algo-developer credentials" -ForegroundColor Green
    } else {
        Write-Host "WARNING: algo-developer credentials not found in ~/.aws/credentials" -ForegroundColor Yellow
        Write-Host "Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    }
} catch {
    Write-Host "WARNING: Could not read AWS credentials file" -ForegroundColor Yellow
    Write-Host "Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fetching dashboard credentials..." -ForegroundColor Cyan

$apiUrl = $null
$poolId = $null
$clientId = $null

# Try Secrets Manager first (most reliable, works without local Terraform state)
try {
    $secretJson = aws secretsmanager get-secret-value `
        --secret-id algo/dashboard-config `
        --region us-east-1 `
        --query SecretString `
        --output text 2>&1
    if ($LASTEXITCODE -eq 0 -and $secretJson) {
        $secret = $secretJson | ConvertFrom-Json
        $apiUrl   = $secret.api_url
        $poolId   = $secret.cognito_user_pool_id
        $clientId = $secret.cognito_user_pool_client_id
        if ($apiUrl) { Write-Host "Credentials from Secrets Manager" -ForegroundColor Green }
    }
} catch {
    # Secrets Manager unavailable, will try Terraform
}

# Fall back to Terraform outputs if Secrets Manager unavailable
if (-not $apiUrl) {
    Write-Host "Secrets Manager unavailable -- trying Terraform..." -ForegroundColor Yellow
    $tfDir = Join-Path $repoRoot "terraform"
    if (Test-Path $tfDir) {
        Push-Location $tfDir
        try {
            $apiUrl   = & terraform output -raw api_url 2>$null
            $poolId   = & terraform output -raw cognito_user_pool_id 2>$null
            $clientId = & terraform output -raw cognito_user_pool_client_id 2>$null
            if ($apiUrl) { Write-Host "Credentials from Terraform" -ForegroundColor Green }
        } catch {
            # Terraform output failed, continue with empty values
        }
        Pop-Location
    }
}

if (-not $apiUrl) {
    Write-Host "[ERROR] Could not retrieve dashboard credentials." -ForegroundColor Red
    Write-Host ""
    Write-Host "To fix this, ensure:" -ForegroundColor Yellow
    Write-Host "  1. AWS credentials are valid:  scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    Write-Host "  2. Terraform has been applied: cd terraform; terraform apply" -ForegroundColor Yellow
    Write-Host "  3. algo/dashboard-config secret exists in Secrets Manager" -ForegroundColor Yellow
    exit 1
}

$env:DASHBOARD_API_URL   = $apiUrl
$env:COGNITO_USER_POOL_ID = $poolId
$env:COGNITO_CLIENT_ID   = $clientId
Write-Host "Dashboard credentials set" -ForegroundColor Green
Write-Host "  API URL: $apiUrl" -ForegroundColor Gray

Write-Host ""
Write-Host "Running dashboard..." -ForegroundColor Cyan
Write-Host "Press 'q' or Ctrl+C to exit" -ForegroundColor Gray
Write-Host ""

# Run dashboard with passed arguments
& python tools/dashboard/dashboard.py @DashboardArgs

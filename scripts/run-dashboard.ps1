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
Write-Host "Fetching Terraform outputs..." -ForegroundColor Cyan

# Get Terraform outputs
cd terraform
try {
    $apiUrl = & terraform output -raw api_url 2>$null
    $poolId = & terraform output -raw cognito_user_pool_id 2>$null
    $clientId = & terraform output -raw cognito_user_pool_client_id 2>$null

    if ($apiUrl -and $poolId -and $clientId) {
        $env:DASHBOARD_API_URL = $apiUrl
        $env:COGNITO_USER_POOL_ID = $poolId
        $env:COGNITO_CLIENT_ID = $clientId
        Write-Host "Terraform outputs loaded successfully" -ForegroundColor Green
        Write-Host "  API URL: $apiUrl" -ForegroundColor Gray
    } else {
        Write-Host "WARNING: Could not fetch all Terraform outputs" -ForegroundColor Yellow
        Write-Host "Run: terraform init && terraform apply" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "ERROR: Failed to fetch Terraform outputs: $_" -ForegroundColor Red
    Write-Host "Make sure you're in the terraform directory and terraform is initialized" -ForegroundColor Yellow
    exit 1
} finally {
    cd ..
}

Write-Host ""
Write-Host "Running dashboard..." -ForegroundColor Cyan
Write-Host "Press 'q' or Ctrl+C to exit" -ForegroundColor Gray
Write-Host ""

# Run dashboard with passed arguments
python "tools/dashboard/dashboard.py" @DashboardArgs

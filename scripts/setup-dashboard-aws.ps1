#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Fetch AWS credentials from Terraform and run dashboard in AWS mode.

.DESCRIPTION
    Automatically sets up environment variables by fetching credentials from Terraform,
    refreshing AWS credentials if needed, then running the dashboard.

.PARAMETER Watch
    Enable watch mode (auto-refresh). Pass a number for interval in seconds (5-600).

.PARAMETER Local
    Use local mode (localhost:3001) instead of AWS.

.PARAMETER Compact
    Use compact positions table (omit T1 and Sector columns).

.EXAMPLE
    .\setup-dashboard-aws.ps1                    # Run once
    .\setup-dashboard-aws.ps1 -Watch             # Watch mode (30s refresh)
    .\setup-dashboard-aws.ps1 -Watch 60          # Watch mode (60s refresh)
    .\setup-dashboard-aws.ps1 -Local             # Use local API
    .\setup-dashboard-aws.ps1 -Compact           # Compact mode
#>

param(
    [switch]$Watch,
    [int]$WatchInterval = 30,
    [switch]$Local,
    [switch]$Compact
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$terraformDir = Join-Path $repoRoot "terraform"
$dashboardScript = Join-Path (Join-Path (Join-Path $repoRoot "tools") "dashboard") "dashboard.py"

if ($Local) {
    Write-Host "Using local mode (localhost:3001)" -ForegroundColor Yellow
    $dashboardArgs = @("--local")
    if ($Watch) {
        $dashboardArgs += "-w"
        if ($WatchInterval -ne 30) {
            $dashboardArgs += [string]$WatchInterval
        }
    }
    if ($Compact) {
        $dashboardArgs += "--compact"
    }
    & python $dashboardScript @dashboardArgs
    exit $LASTEXITCODE
}

# AWS Mode: Setup credentials and fetch from Terraform
Write-Host "Dashboard AWS Setup" -ForegroundColor Cyan
Write-Host ""

# Set AWS profile
$env:AWS_PROFILE = "algo-developer"
$env:AWS_DEFAULT_REGION = "us-east-1"

# Check if AWS credentials exist
$credentialsFile = "$HOME\.aws\credentials"
$credsExist = Test-Path $credentialsFile
if ($credsExist) {
    $credsContent = Get-Content $credentialsFile -Raw
    $credsExist = $credsContent -match "\[algo-developer\]"
}

if (-not $credsExist) {
    Write-Host "AWS credentials not found locally" -ForegroundColor Yellow
    Write-Host "Refreshing from Secrets Manager..." -ForegroundColor Cyan
    Write-Host ""

    & "$scriptDir\refresh-aws-credentials.ps1"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to refresh AWS credentials" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

# Fetch Terraform outputs
Write-Host "Fetching Terraform outputs..." -ForegroundColor Cyan
try {
    Push-Location $terraformDir

    # Initialize Terraform if needed
    if (-not (Test-Path ".terraform")) {
        Write-Host "Initializing Terraform..." -ForegroundColor Yellow
        & terraform init `
            -backend-config=bucket=stocks-terraform-state `
            -backend-config=key=stocks/terraform.tfstate `
            -backend-config=region=us-east-1 `
            -backend-config=encrypt=true

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Terraform init failed" -ForegroundColor Red
            exit 1
        }
    }

    # Get outputs as JSON
    $outputs = & terraform output -json 2>$null | ConvertFrom-Json

    $apiUrl = $outputs.api_url.value
    $poolId = $outputs.cognito_user_pool_id.value
    $clientId = $outputs.cognito_user_pool_client_id.value

    if (-not $apiUrl -or -not $poolId -or -not $clientId) {
        Write-Host "Failed to fetch required Terraform outputs" -ForegroundColor Red
        exit 1
    }

    Write-Host "Credentials fetched successfully" -ForegroundColor Green

}
finally {
    Pop-Location
}

# Set environment variables
Write-Host "Setting environment variables..." -ForegroundColor Cyan
$env:DASHBOARD_API_URL = $apiUrl
$env:COGNITO_USER_POOL_ID = $poolId
$env:COGNITO_CLIENT_ID = $clientId

Write-Host "Environment ready" -ForegroundColor Green
Write-Host ""

# Run dashboard
Write-Host "Starting dashboard..." -ForegroundColor Cyan
$dashboardArgs = @()

if ($Watch) {
    $dashboardArgs += "-w"
    if ($WatchInterval -ne 30) {
        $dashboardArgs += [string]$WatchInterval
    }
}

if ($Compact) {
    $dashboardArgs += "--compact"
}

& python $dashboardScript @dashboardArgs
exit $LASTEXITCODE

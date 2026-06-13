#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Fetch AWS credentials from Terraform and set environment variables for dashboard.

.DESCRIPTION
    Automatically initializes Terraform (if needed), fetches api_url, cognito_user_pool_id,
    and cognito_user_pool_client_id, then runs the dashboard in AWS mode.

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
$dashboardScript = Join-Path $repoRoot "tools" "dashboard" "dashboard.py"

Write-Host "🚀 Dashboard AWS Setup" -ForegroundColor Cyan

if ($Local) {
    Write-Host "Location: Using local mode (localhost:3001)" -ForegroundColor Yellow
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

# AWS Mode: Fetch credentials from Terraform
Write-Host "Setup: Fetching AWS credentials from Terraform..." -ForegroundColor Cyan

# Set AWS profile to use the algo-developer credentials
$env:AWS_PROFILE = "algo-developer"
$env:AWS_DEFAULT_REGION = "us-east-1"

# Verify AWS credentials are available
try {
    $identity = aws sts get-caller-identity 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Status: AWS credentials not available" -ForegroundColor Yellow
        Write-Host "" -ForegroundColor Yellow
        Write-Host "Action: Refreshing AWS credentials from Secrets Manager..." -ForegroundColor Cyan
        & "$scriptDir\refresh-aws-credentials.ps1"

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to refresh AWS credentials" -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "Status: AWS credentials available" -ForegroundColor Green
    }
}
catch {
    Write-Host "Status: AWS credentials not available" -ForegroundColor Yellow
    Write-Host "" -ForegroundColor Yellow
    Write-Host "Action: Refreshing AWS credentials from Secrets Manager..." -ForegroundColor Cyan
    & "$scriptDir\refresh-aws-credentials.ps1"

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to refresh AWS credentials" -ForegroundColor Red
        exit 1
    }
}
    catch {
    }
    return $null
}

# Show current configuration
if ($ShowConfig) {
    Write-Host "Current Dashboard Configuration:" -ForegroundColor Cyan
    Write-Host "  DASHBOARD_API_URL: $($env:DASHBOARD_API_URL)" -ForegroundColor Yellow
    Write-Host "  DB_HOST: $($env:DB_HOST)" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

# If endpoint not provided, try to auto-detect
if (-not $ApiEndpoint) {
    Write-Host "Detecting Lambda API endpoint..." -ForegroundColor Cyan

    $ApiEndpoint = Get-ApiEndpointFromTerraform
    if ($ApiEndpoint) {
        Write-Host "  Found via Terraform: $ApiEndpoint" -ForegroundColor Green
    }
    else {
        $ApiEndpoint = Get-ApiEndpointFromAws
        if ($ApiEndpoint) {
            Write-Host "  Found via AWS CLI: $ApiEndpoint" -ForegroundColor Green
        }
        else {
            Write-Host "  Could not auto-detect API endpoint" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Options:" -ForegroundColor Cyan
            Write-Host "  1. Run: terraform -chdir=terraform output api_url" -ForegroundColor Gray
            Write-Host "  2. Check AWS console: API Gateway > algo-api-dev" -ForegroundColor Gray
            Write-Host "  3. Then run: .\scripts\setup-dashboard-aws.ps1 -ApiEndpoint https://your-endpoint" -ForegroundColor Gray
            Write-Host ""
            exit 1
        }
    }
}

# Validate endpoint format
if ($ApiEndpoint -notmatch "^https://") {
    Write-Host "ERROR: Invalid API endpoint format" -ForegroundColor Red
    Write-Host "Must start with https://, got: $ApiEndpoint" -ForegroundColor Red
    exit 1
}

# Set environment variable
$env:DASHBOARD_API_URL = $ApiEndpoint

# Show confirmation
Write-Host ""
Write-Host "Dashboard AWS configuration:" -ForegroundColor Green
Write-Host "  DASHBOARD_API_URL = $ApiEndpoint" -ForegroundColor Yellow
Write-Host ""

# Test connectivity (optional)
Write-Host "Testing connectivity..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "$ApiEndpoint/health" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "  API is reachable: $($response.StatusCode)" -ForegroundColor Green
}
catch {
    Write-Host "  Warning: Could not reach API endpoint" -ForegroundColor Yellow
    Write-Host "    (This may be normal if API requires authentication)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "You can now run the dashboard:" -ForegroundColor Cyan
Write-Host "  python tools/dashboard/dashboard.py" -ForegroundColor Gray
Write-Host ""
Write-Host "To persist this configuration, add to your PowerShell profile:" -ForegroundColor Cyan
Write-Host '  $env:DASHBOARD_API_URL = "' + $ApiEndpoint + '"' -ForegroundColor Gray

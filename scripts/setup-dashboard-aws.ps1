#!/usr/bin/env pwsh
<#
.SYNOPSIS
Setup dashboard to access AWS data via Lambda API endpoint.

.DESCRIPTION
Configures DASHBOARD_API_URL environment variable to point to the algo-api-dev
Lambda API endpoint, allowing the dashboard to access AWS data from a local machine.

The Lambda API is deployed in VPC with access to RDS, so it can fetch data
and return it via HTTP, eliminating the need for direct RDS connectivity.

.EXAMPLE
.\scripts\setup-dashboard-aws.ps1
#>

param(
    [string]$ApiEndpoint,
    [switch]$ShowConfig,
    [switch]$ForceInteractive
)

# Try to get API endpoint from Terraform first
function Get-ApiEndpointFromTerraform {
    try {
        Push-Location terraform
        $output = terraform output api_url -raw 2>$null
        Pop-Location
        if ($output -and $output.StartsWith("https://")) {
            return $output
        }
    }
    catch {
        Pop-Location
    }
    return $null
}

# Try to get API endpoint from AWS CLI
function Get-ApiEndpointFromAws {
    try {
        $output = aws apigatewayv2 get-apis `
            --region us-east-1 `
            --query "Items[?contains(Name, 'algo-api')].ApiEndpoint" `
            --output text 2>$null

        if ($output -and $output.StartsWith("https://")) {
            return $output
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

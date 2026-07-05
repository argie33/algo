#!/usr/bin/env pwsh
<#
.SYNOPSIS
Trigger critical data loaders in AWS via Lambda/ECS

.DESCRIPTION
Invokes the trigger-loaders Lambda function to populate database tables:
  1. price_daily - Stock prices
  2. market_health_daily - VIX, breadth, trends
  3. market_exposure_daily - Market regime
  4. sector_ranking - Sector rankings

.EXAMPLE
./trigger-aws-loaders.ps1
#>

param(
    [string]$region = "us-east-1",
    [switch]$wait
)

$ErrorActionPreference = "Stop"

$loaders = @(
    "price_daily",
    "market_health_daily",
    "market_exposure_daily",
    "sector_ranking"
)

Write-Host "Triggering AWS Loaders via Lambda" -ForegroundColor Cyan
Write-Host "Region: $region" -ForegroundColor Gray
Write-Host ""

foreach ($loader in $loaders) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Invoking: $loader" -ForegroundColor Green

    $payload = @{
        loader_name = $loader
        task_count = 1
    } | ConvertTo-Json

    try {
        $response = aws lambda invoke `
            --function-name trigger-loaders `
            --payload $payload `
            --region $region `
            --cli-binary-format raw-in-base64-out `
            /tmp/response.json 2>&1

        Write-Host "  ✓ Triggered (check CloudWatch logs for progress)" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Error: $_" -ForegroundColor Red
        exit 1
    }

    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "All loaders triggered successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Monitor progress:" -ForegroundColor Cyan
Write-Host "  aws logs tail /aws/ecs/algo-cluster --follow --region $region" -ForegroundColor Gray
Write-Host ""
Write-Host "Check dashboard data:" -ForegroundColor Cyan
Write-Host "  python -m dashboard (after loaders complete)" -ForegroundColor Gray

#!/usr/bin/env pwsh
<#
.SYNOPSIS
Run critical data loaders to populate dashboard database

.DESCRIPTION
Triggers the following loaders in sequence:
  1. price_daily - SPY and stock prices (required for market exposure)
  2. market_health_daily - VIX, market breadth, trends
  3. market_exposure_daily - Market regime and exposure factors
  4. sector_ranking - Sector performance rankings

.EXAMPLE
./run-critical-loaders.ps1
#>

param(
    [int]$parallelism = 1,
    [switch]$verbose
)

$ErrorActionPreference = "Stop"
$loaders = @(
    @{ name = "price_daily"; module = "loaders.load_prices"; desc = "Stock prices (SPY, etc)" },
    @{ name = "market_health_daily"; module = "loaders.load_market_health_daily"; desc = "Market breadth, VIX, trends" },
    @{ name = "market_exposure_daily"; module = "loaders.load_market_exposure_daily"; desc = "Market regime & exposure" },
    @{ name = "sector_ranking"; module = "loaders.load_sector_ranking"; desc = "Sector performance rankings" }
)

Write-Host "="*70 -ForegroundColor Cyan
Write-Host "CRITICAL DATA LOADERS - Dashboard Data Population" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

# Change to repo directory
Push-Location (Split-Path -Parent (Split-Path -Parent (Split-Path -Absolute $MyInvocation.MyCommand.Path)))

try {
    foreach ($loader in $loaders) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Running: $($loader.name)" -ForegroundColor Green
        Write-Host "  Description: $($loader.desc)" -ForegroundColor Gray

        $cmd = "python -m $($loader.module) --parallelism $parallelism"
        if ($verbose) {
            Write-Host "  Command: $cmd" -ForegroundColor DarkGray
        }

        try {
            Invoke-Expression $cmd
            Write-Host "  ✓ COMPLETED" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ FAILED: $_" -ForegroundColor Red
            Write-Host ""
            Write-Host "CRITICAL: Loader failed. Dashboard requires this data." -ForegroundColor Yellow
            exit 1
        }
        Write-Host ""
    }

    Write-Host "="*70 -ForegroundColor Cyan
    Write-Host "ALL LOADERS COMPLETED" -ForegroundColor Green
    Write-Host "="*70 -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Run dashboard: python -m dashboard" -ForegroundColor Gray
    Write-Host "  2. Panels should now show market data" -ForegroundColor Gray
    Write-Host ""

} finally {
    Pop-Location
}

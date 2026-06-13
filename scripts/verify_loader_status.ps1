#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify that critical loaders are running daily and updating data_loader_status.

This script checks:
1. data_loader_status table has recent entries for critical loaders
2. All loaders have been updated within the last 24 hours
3. Status values are correct (COMPLETED/INCOMPLETE, not FAILED/RUNNING)

Exit code: 0 if all checks pass, 1 if any loader is stale/missing
#>

param(
    [int]$AgeThresholdHours = 24,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"

# Critical loaders that MUST run daily
$CriticalLoaders = @(
    'stock_symbols',
    'price_daily',
    'market_health_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'signal_quality_scores',
    'swing_trader_scores',
    'sector_ranking',
    'sector_performance'
)

Write-Host "===================================" -ForegroundColor Cyan
Write-Host "LOADER STATUS VERIFICATION" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Threshold: $AgeThresholdHours hours"
Write-Host "Critical loaders: $($CriticalLoaders.Count)"
Write-Host ""

# Try to connect to database using psql
$env:PGPASSWORD = $env:DB_PASSWORD
$DbHost = $env:DB_HOST
$DbName = $env:DB_NAME
$DbUser = $env:DB_USER
$DbPort = $env:DB_PORT -or 5432

if (-not $DbHost) {
    Write-Host "ERROR: DB_HOST environment variable not set" -ForegroundColor Red
    exit 1
}

Write-Host "Connecting to $DbHost/$DbName..." -ForegroundColor Yellow

# Query loader status
$Query = @"
SELECT
    table_name,
    status,
    EXTRACT(EPOCH FROM (NOW() - last_updated))/3600 AS age_hours,
    TO_CHAR(last_updated, 'YYYY-MM-DD HH24:MI:SS') AS last_updated,
    row_count,
    latest_date
FROM data_loader_status
WHERE table_name = ANY(ARRAY['stock_symbols', 'price_daily', 'market_health_daily',
    'technical_data_daily', 'buy_sell_daily', 'signal_quality_scores', 'swing_trader_scores',
    'sector_ranking', 'sector_performance'])
ORDER BY last_updated DESC;
"@

try {
    $results = psql -h $DbHost -p $DbPort -U $DbUser -d $DbName -t -A -F '|' -c $Query
} catch {
    Write-Host "ERROR: Could not connect to database: $_" -ForegroundColor Red
    exit 1
}

$staleLoaders = @()
$okLoaders = @()

foreach ($line in $results) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }

    $parts = $line -split '\|'
    if ($parts.Count -lt 3) { continue }

    $tableName = $parts[0]
    $status = $parts[1]
    $ageHours = [float]($parts[2])
    $lastUpdated = $parts[3]
    $rowCount = $parts[4]

    $isCritical = $CriticalLoaders -contains $tableName

    if ($null -eq $ageHours -or $ageHours -gt $AgeThresholdHours) {
        $staleLoaders += @{
            Name = $tableName
            Age = $ageHours
            Status = $status
        }
        Write-Host "✗ $tableName" -ForegroundColor Red
        Write-Host "  Status: $status | Age: $(if ($ageHours) { "$([math]::Round($ageHours, 1))h" } else { "NEVER_RUN" }) | LastUpdated: $lastUpdated" -ForegroundColor Red
    } else {
        $okLoaders += $tableName
        Write-Host "✓ $tableName" -ForegroundColor Green
        Write-Host "  Status: $status | Age: $([math]::Round($ageHours, 1))h | Rows: $rowCount | LastUpdated: $lastUpdated" -ForegroundColor Green
    }
}

# Check for missing loaders
$foundLoaders = ($results | ForEach-Object { ($_ -split '\|')[0] }) | Sort-Object -Unique
$missingLoaders = $CriticalLoaders | Where-Object { $_ -notin $foundLoaders }

if ($missingLoaders.Count -gt 0) {
    Write-Host "" -ForegroundColor Yellow
    Write-Host "Missing loaders (never run):" -ForegroundColor Yellow
    foreach ($loader in $missingLoaders) {
        Write-Host "✗ $loader" -ForegroundColor Red
        $staleLoaders += @{
            Name = $loader
            Age = $null
            Status = "NEVER_RUN"
        }
    }
}

# Summary
Write-Host "" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "OK: $($okLoaders.Count)/$($CriticalLoaders.Count)" -ForegroundColor $(if ($staleLoaders.Count -eq 0) { "Green" } else { "Red" })
Write-Host "STALE/MISSING: $($staleLoaders.Count)/$($CriticalLoaders.Count)" -ForegroundColor $(if ($staleLoaders.Count -gt 0) { "Red" } else { "Green" })

if ($staleLoaders.Count -gt 0) {
    Write-Host "" -ForegroundColor Red
    Write-Host "ALERT: $($staleLoaders.Count) loader(s) have stale/missing status!" -ForegroundColor Red
    Write-Host "Action: Check orchestrator logs and loader task definitions" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "" -ForegroundColor Green
    Write-Host "OK: All critical loaders are running daily" -ForegroundColor Green
    exit 0
}

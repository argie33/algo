#!/usr/bin/env pwsh
<#
.SYNOPSIS
Remove weekend/holiday price rows from price tables due to yfinance data errors.

This script removes rows where the date is a Saturday, Sunday, or US market holiday.
#>

param(
    [switch]$DryRun = $false,
    [string]$Tables = "price_daily,price_weekly,price_monthly,etf_price_daily,etf_price_weekly,etf_price_monthly"
)

# Load environment
$env:DB_HOST = $env:DB_HOST -or "localhost"
$env:DB_PORT = $env:DB_PORT -or "5432"
$env:DB_USER = $env:DB_USER -or "postgres"
$env:DB_NAME = $env:DB_NAME -or "algo"

if (-not $env:DB_PASSWORD) {
    Write-Error "DB_PASSWORD not set in environment"
    exit 1
}

# US market holidays (same as algo_market_calendar.py)
$holidays = @(
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-03-28", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-10", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"
)

$tableList = $Tables -split ','

Write-Host "=== Weekend/Holiday Price Data Cleanup ===" -ForegroundColor Green
Write-Host "Dry run: $DryRun" -ForegroundColor Yellow

foreach ($table in $tableList) {
    $table = $table.Trim()

    # Count weekends
    $weekendQuery = "SELECT COUNT(*) FROM $table WHERE EXTRACT(DOW FROM date) IN (0, 6)"

    # Count holidays
    $holidayCondition = "date::text IN ('" + ($holidays -join "','") + "')"
    $holidayQuery = "SELECT COUNT(*) FROM $table WHERE $holidayCondition"

    Write-Host "`nTable: $table"
    Write-Host "  Checking for weekend/holiday rows..."

    try {
        $env:PGPASSWORD = $env:DB_PASSWORD

        # Count weekends
        $weekendCount = psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -t -c $weekendQuery 2>$null
        Write-Host "    Weekend rows: $weekendCount"

        # Count holidays
        $holidayCount = psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -t -c $holidayQuery 2>$null
        Write-Host "    Holiday rows: $holidayCount"

        $totalRows = [int]$weekendCount + [int]$holidayCount

        if ($totalRows -gt 0) {
            if ($DryRun) {
                Write-Host "    [DRY RUN] Would delete $totalRows rows" -ForegroundColor Yellow
            } else {
                Write-Host "    Deleting $totalRows rows..." -ForegroundColor Yellow

                # Delete weekends
                $delWeekend = "DELETE FROM $table WHERE EXTRACT(DOW FROM date) IN (0, 6)"
                psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -c $delWeekend 2>$null

                # Delete holidays
                $delHoliday = "DELETE FROM $table WHERE $holidayCondition"
                psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -c $delHoliday 2>$null

                Write-Host "    ✓ Deleted" -ForegroundColor Green
            }
        } else {
            Write-Host "    ✓ No weekend/holiday rows found" -ForegroundColor Green
        }
    } catch {
        Write-Host "    ✗ Error: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== Done ===" -ForegroundColor Green

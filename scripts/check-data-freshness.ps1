# Check data freshness - specifically staleness columns populated by EOD pipeline
# CRITICAL: Must run this on Jun 6 at 4:05 PM to verify data patrol completed
# Usage: ./check-data-freshness.ps1

$env:PGPASSWORD = $env:DB_PASSWORD

$query = @"
SELECT
    COUNT(*) as total_rows,
    COUNT(buy_sell_daily_age_days) as bs_non_null,
    COUNT(technical_data_age_days) as tech_non_null,
    COUNT(trend_template_age_days) as trend_non_null,
    MAX(buy_sell_daily_age_days) as max_bs_age,
    MAX(technical_data_age_days) as max_tech_age,
    MAX(trend_template_age_days) as max_trend_age
FROM signal_quality_scores;
"@

Write-Host "Checking data freshness staleness columns..." -ForegroundColor Cyan

try {
    $result = psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -t -c $query

    $lines = $result | where { $_ -ne '' }
    if ($lines.Count -lt 1) {
        Write-Host "✗ Query returned no results" -ForegroundColor Red
        exit 1
    }

    # Parse results (single line output)
    $parts = $lines[0] -split '\|' | % { $_.Trim() }

    $total = [int]$parts[0]
    $bsNonNull = [int]$parts[1]
    $techNonNull = [int]$parts[2]
    $trendNonNull = [int]$parts[3]
    $maxBs = if ($parts[4] -eq '') { $null } else { $parts[4] }
    $maxTech = if ($parts[5] -eq '') { $null } else { $parts[5] }
    $maxTrend = if ($parts[6] -eq '') { $null } else { $parts[6] }

    Write-Host ""
    Write-Host "Results:" -ForegroundColor Cyan
    Write-Host "  Total rows in signal_quality_scores: $total"
    Write-Host "  buy_sell_daily_age_days non-NULL: $bsNonNull (max: $maxBs)"
    Write-Host "  technical_data_age_days non-NULL: $techNonNull (max: $maxTech)"
    Write-Host "  trend_template_age_days non-NULL: $trendNonNull (max: $maxTrend)"
    Write-Host ""

    # Verdict
    if ($bsNonNull -eq $total -and $techNonNull -eq $total -and $trendNonNull -eq $total) {
        Write-Host "✓ SUCCESS: All staleness columns fully populated!" -ForegroundColor Green
        Write-Host "  Data patrol completed successfully."
        exit 0
    } else {
        Write-Host "✗ FAILURE: Some staleness columns are NULL" -ForegroundColor Red
        Write-Host "  Data patrol did not complete - Phase 1 will fail data freshness checks." -ForegroundColor Red
        exit 1
    }

} catch {
    Write-Host "✗ Error checking database: $_" -ForegroundColor Red
    exit 1
}

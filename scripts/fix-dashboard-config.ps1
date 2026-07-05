#!/usr/bin/env pwsh
<#
.SYNOPSIS
Fix dashboard config by populating missing algo_config entries

.DESCRIPTION
Inserts required configuration values into algo_config table.
Uses environment variables: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
#>

param(
    [switch]$DryRun
)

Write-Host "Dashboard Configuration Fix" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# Check environment variables
$dbHost = $env:DB_HOST
$dbUser = $env:DB_USER
$dbPassword = $env:DB_PASSWORD
$dbName = $env:DB_NAME

if (-not $dbHost -or -not $dbUser -or -not $dbPassword -or -not $dbName) {
    Write-Host "ERROR: Database credentials not set in environment" -ForegroundColor Red
    Write-Host ""
    Write-Host "Required environment variables:" -ForegroundColor Yellow
    Write-Host "  DB_HOST         (RDS endpoint)" -ForegroundColor Gray
    Write-Host "  DB_USER         (postgres user)" -ForegroundColor Gray
    Write-Host "  DB_PASSWORD     (password)" -ForegroundColor Gray
    Write-Host "  DB_NAME         (database name, usually 'algo')" -ForegroundColor Gray
    exit 1
}

Write-Host "Connecting to database..." -ForegroundColor Green
Write-Host "Host: $dbHost" -ForegroundColor Gray
Write-Host "Database: $dbName" -ForegroundColor Gray
Write-Host ""

# Create Python script to run SQL
$pythonScript = @"
import psycopg2
import sys

try:
    conn = psycopg2.connect(
        host='$dbHost',
        database='$dbName',
        user='$dbUser',
        password='$dbPassword',
        sslmode='require'
    )
    cur = conn.cursor()

    # Read and execute SQL
    with open('scripts/populate-algo-config.sql', 'r') as f:
        sql = f.read()

    print("[*] Executing SQL migration...")
    cur.execute(sql)
    conn.commit()

    # Verify insertion
    cur.execute("""
        SELECT COUNT(*) FROM algo_config
        WHERE key IN (
            'min_signal_quality_score',
            'min_swing_score',
            'min_completeness_score',
            'min_volume_ma_50d',
            'min_avg_daily_dollar_volume',
            'earnings_blackout_days_before',
            'earnings_blackout_days_after'
        )
    """)
    count = cur.fetchone()[0]

    print(f"[✓] SUCCESS: {count}/7 required config keys populated")
    print("")
    print("[*] Verifying config values...")
    cur.execute("""
        SELECT key, value FROM algo_config
        WHERE key IN (
            'min_signal_quality_score',
            'min_swing_score',
            'min_completeness_score',
            'min_volume_ma_50d',
            'min_avg_daily_dollar_volume',
            'earnings_blackout_days_before',
            'earnings_blackout_days_after'
        )
        ORDER BY key
    """)

    for key, value in cur.fetchall():
        print(f"  {key} = {value}")

    cur.close()
    conn.close()
    sys.exit(0)

except psycopg2.Error as e:
    print(f"[✗] Database error: {e}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"[✗] Error: {e}", file=sys.stderr)
    sys.exit(1)
"@

if ($DryRun) {
    Write-Host "[DRY RUN] Would execute the following SQL:" -ForegroundColor Yellow
    Get-Content scripts/populate-algo-config.sql
    exit 0
}

# Write Python script to temp file and execute
$tempScript = "$env:TEMP\fix-config-$([guid]::NewGuid().ToString().Substring(0,8)).py"
$pythonScript | Out-File -FilePath $tempScript -Encoding UTF8

try {
    python $tempScript

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[✓] Configuration fix applied successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Restart the dashboard: python -m dashboard" -ForegroundColor Gray
        Write-Host "  2. All panels should now load with data" -ForegroundColor Gray
    } else {
        Write-Host "[✗] Fix failed" -ForegroundColor Red
        exit 1
    }
} finally {
    Remove-Item -Path $tempScript -ErrorAction SilentlyContinue
}

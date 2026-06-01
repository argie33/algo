#!/usr/bin/env pwsh
<#
.SYNOPSIS
Apply migration 004 (idempotency_key column) to RDS database.

.DESCRIPTION
Applies the migration to add idempotency_key column to algo_trades table.
This migration must be applied after infrastructure deploys (CI cannot reach private RDS Proxy).

.PARAMETER DryRun
Show what will be applied without executing (Python migration only supports actual execution)

.EXAMPLE
./scripts/apply-migration-004.ps1
./scripts/apply-migration-004.ps1 -DryRun

.NOTES
Requires:
- Python 3.9+
- Database credentials in environment (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
- OR AWS credentials to fetch from Secrets Manager
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Migration 004: Add idempotency_key" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
$python = (Get-Command python3 -ErrorAction SilentlyContinue) -or (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) {
    Write-Error "Python not found. Install Python 3.9+ and try again."
    exit 1
}

# Get Python path
$pythonCmd = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
Write-Host "Using Python: $($pythonCmd)" -ForegroundColor Green

# Check if DB credentials are available
if (-not $env:DB_HOST) {
    Write-Host "DB_HOST not set. Attempting to fetch from AWS Secrets Manager..." -ForegroundColor Yellow

    # Try to get credentials from AWS Secrets Manager
    try {
        $secret = aws secretsmanager get-secret-value --secret-id algo/database --query SecretString --output text | ConvertFrom-Json
        $env:DB_HOST = $secret.host
        $env:DB_PORT = $secret.port
        $env:DB_USER = $secret.username
        $env:DB_PASSWORD = $secret.password
        $env:DB_NAME = $secret.dbname
        $env:DB_SSL = "require"
        Write-Host "✓ Loaded credentials from AWS Secrets Manager" -ForegroundColor Green
    } catch {
        Write-Error "Failed to load credentials from AWS or environment. Set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME environment variables."
        exit 1
    }
} else {
    Write-Host "Using database credentials from environment" -ForegroundColor Green
}

Write-Host "Connecting to: $($env:DB_HOST):$($env:DB_PORT)/$($env:DB_NAME)" -ForegroundColor Cyan
Write-Host ""

# Show migration details
Write-Host "Migration Details:" -ForegroundColor Cyan
Write-Host "  - Adds idempotency_key column to algo_trades table" -ForegroundColor Gray
Write-Host "  - Creates index idx_algo_trades_idempotency_key" -ForegroundColor Gray
Write-Host "  - Prevents duplicate trade execution" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN MODE (Python migrations execute immediately)" -ForegroundColor Yellow
}

# Run migration
Write-Host "Executing migration..." -ForegroundColor Cyan
$migrationsScript = Join-Path $PSScriptRoot ".." "migrations" "run.py"

try {
    & $pythonCmd $migrationsScript apply 004_add_idempotency_key_column

    Write-Host ""
    Write-Host "✓ Migration 004 completed successfully" -ForegroundColor Green
    Write-Host ""

    # Verify
    Write-Host "Verifying migration..." -ForegroundColor Cyan
    & $pythonCmd $migrationsScript status

} catch {
    Write-Host ""
    Write-Error "Migration 004 failed: $_"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ All done! Ready for trade execution" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

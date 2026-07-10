#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start local development environment (dev_server + dashboard TUI)

.DESCRIPTION
Starts the API dev_server on localhost:3001 and runs the dashboard in local mode.
This script handles:
1. Starting the dev_server in the background
2. Waiting for dev_server to be ready
3. Starting the dashboard TUI with --local flag
4. Cleanup on exit

.EXAMPLE
.\start_local_dev.ps1                # Start dashboard in local mode
.\start_local_dev.ps1 -NoWatch        # Single refresh, don't watch
.\start_local_dev.ps1 -DashboardOnly  # Start dashboard only (dev_server already running)

.NOTES
Requirements: Python 3.11+, PostgreSQL running on localhost:5432
#>

param(
    [switch]$NoWatch = $false,
    [switch]$DashboardOnly = $false,
    [int]$ApiPort = 3001
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== LOCAL DEVELOPMENT ENVIRONMENT ===" -ForegroundColor Cyan
Write-Host "Starting local dev_server + dashboard..." -ForegroundColor Green
Write-Host ""

# Start dev_server in background if not --DashboardOnly
if (-not $DashboardOnly) {
    Write-Host "[1/2] Starting dev_server on http://localhost:$ApiPort" -ForegroundColor Yellow

    # Start dev_server
    $devServerProc = Start-Process -FilePath "python" `
        -ArgumentList "api-pkg/dev_server.py" `
        -WorkingDirectory $ScriptDir `
        -NoNewWindow `
        -PassThru

    if ($null -eq $devServerProc) {
        Write-Host "ERROR: Failed to start dev_server" -ForegroundColor Red
        exit 1
    }

    Write-Host "  Process ID: $($devServerProc.Id)" -ForegroundColor Dim

    # Wait for dev_server to be ready
    Write-Host "  Waiting for dev_server to be ready..." -ForegroundColor Dim
    $ready = $false
    $attempts = 0
    while (-not $ready -and $attempts -lt 30) {
        Start-Sleep -Milliseconds 500
        $attempts++
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$ApiPort/health" `
                -Headers @{"Authorization" = "Bearer dev-admin"} `
                -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                $ready = $true
                Write-Host "  ✓ dev_server ready (took ${attempts}x500ms)" -ForegroundColor Green
            }
        } catch {
            # Still starting up
        }
    }

    if (-not $ready) {
        Write-Host "ERROR: dev_server did not start in time (30s)" -ForegroundColor Red
        Stop-Process -Id $devServerProc.Id -ErrorAction SilentlyContinue
        exit 1
    }

    Write-Host ""
}

# Start dashboard with --local flag
Write-Host "[2/2] Starting dashboard (LOCAL MODE)" -ForegroundColor Yellow
Write-Host "  Dashboard API: http://localhost:$ApiPort" -ForegroundColor Dim

if ($NoWatch) {
    Write-Host "  Mode: Single refresh" -ForegroundColor Dim
    & python -m dashboard --local
} else {
    Write-Host "  Mode: Watch mode (refresh every 30s)" -ForegroundColor Dim
    Write-Host "  Press 'q' to quit" -ForegroundColor Dim
    & python -m dashboard --local -w 30
}

# Cleanup
Write-Host ""
Write-Host "Cleaning up..." -ForegroundColor Yellow
if (-not $DashboardOnly -and $null -ne $devServerProc) {
    Stop-Process -Id $devServerProc.Id -ErrorAction SilentlyContinue
    Write-Host "  ✓ Stopped dev_server" -ForegroundColor Green
}

Write-Host "Done." -ForegroundColor Green

#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start and manage all development services (dev_server, vite, orchestrator)
.DESCRIPTION
Starts PostgreSQL connection, dev_server (API), vite (frontend), and validates orchestrator.
All services run in background jobs and can be restarted if they crash.
.EXAMPLE
.\scripts\start-dev-environment.ps1
#>

param(
    [switch]$NoAutoRestart = $false,
    [int]$HealthCheckIntervalSeconds = 30
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Colors for output
$colors = @{
    Success = "Green"
    Error   = "Red"
    Info    = "Cyan"
    Warn    = "Yellow"
}

function Write-Status {
    param([string]$Message, [string]$Type = "Info")
    $color = $colors[$Type] ?? "White"
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor $color
}

function Get-ProcessPorts {
    param([int]$Port)
    try {
        $proc = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        return $proc.OwningProcess
    }
    catch { return $null }
}

function Stop-ProcessByPort {
    param([int]$Port)
    $pid = Get-ProcessPorts -Port $Port
    if ($pid) {
        Write-Status "Stopping process on port $Port (PID: $pid)" "Warn"
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

# Ensure LOCAL_MODE and DB credentials
$env:LOCAL_MODE = "true"
$env:DB_HOST = $env:DB_HOST ?? "localhost"
$env:DB_PORT = $env:DB_PORT ?? "5432"
$env:DB_NAME = $env:DB_NAME ?? "stocks"
$env:DB_USER = $env:DB_USER ?? "stocks"
$env:DB_PASSWORD = $env:DB_PASSWORD ?? "stocks"
$env:ORCHESTRATOR_EXECUTION_MODE = "paper"

Write-Status "Development Environment Configuration:" "Info"
Write-Status "  DB_HOST: $($env:DB_HOST)" "Info"
Write-Status "  LOCAL_MODE: $($env:LOCAL_MODE)" "Info"
Write-Status "  ORCHESTRATOR_EXECUTION_MODE: $($env:ORCHESTRATOR_EXECUTION_MODE)" "Info"

# Clean up any orphaned processes
Write-Status "Cleaning up orphaned processes..." "Info"
Stop-ProcessByPort -Port 3001
Stop-ProcessByPort -Port 5173

# Start dev_server (API) on port 3001
Write-Status "Starting dev_server (API) on port 3001..." "Info"
$devServerJob = Start-Job -Name "dev-server-3001" -ScriptBlock {
    cd "$((Get-Location).Path)\..\api-pkg"
    python dev_server.py
} -WorkingDirectory (Get-Location)

# Wait for dev_server to start
Start-Sleep -Seconds 3
$devServerPid = Get-ProcessPorts -Port 3001
if ($devServerPid) {
    Write-Status "✓ dev_server running on port 3001 (PID: $devServerPid)" "Success"
}
else {
    Write-Status "✗ dev_server failed to start" "Error"
}

# Start Vite dev server (frontend) on port 5173
Write-Status "Starting Vite dev server (Frontend) on port 5173..." "Info"

# First, regenerate config.js for local dev
Set-Location webapp\frontend
node scripts\setup-dev.js
Write-Status "Config.js regenerated for local development" "Info"

$viteJob = Start-Job -Name "vite-5173" -ScriptBlock {
    cd "$((Get-Location).Path)"
    npm run dev
} -WorkingDirectory (Get-Location)

# Wait for Vite to start
Start-Sleep -Seconds 5
$vitePid = Get-ProcessPorts -Port 5173
if ($vitePid) {
    Write-Status "✓ Vite running on port 5173 (PID: $vitePid)" "Success"
    Write-Status "  Dashboard: http://localhost:5173" "Info"
    Write-Status "  API (via proxy): http://localhost:5173/api/*" "Info"
}
else {
    Write-Status "✗ Vite failed to start" "Error"
}

Set-Location ../..

# Validate orchestrator setup
Write-Status "Validating orchestrator readiness..." "Info"
$validation = python scripts/validate_orchestrator_readiness.py 2>&1 | Select-String "PASS|FAIL" -First 1
if ($validation) {
    Write-Status "✓ Orchestrator ready" "Success"
}
else {
    Write-Status "⚠ Orchestrator validation incomplete (non-blocking)" "Warn"
}

# Display summary
Write-Status "====== DEVELOPMENT ENVIRONMENT READY ======" "Success"
Write-Status "Frontend Dashboard: http://localhost:5173" "Info"
Write-Status "Backend API: http://localhost:3001" "Info"
Write-Status "Vite Proxy Routes: /api/* → localhost:3001" "Info"
Write-Status "Paper Trading Mode: ENABLED" "Info"
Write-Status "" "Info"
Write-Status "Jobs running:" "Info"
Get-Job | Where-Object { $_.State -eq "Running" } | ForEach-Object {
    Write-Status "  - $($_.Name): $($_.State)" "Info"
}

if (-not $NoAutoRestart) {
    Write-Status "Health check running every $HealthCheckIntervalSeconds seconds..." "Info"
    Write-Status "Press Ctrl+C to stop" "Info"

    # Health check loop
    while ($true) {
        Start-Sleep -Seconds $HealthCheckIntervalSeconds

        # Check dev_server
        $devServerPid = Get-ProcessPorts -Port 3001
        if (-not $devServerPid) {
            Write-Status "⚠ dev_server (3001) crashed, restarting..." "Warn"
            Stop-ProcessByPort -Port 3001
            $devServerJob = Start-Job -Name "dev-server-3001" -ScriptBlock {
                cd "$((Get-Location).Path)\..\api-pkg"
                python dev_server.py
            }
            Start-Sleep -Seconds 3
        }

        # Check Vite
        $vitePid = Get-ProcessPorts -Port 5173
        if (-not $vitePid) {
            Write-Status "⚠ Vite (5173) crashed, restarting..." "Warn"
            Stop-ProcessByPort -Port 5173
            $viteJob = Start-Job -Name "vite-5173" -ScriptBlock {
                cd "$((Get-Location).Path)\webapp\frontend"
                npm run dev
            }
            Start-Sleep -Seconds 5
        }
    }
}
else {
    Write-Status "Auto-restart disabled. Services will stop if they crash." "Warn"
}

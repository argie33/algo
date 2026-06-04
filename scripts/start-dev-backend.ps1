#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start the local development backend server with proper process management.

This script:
1. Kills any existing dev_server.py processes
2. Waits for port 3001 to be free
3. Starts a fresh instance of dev_server.py
4. Keeps the process running in the foreground

.DESCRIPTION
Run this in a dedicated terminal for the backend.
The process will stay running until you press Ctrl+C.

.EXAMPLE
.\scripts\start-dev-backend.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "`n=== Starting Development Backend ===" -ForegroundColor Cyan

# Kill any existing dev_server processes
Write-Host "Cleaning up old processes..." -ForegroundColor Yellow
$existingProcesses = Get-Process python -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "dev_server" }

if ($existingProcesses) {
    Write-Host "  Killing $(($existingProcesses | Measure-Object).Count) old dev_server process(es)..." -ForegroundColor Yellow
    $existingProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# Verify port 3001 is free
$maxWait = 10
$waited = 0
while ((netstat -ano 2>$null | Select-String ":3001") -and $waited -lt $maxWait) {
    Write-Host "  Waiting for port 3001 to free up..." -ForegroundColor Gray
    Start-Sleep -Seconds 1
    $waited++
}

if (netstat -ano 2>$null | Select-String ":3001") {
    Write-Host "  ✗ Port 3001 still in use after waiting" -ForegroundColor Red
    Write-Host "  Try: taskkill /F /IM python.exe" -ForegroundColor Red
    exit 1
}

Write-Host "  ✓ Port 3001 is free" -ForegroundColor Green

# Start dev_server
Write-Host "`nStarting dev server..." -ForegroundColor Cyan
Write-Host "  Location: lambda/api/dev_server.py" -ForegroundColor Gray
Write-Host "  Port: 3001" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

Push-Location lambda/api
try {
    python dev_server.py
}
finally {
    Pop-Location
}

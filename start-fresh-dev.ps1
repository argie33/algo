#!/usr/bin/env pwsh
<#
.SYNOPSIS
Start fresh development environment - kills old processes and starts clean
.DESCRIPTION
This script ensures you have a clean development environment:
1. Kills any existing dev_server processes (port 3001)
2. Kills any existing Vite server processes (port 5173)
3. Starts fresh dev_server
4. Starts fresh Vite dev server
5. Opens the dashboard in browser with cache cleared
#>

param(
    [switch]$NoBrowser = $false,
    [switch]$DevServerOnly = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Fresh Development Environment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Helper function to kill processes on port
function Kill-ProcessOnPort {
    param([int]$Port)
    Write-Host "Checking port $Port..." -ForegroundColor Yellow
    $processes = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING"
    if ($processes) {
        foreach ($process in $processes) {
            $parts = $process -split '\s+' | Where-Object { $_ -ne '' }
            $pid = $parts[-1]
            if ($pid) {
                Write-Host "  Found process $pid on port $Port - killing..." -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 500
            }
        }
    }
}

Write-Host "[1/4] Cleaning up old processes..." -ForegroundColor Green
Kill-ProcessOnPort 3001
Kill-ProcessOnPort 5173
Start-Sleep -Seconds 1

if (-not $DevServerOnly) {
    Write-Host ""
    Write-Host "[2/4] Starting dev_server (Lambda API on port 3001)..." -ForegroundColor Green
    Write-Host "  Command: python api-pkg/dev_server.py" -ForegroundColor Gray
    Write-Host "  This will run in the background..." -ForegroundColor Gray
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "api-pkg/dev_server.py" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3

    Write-Host ""
    Write-Host "[3/4] Starting Vite dev server (Frontend on port 5173)..." -ForegroundColor Green
    Write-Host "  Location: webapp/frontend" -ForegroundColor Gray
    Write-Host "  Command: npm run dev" -ForegroundColor Gray
    Write-Host "  This will run in a new window..." -ForegroundColor Gray
    Start-Process -FilePath "npm" -ArgumentList "run dev" -WorkingDirectory "webapp/frontend" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
} else {
    Write-Host ""
    Write-Host "[2/4] Starting dev_server ONLY (Lambda API on port 3001)..." -ForegroundColor Green
    Write-Host "  Command: python api-pkg/dev_server.py" -ForegroundColor Gray
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "api-pkg/dev_server.py" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "[4/4] Verification..." -ForegroundColor Green

$devServerOk = $false
$viteOk = $false

# Quick test of dev_server
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:3001/api/portfolio" -Headers @{"Authorization"="Bearer dev-admin"} -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) {
        Write-Host "  ✓ Dev server responding on port 3001" -ForegroundColor Green
        $devServerOk = $true
    }
} catch {
    Write-Host "  ✗ Dev server NOT responding" -ForegroundColor Red
}

# Quick test of Vite
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:5173/api/portfolio" -Headers @{"Authorization"="Bearer dev-admin"} -TimeoutSec 5 -ErrorAction SilentlyContinue
    if ($resp.StatusCode -eq 200) {
        Write-Host "  ✓ Vite proxy working on port 5173" -ForegroundColor Green
        $viteOk = $true
    }
} catch {
    Write-Host "  ✗ Vite NOT responding yet (may still be loading)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. BROWSER CACHE (CRITICAL):" -ForegroundColor Yellow
Write-Host "   - Open browser DevTools (F12)" -ForegroundColor Gray
Write-Host "   - Application tab -> Clear Storage -> Clear All" -ForegroundColor Gray
Write-Host "   - Or: Ctrl+Shift+R hard refresh" -ForegroundColor Gray
Write-Host ""
Write-Host "2. OPEN DASHBOARD:" -ForegroundColor Yellow
Write-Host "   - Go to: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. IF DASHBOARD STILL SHOWS 'DATA NOT AVAILABLE':" -ForegroundColor Yellow
Write-Host "   - Check browser console (F12) for JavaScript errors" -ForegroundColor Gray
Write-Host "   - Run: python3 -c 'import requests; print(requests.get(\"http://localhost:3001/api/algo/status\", headers={\"Authorization\": \"Bearer dev-admin\"}).status_code)'" -ForegroundColor Gray
Write-Host "   - Expected output: 200" -ForegroundColor Gray
Write-Host ""
Write-Host "Dev server location: $PSScriptRoot\api-pkg" -ForegroundColor Gray
Write-Host "Vite server location: $PSScriptRoot\webapp\frontend" -ForegroundColor Gray
Write-Host ""

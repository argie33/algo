#!/usr/bin/env pwsh
<#
.SYNOPSIS
Complete local development environment setup and startup guide.

This script validates the environment and shows you exactly what to do next.

.DESCRIPTION
Run this once when you clone the repo or after significant changes.
It will:
1. Generate frontend config.js for development
2. Validate all required dependencies
3. Show step-by-step startup instructions

.EXAMPLE
.\scripts\start-dev-environment.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

Write-Host "`n" -ForegroundColor Cyan
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        LOCAL DEVELOPMENT ENVIRONMENT SETUP                 ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

# 1. Generate frontend config
Write-Host "`n[1/4] Setting up frontend configuration..." -ForegroundColor Yellow
& .\scripts\setup-frontend-dev-config.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to generate frontend config" -ForegroundColor Red
    exit 1
}

# 2. Check Python
Write-Host "`n[2/4] Checking Python setup..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Python: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Python not found or not in PATH" -ForegroundColor Red
    exit 1
}

# 3. Check Node
Write-Host "`n[3/4] Checking Node.js setup..." -ForegroundColor Yellow
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Node.js: $nodeVersion" -ForegroundColor Green
    $npmVersion = npm --version 2>&1
    Write-Host "  ✓ npm: $npmVersion" -ForegroundColor Green
} else {
    Write-Host "  ✗ Node.js not found or not in PATH" -ForegroundColor Red
    exit 1
}

# 4. Check database
Write-Host "`n[4/4] Checking PostgreSQL..." -ForegroundColor Yellow
$port5432 = netstat -ano 2>$null | Select-String ":5432"
if ($port5432) {
    Write-Host "  ✓ PostgreSQL listening on port 5432" -ForegroundColor Green
} else {
    Write-Host "  ⚠ PostgreSQL not detected on port 5432" -ForegroundColor Yellow
    Write-Host "    → Make sure PostgreSQL is running locally (stocks DB)" -ForegroundColor Gray
}

# Summary
Write-Host "`n" -ForegroundColor Cyan
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                  STARTUP INSTRUCTIONS                      ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan

Write-Host "`n📋 BEFORE YOU START:" -ForegroundColor Cyan
Write-Host "  • Kill any existing dev_server.py processes:" -ForegroundColor White
Write-Host "    → Get-Process python | Where-Object {\$_.CommandLine -match 'dev_server'} | Stop-Process -Force"
Write-Host ""
Write-Host "  • Ensure PostgreSQL is running:" -ForegroundColor White
Write-Host "    → Listen on 0.0.0.0:5432" -ForegroundColor Gray
Write-Host "    → Database: stocks" -ForegroundColor Gray
Write-Host "    → User: stocks / Password: stocks" -ForegroundColor Gray

Write-Host "`n🚀 STARTUP (use 3 separate terminal windows):" -ForegroundColor Cyan

Write-Host ""
Write-Host "  Terminal 1 - Backend:" -ForegroundColor Green
Write-Host "    cd C:\Users\arger\code\algo" -ForegroundColor White
Write-Host "    .\scripts\start-dev-backend.ps1" -ForegroundColor White
Write-Host "    " -ForegroundColor Gray
Write-Host "    (or manually)" -ForegroundColor Gray
Write-Host "    cd lambda/api" -ForegroundColor Gray
Write-Host "    python dev_server.py" -ForegroundColor Gray

Write-Host ""
Write-Host "  Terminal 2 - Frontend:" -ForegroundColor Green
Write-Host "    cd C:\Users\arger\code\algo\webapp\frontend" -ForegroundColor White
Write-Host "    npm install  (first time only)" -ForegroundColor White
Write-Host "    npm run dev" -ForegroundColor White

Write-Host ""
Write-Host "  Terminal 3 - Optional: Watch logs:" -ForegroundColor Green
Write-Host "    (leave open for monitoring)" -ForegroundColor Gray

Write-Host "`n✨ TEST YOUR SETUP:" -ForegroundColor Cyan
Write-Host "  1. Open http://localhost:5173 in your browser" -ForegroundColor White
Write-Host "  2. Check browser console for errors (F12)" -ForegroundColor White
Write-Host "  3. Try an API call (e.g., login, dashboard, etc.)" -ForegroundColor White

Write-Host "`n📊 EXPECTED BEHAVIOR:" -ForegroundColor Cyan
Write-Host "  ✓ Frontend loads without CORS errors" -ForegroundColor Green
Write-Host "  ✓ API calls route to localhost:3001 (Vite proxy)" -ForegroundColor Green
Write-Host "  ✓ No 5xx errors in console" -ForegroundColor Green
Write-Host "  ✓ Dev server shows request logs for each API call" -ForegroundColor Green

Write-Host "`n🔧 TROUBLESHOOTING:" -ForegroundColor Cyan
Write-Host "  • Port 3001 in use: taskkill /F /IM python.exe" -ForegroundColor White
Write-Host "  • npm issues: npm install --force in webapp/frontend" -ForegroundColor White
Write-Host "  • DB not found: Check PostgreSQL is running with 'stocks' database" -ForegroundColor White
Write-Host "  • Config wrong: Run .\scripts\setup-frontend-dev-config.ps1" -ForegroundColor White

Write-Host "`n" -ForegroundColor Cyan

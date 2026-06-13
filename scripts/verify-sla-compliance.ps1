#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify AWS SLA compliance for the algo system.
Checks: API response times, data freshness, dashboard data sources.
#>

param(
    [string]$ApiUrl = "http://localhost:3001",
    [int]$TimeoutSec = 10
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "====== AWS SLA COMPLIANCE CHECK ======" -ForegroundColor Cyan
Write-Host "Checking API at: $ApiUrl"
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

$issues = @()
$checks = @()

# ========== CHECK 1: API Response Times ==========
Write-Host "[1/5] Checking API response times..." -ForegroundColor Yellow

$endpoints = @(
    "/api/algo/portfolio",
    "/api/algo/performance",
    "/api/algo/positions",
    "/api/algo/market",
    "/api/health"
)

$latencies = @()

foreach ($endpoint in $endpoints) {
    try {
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        $response = Invoke-WebRequest -Uri "$ApiUrl$endpoint" -TimeoutSec $TimeoutSec
        $timer.Stop()

        $latency = $timer.ElapsedMilliseconds
        $latencies += $latency

        $status = if ($latency -lt 100) { "Fast" } elseif ($latency -lt 500) { "OK" } else { "Slow" }
        Write-Host "  $endpoint : ${latency}ms ($status)" -ForegroundColor $(if ($latency -lt 500) { "Green" } else { "Red" })

        if ($latency -gt 5000) {
            $issues += "API endpoint $endpoint taking ${latency}ms (SLA: <5s)"
        }
    } catch {
        Write-Host "  $endpoint : ERROR" -ForegroundColor Red
        $issues += "API endpoint $endpoint unavailable"
    }
}

if ($latencies.Count -gt 0) {
    $avgLatency = [math]::Round(($latencies | Measure-Object -Average).Average, 0)
    Write-Host "  Average latency: ${avgLatency}ms" -ForegroundColor Cyan
    $checks += "API latency (avg): ${avgLatency}ms"
}
Write-Host ""

# ========== CHECK 2: Data Source Verification ==========
Write-Host "[2/5] Checking data source configuration..." -ForegroundColor Yellow

$dashboardFile = "tools/dashboard/dashboard.py"
if (Test-Path $dashboardFile) {
    $content = Get-Content $dashboardFile -Raw

    $apiCalls = ($content | Select-String "api_call\(" -AllMatches).Matches.Count
    $dbCalls = ($content | Select-String "DatabaseContext\|psycopg2" -AllMatches).Matches.Count

    Write-Host "  API calls detected: $apiCalls" -ForegroundColor Green
    Write-Host "  Direct DB calls detected: $dbCalls" -ForegroundColor $(if ($dbCalls -eq 0) { "Green" } else { "Yellow" })

    if ($dbCalls -eq 0) {
        Write-Host "  PASS: Dashboard uses API only" -ForegroundColor Green
        $checks += "Dashboard: API-only"
    } else {
        Write-Host "  WARN: Dashboard may have direct DB access" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ERROR: Dashboard file not found" -ForegroundColor Red
}

Write-Host ""

# ========== CHECK 3: AWS Credentials ==========
Write-Host "[3/5] Checking AWS credentials..." -ForegroundColor Yellow

$awsProfile = $env:AWS_PROFILE
if ($awsProfile) {
    Write-Host "  AWS_PROFILE: $awsProfile" -ForegroundColor Green
    $checks += "AWS profile: $awsProfile"
} else {
    Write-Host "  AWS_PROFILE: NOT SET" -ForegroundColor Yellow
    $issues += "AWS_PROFILE environment variable not set"
}

Write-Host ""

# ========== CHECK 4: Development vs Production ==========
Write-Host "[4/5] Checking environment configuration..." -ForegroundColor Yellow

$envFile = "lambda/api/dev_server.py"
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    if ($content -match "AWS Secrets Manager") {
        Write-Host "  Dev server: Configured for AWS Secrets Manager" -ForegroundColor Green
        $checks += "Dev server: AWS-ready"
    }
}

Write-Host ""

# ========== CHECK 5: Database Connection Config ==========
Write-Host "[5/5] Checking database configuration..." -ForegroundColor Yellow

if ($env:DB_HOST) {
    $dbHost = if ($env:DB_HOST -match "localhost|127") { "localhost (dev)" } else { "AWS RDS" }
    Write-Host "  Database: $dbHost" -ForegroundColor Green
    $checks += "Database configured: $dbHost"
} else {
    Write-Host "  Database: No DB_HOST configured" -ForegroundColor Yellow
    $issues += "DB_HOST not configured"
}

Write-Host ""

# ========== SUMMARY ==========
Write-Host "====== SLA COMPLIANCE SUMMARY ======" -ForegroundColor Cyan
Write-Host "Checks passed: $($checks.Count)" -ForegroundColor Green
Write-Host "Issues found: $($issues.Count)" -ForegroundColor $(if ($issues.Count -eq 0) { "Green" } else { "Red" })

if ($checks.Count -gt 0) {
    Write-Host ""
    Write-Host "Passed checks:" -ForegroundColor Green
    $checks | ForEach-Object { Write-Host "  [OK] $_" }
}

if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "Issues to resolve:" -ForegroundColor Red
    $issues | ForEach-Object { Write-Host "  [!] $_" }
    exit 1
} else {
    Write-Host ""
    Write-Host "[SUCCESS] All SLA checks passed!" -ForegroundColor Green
    exit 0
}

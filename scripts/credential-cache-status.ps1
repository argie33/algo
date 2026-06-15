#!/usr/bin/env pwsh
<#
.SYNOPSIS
Check and manage dev credential cache status.

.DESCRIPTION
Shows cache age, TTL, freshness, and allows manual refresh or clear.

.PARAMETER Action
Operation: Status (default), Refresh, Clear, Test

.EXAMPLE
./credential-cache-status.ps1
./credential-cache-status.ps1 -Action Refresh
./credential-cache-status.ps1 -Action Clear
./credential-cache-status.ps1 -Action Test
#>

param(
    [ValidateSet("Status", "Refresh", "Clear", "Test")]
    [string]$Action = "Status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CacheManager = Join-Path (Split-Path $PSScriptRoot) "dev-cache-manager.ps1"

if (-not (Test-Path $CacheManager)) {
    Write-Error "dev-cache-manager.ps1 not found at $CacheManager"
    exit 1
}

switch ($Action) {
    "Status" {
        Write-Host "Credential Cache Status:" -ForegroundColor Cyan
        Write-Host "========================" -ForegroundColor Cyan
        & $CacheManager -Mode Status
    }

    "Refresh" {
        Write-Host "Initiating credential refresh..." -ForegroundColor Cyan
        $RefreshScript = Join-Path (Split-Path $PSScriptRoot) "refresh-aws-credentials.ps1"
        if (Test-Path $RefreshScript) {
            & $RefreshScript
        } else {
            Write-Error "refresh-aws-credentials.ps1 not found"
            exit 1
        }
    }

    "Clear" {
        Write-Host "Clearing credential cache..." -ForegroundColor Yellow
        & $CacheManager -Mode Clear
        Write-Host "Cache cleared. Run 'refresh-aws-credentials.ps1' to fetch fresh credentials." -ForegroundColor Green
    }

    "Test" {
        Write-Host "Testing cached credentials..." -ForegroundColor Cyan
        $CachedCreds = & $CacheManager -Mode Get | ConvertFrom-Json

        if ($CachedCreds.access_key_id) {
            Write-Host "Found cached credentials:" -ForegroundColor Green
            Write-Host "  Access Key: $($CachedCreds.access_key_id)" -ForegroundColor Gray
            Write-Host "  Expires: $($CachedCreds.expires_at)" -ForegroundColor Gray

            # Test with AWS CLI
            Write-Host ""
            Write-Host "Testing with AWS CLI..." -ForegroundColor Cyan
            $env:AWS_PROFILE = "algo-developer"
            $env:AWS_DEFAULT_REGION = "us-east-1"

            $Identity = aws sts get-caller-identity --profile algo-developer 2>&1
            if ($LASTEXITCODE -eq 0) {
                $IdentityObj = $Identity | ConvertFrom-Json
                Write-Host "[OK] Credentials are valid" -ForegroundColor Green
                Write-Host "  Account: $($IdentityObj.Account)" -ForegroundColor Green
                Write-Host "  ARN: $($IdentityObj.Arn)" -ForegroundColor Green
            } else {
                Write-Host "[ERROR] Credentials are invalid or expired" -ForegroundColor Red
                Write-Host "  Error: $Identity" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "No cached credentials found" -ForegroundColor Yellow
            Write-Host "Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Cyan
        }
    }
}

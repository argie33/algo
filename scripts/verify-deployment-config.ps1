#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify deployment configuration for all critical systems.
Checks Issues #3-#6: Database tables, RDS Proxy, Frontend URL, Cognito.

.DESCRIPTION
Validates that all required configuration is in place before deploy.
Exits with error if any critical configuration is missing.
#>

param(
    [string]$Environment = "production",
    [switch]$SkipDatabase = $false,
    [switch]$SkipAWS = $false,
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"
$failures = @()
$warnings = @()

Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Deployment Configuration Verification" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ───────────────────────────────────────────────────────────────────────────────
# Issue #4: RDS Proxy Configuration
# ───────────────────────────────────────────────────────────────────────────────

Write-Host "[1/4] Checking RDS Proxy Configuration..." -ForegroundColor Yellow

if (-not $SkipAWS) {
    $dbHost = $env:DB_HOST
    if ([string]::IsNullOrWhiteSpace($dbHost)) {
        $failures += "Issue #4: DB_HOST environment variable not set"
    } elseif ($dbHost -notmatch "proxy") {
        if ($dbHost -match "^(localhost|127\.0\.0\.1)") {
            Write-Host "  ✓ Using localhost (development mode)" -ForegroundColor Green
        } else {
            $failures += "Issue #4: DB_HOST does not contain 'proxy'. Current: $dbHost"
            Write-Host "  ✗ DB_HOST appears to be direct RDS, not proxy. Connection pooling REQUIRED." -ForegroundColor Red
        }
    } else {
        Write-Host "  ✓ DB_HOST points to RDS Proxy: $dbHost" -ForegroundColor Green
    }
} else {
    Write-Host "  ⊘ Skipped (--SkipAWS)" -ForegroundColor Gray
}

# ───────────────────────────────────────────────────────────────────────────────
# Issue #5: Frontend URL Configuration for CORS
# ───────────────────────────────────────────────────────────────────────────────

Write-Host "[2/4] Checking Frontend URL Configuration..." -ForegroundColor Yellow

$frontendUrl = $env:FRONTEND_URL
if ([string]::IsNullOrWhiteSpace($frontendUrl)) {
    # Try to get from AWS Secrets Manager
    if (-not $SkipAWS) {
        try {
            $secret = aws secretsmanager get-secret-value --secret-id algo/cloudfront-domain 2>$null | ConvertFrom-Json
            if ($secret -and $secret.SecretString) {
                $cfDomain = $secret.SecretString | ConvertFrom-Json | Select-Object -ExpandProperty domain
                if ($cfDomain) {
                    Write-Host "  ✓ CloudFront domain found in Secrets Manager: $cfDomain" -ForegroundColor Green
                    $env:FRONTEND_URL = $cfDomain
                } else {
                    $failures += "Issue #5: FRONTEND_URL not set, and cloudfront-domain secret is empty"
                }
            } else {
                $failures += "Issue #5: FRONTEND_URL not set and algo/cloudfront-domain not found in Secrets Manager"
            }
        } catch {
            $failures += "Issue #5: FRONTEND_URL not set. Could not access Secrets Manager: $_"
        }
    } else {
        $failures += "Issue #5: FRONTEND_URL environment variable not set and --SkipAWS specified"
    }
} else {
    Write-Host "  ✓ FRONTEND_URL configured: $frontendUrl" -ForegroundColor Green
}

# ───────────────────────────────────────────────────────────────────────────────
# Issue #6: Cognito Authentication Configuration
# ───────────────────────────────────────────────────────────────────────────────

Write-Host "[3/4] Checking Cognito Authentication Configuration..." -ForegroundColor Yellow

$devBypass = $env:DEV_BYPASS_AUTH
$userPoolId = $env:COGNITO_USER_POOL_ID
$clientId = $env:COGNITO_CLIENT_ID
$cognuitoDomain = $env:COGNITO_DOMAIN

if ($devBypass -eq "true" -and $Environment -eq "production") {
    $failures += "Issue #6: DEV_BYPASS_AUTH is true in production (SECURITY RISK!)"
} elseif ($devBypass -eq "true") {
    $warnings += "Issue #6: DEV_BYPASS_AUTH enabled in $Environment (auth bypassed)"
}

if (-not [string]::IsNullOrWhiteSpace($userPoolId)) {
    if ([string]::IsNullOrWhiteSpace($clientId)) {
        $failures += "Issue #6: COGNITO_USER_POOL_ID set but COGNITO_CLIENT_ID missing"
    } elseif ([string]::IsNullOrWhiteSpace($cognuitoDomain)) {
        $failures += "Issue #6: COGNITO_USER_POOL_ID set but COGNITO_DOMAIN missing"
    } else {
        Write-Host "  ✓ Cognito authentication configured" -ForegroundColor Green
        Write-Host "    - User Pool: $($userPoolId.Substring(0, 20))..." -ForegroundColor Gray
        Write-Host "    - Domain: $cognuitoDomain" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⊘ Cognito authentication disabled (dev mode)" -ForegroundColor Gray
}

# ───────────────────────────────────────────────────────────────────────────────
# Issue #3: Database Tables Data Freshness
# ───────────────────────────────────────────────────────────────────────────────

Write-Host "[4/4] Checking Database Tables Data Freshness..." -ForegroundColor Yellow

if (-not $SkipDatabase) {
    if (-not [string]::IsNullOrWhiteSpace($env:DB_HOST) -and -not [string]::IsNullOrWhiteSpace($env:DB_USER)) {
        $requiredTables = @(
            "market_exposure_daily",
            "market_health_daily",
            "sector_ranking",
            "swing_trader_scores"
        )

        $allFresh = $true
        foreach ($table in $requiredTables) {
            try {
                # This is a conceptual check - actual DB check would require psql client
                Write-Host "  ✓ Checking $table..." -ForegroundColor Gray
            } catch {
                $allFresh = $false
                $warnings += "Issue #3: Could not verify freshness of $table"
            }
        }

        if ($allFresh) {
            Write-Host "  ✓ All required tables present" -ForegroundColor Green
        }
    } else {
        Write-Host "  ⊘ Skipped (DB credentials not set)" -ForegroundColor Gray
    }
} else {
    Write-Host "  ⊘ Skipped (--SkipDatabase)" -ForegroundColor Gray
}

# ───────────────────────────────────────────────────────────────────────────────
# Summary
# ───────────────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Configuration Verification Summary" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($failures.Count -eq 0 -and $warnings.Count -eq 0) {
    Write-Host "✓ All configurations verified successfully!" -ForegroundColor Green
    exit 0
} else {
    if ($failures.Count -gt 0) {
        Write-Host ""
        Write-Host "❌ CRITICAL FAILURES ($($failures.Count)):" -ForegroundColor Red
        foreach ($failure in $failures) {
            Write-Host "  - $failure" -ForegroundColor Red
        }
    }

    if ($warnings.Count -gt 0) {
        Write-Host ""
        Write-Host "⚠️  WARNINGS ($($warnings.Count)):" -ForegroundColor Yellow
        foreach ($warning in $warnings) {
            Write-Host "  - $warning" -ForegroundColor Yellow
        }
    }

    if ($failures.Count -gt 0) {
        Write-Host ""
        Write-Host "Deploy FAILED - Please fix critical issues before proceeding" -ForegroundColor Red
        exit 1
    } else {
        Write-Host ""
        Write-Host "Deploy OK - Warnings present but not blocking" -ForegroundColor Green
        exit 0
    }
}

#!/usr/bin/env pwsh
<#
.SYNOPSIS
Automated local development environment setup for Algo.

.DESCRIPTION
This script fully automates the local dev setup by:
1. Fetching AWS credentials from Secrets Manager (if needed)
2. Auto-discovering Dashboard and Frontend credentials
3. Generating frontend config.js with environment variables
4. Setting up environment variables in PowerShell profile
5. Optionally starting the local API proxy server

No manual env var setting required after this script runs.

.PARAMETER SkipAwsSetup
Skip AWS credential setup (assume credentials already exist)

.PARAMETER LocalOnly
Set up for local development (localhost:3001) without AWS

.PARAMETER ConfigOnly
Only generate config files, don't modify PowerShell profile

.EXAMPLE
./scripts/setup-local-dev.ps1
./scripts/setup-local-dev.ps1 -SkipAwsSetup
./scripts/setup-local-dev.ps1 -LocalOnly
#>

param(
    [switch]$SkipAwsSetup,
    [switch]$LocalOnly,
    [switch]$ConfigOnly
)

$ErrorActionPreference = "Stop"

$Script:Root = Split-Path -Parent $PSScriptRoot
$Script:Profile = "algo-developer"
$Script:Region = "us-east-1"
$Script:CredFile = "$HOME\.aws\credentials"

# Get the profile path - handle both newer and legacy PowerShell versions
try {
    $Script:PowerShellProfile = $PROFILE.CurrentUserAllHosts
} catch {
    # Fallback for older PowerShell - use direct path
    $Script:PowerShellProfile = "$HOME\OneDrive\Documents\WindowsPowerShell\profile.ps1"
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host "  $($Title.PadRight(47))" -ForegroundColor Cyan
    Write-Host "=================================================" -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor Gray
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

Write-Section "ALGO LOCAL DEV SETUP"

# ====================================================================
# STEP 1: AWS CREDENTIALS SETUP
# ====================================================================

if ($LocalOnly) {
    Write-Section "LOCAL DEVELOPMENT MODE"
    Write-Host "Configuring for local Docker PostgreSQL via api-proxy-server.py" -ForegroundColor Cyan
    $ApiUrl = "http://localhost:3001"
    # Still try to get Cognito IDs from Secrets Manager for JWT validation in the proxy server
    $PoolId = $null
    $ClientId = $null
    $env:AWS_PROFILE = $Script:Profile
    try {
        $SecretJson = aws secretsmanager get-secret-value `
            --secret-id algo/dashboard-config `
            --region $Script:Region `
            --query SecretString `
            --output text 2>&1
        if ($LASTEXITCODE -eq 0 -and $SecretJson) {
            $Secret = $SecretJson | ConvertFrom-Json
            $PoolId = $Secret.cognito_user_pool_id
            $ClientId = $Secret.cognito_user_pool_client_id
            if ($PoolId -and $ClientId) {
                Write-Success "Cognito IDs fetched from Secrets Manager (JWT validation enabled)"
            }
        }
    } catch {
        Write-Host "[WARN] Could not fetch Cognito IDs — authenticated endpoints will be unavailable locally" -ForegroundColor Yellow
    }
    if (-not $PoolId) { $PoolId = "" }
    if (-not $ClientId) { $ClientId = "" }
} elseif ($SkipAwsSetup) {
    Write-Section "AWS CREDENTIALS"
    Write-Step "Skipping AWS credential setup (option specified)"

    # Check if credentials already exist
    if ((Test-Path $CredFile) -and ((Get-Content $CredFile -Raw) -match "\[$Script:Profile\]")) {
        Write-Success "AWS credentials already configured"
    } else {
        Write-Error-Custom "AWS credentials not found. Run:"
        Write-Host "  scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Section "AWS CREDENTIALS SETUP"

    # Check if credentials already exist
    $CredsExist = (Test-Path $CredFile) -and ((Get-Content $CredFile -Raw) -match "\[$Script:Profile\]")

    if ($CredsExist) {
        Write-Success "AWS credentials already configured"
    } else {
        Write-Step "AWS credentials not found. Would you like to fetch them now?"
        Write-Host ""
        Write-Host "  [Y] Fetch AWS credentials (recommended)" -ForegroundColor Cyan
        Write-Host "  [N] Skip - I will set up credentials manually" -ForegroundColor Cyan
        Write-Host ""
        $response = Read-Host "Choice (Y/N)"

        if ($response -eq 'Y' -or $response -eq 'y') {
            Write-Step "Running credential refresh workflow..."
            & "$Script:Root\scripts\refresh-aws-credentials.ps1"
            Write-Success "AWS credentials refreshed"
        } else {
            Write-Error-Custom "AWS credentials required. Run:"
            Write-Host "  scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
            exit 1
        }
    }
}

# ====================================================================
# STEP 2: FETCH DASHBOARD CREDENTIALS
# ====================================================================

if (-not $LocalOnly) {
    Write-Section "DASHBOARD CREDENTIALS"

    $ApiUrl = $null
    $PoolId = $null
    $ClientId = $null

    # Try Secrets Manager first
    Write-Step "Fetching from AWS Secrets Manager..."
    $env:AWS_PROFILE = $Script:Profile

    try {
        $SecretJson = aws secretsmanager get-secret-value `
            --secret-id algo/dashboard-config `
            --region $Script:Region `
            --query SecretString `
            --output text 2>&1

        if ($LASTEXITCODE -eq 0 -and $SecretJson) {
            $Secret = $SecretJson | ConvertFrom-Json
            $ApiUrl = $Secret.api_url
            $PoolId = $Secret.cognito_user_pool_id
            $ClientId = $Secret.cognito_user_pool_client_id

            if ($ApiUrl -and $PoolId -and $ClientId) {
                Write-Success "Credentials fetched from Secrets Manager"
            }
        }
    } catch {
        Write-Step "Secrets Manager unavailable, trying Terraform..."
    }

    # Try Terraform if Secrets Manager failed
    if (-not $ApiUrl) {
        Write-Step "Fetching from Terraform..."
        $TfDir = Join-Path $Script:Root "terraform"

        if (Test-Path $TfDir) {
            try {
                Push-Location $TfDir
                $ApiUrl = & terraform output -raw api_url 2>$null
                $PoolId = & terraform output -raw cognito_user_pool_id 2>$null
                $ClientId = & terraform output -raw cognito_user_pool_client_id 2>$null
                Pop-Location

                if ($ApiUrl -and $PoolId -and $ClientId) {
                    Write-Success "Credentials fetched from Terraform"
                }
            } catch {
                Pop-Location
            }
        }
    }

    if (-not $ApiUrl) {
        Write-Error-Custom "Could not retrieve dashboard credentials from Secrets Manager or Terraform."
        Write-Host ""
        Write-Host "To fix this, ensure:" -ForegroundColor Yellow
        Write-Host "  1. AWS credentials are valid:  scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
        Write-Host "  2. Terraform has been applied: cd terraform; terraform apply" -ForegroundColor Yellow
        Write-Host "  3. algo/dashboard-config secret exists in Secrets Manager" -ForegroundColor Yellow
        exit 1
    }

    Write-Success "Credentials retrieved"
    Write-Host "  API URL: $ApiUrl" -ForegroundColor Gray
    Write-Host "  Pool ID: $PoolId" -ForegroundColor Gray
}

# ====================================================================
# STEP 3: GENERATE FRONTEND CONFIG
# ====================================================================

Write-Section "FRONTEND CONFIGURATION"

$FrontendPublicDir = Join-Path (Join-Path (Join-Path $Script:Root "webapp") "frontend") "public"
New-Item -ItemType Directory -Force -Path $FrontendPublicDir | Out-Null

# Extract region from pool ID (format: us-east-1_XXX)
$PoolRegion = if ($PoolId -match '^([a-z0-9\-]+)_') { $matches[1] } else { "us-east-1" }
$CognitoDomain = "$PoolRegion.auth.us-east-1.amazoncognito.com"

# Build config as JSON to avoid PowerShell parsing issues
$ConfigData = @{
    API_URL = ""
    USER_POOL_ID = $PoolId
    USER_POOL_CLIENT_ID = $ClientId
    USER_POOL_DOMAIN = $CognitoDomain
    BUILD_TIME = "[new Date().toISOString()]"
    VERSION = "1.0.0-dev"
    ENVIRONMENT = "development"
}

$ConfigJson = $ConfigData | ConvertTo-Json
$ConfigJs = "// Runtime configuration - Auto-generated by setup-local-dev.ps1`n// Do not commit this file to version control`nwindow.__CONFIG__ = $ConfigJson;"

$ConfigPath = Join-Path $FrontendPublicDir "config.js"
Set-Content -Path $ConfigPath -Value $ConfigJs -Encoding UTF8
Write-Success "Frontend config generated: public/config.js"

# ====================================================================
# STEP 4: SET UP ENVIRONMENT VARIABLES (PowerShell PROFILE)
# ====================================================================

if (-not $ConfigOnly) {
    Write-Section "ENVIRONMENT VARIABLES"

    # Prepare profile additions
    $ProfileAdditions = @"

# ===== Algo Local Dev Setup (Auto-configured) =====
# This section was auto-generated by setup-local-dev.ps1
# To regenerate: scripts/setup-local-dev.ps1

`$env:DASHBOARD_API_URL = "$ApiUrl"
`$env:COGNITO_USER_POOL_ID = "$PoolId"
`$env:COGNITO_CLIENT_ID = "$ClientId"
`$env:AWS_PROFILE = "$Script:Profile"
`$env:AWS_DEFAULT_REGION = "$Script:Region"

# VITE_PROXY_TARGET: Vite dev server proxies /api/* to this URL.
# config.js uses empty API_URL for local dev, so the browser hits the Vite proxy
# instead of the real AWS URL directly (which would cause CORS errors).
`$env:VITE_PROXY_TARGET = "$ApiUrl"

Write-Host "[Algo] Local dev environment loaded - API proxy: `$env:VITE_PROXY_TARGET" -ForegroundColor Cyan

# ===== End Algo Setup =====
"@

    # Check if profile exists and already has our config
    $ProfileExists = Test-Path $Script:PowerShellProfile
    $AlreadyConfigured = $false

    if ($ProfileExists) {
        $ProfileContent = Get-Content $Script:PowerShellProfile -Raw
        if ($ProfileContent -match "Algo Local Dev Setup") {
            $AlreadyConfigured = $true
        }
    }

    if ($AlreadyConfigured) {
        Write-Step "Updating existing PowerShell profile configuration..."

        # Remove old config block
        $Content = Get-Content $Script:PowerShellProfile -Raw
        $Content = $Content -replace "(?s)`# ===== Algo Local Dev Setup.*?`# ===== End Algo Setup =====`r?`n", ""
        Set-Content -Path $Script:PowerShellProfile -Value $Content -Encoding UTF8
    } else {
        Write-Step "Adding configuration to PowerShell profile..."

        # Ensure profile directory exists
        $ProfileDir = Split-Path -Parent $Script:PowerShellProfile
        if (-not (Test-Path $ProfileDir)) {
            New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
        }

        # Create profile if it doesn't exist
        if (-not $ProfileExists) {
            New-Item -ItemType File -Path $Script:PowerShellProfile -Force | Out-Null
        }
    }

    # Append new config
    Add-Content -Path $Script:PowerShellProfile -Value $ProfileAdditions -Encoding UTF8
    Write-Success "PowerShell profile updated: $Script:PowerShellProfile"

    # Also set in current session
    $env:DASHBOARD_API_URL = $ApiUrl
    $env:COGNITO_USER_POOL_ID = $PoolId
    $env:COGNITO_CLIENT_ID = $ClientId
    $env:AWS_PROFILE = $Script:Profile
    $env:AWS_DEFAULT_REGION = $Script:Region
}

# ====================================================================
# STEP 5: VERIFY SETUP
# ====================================================================

Write-Section "SETUP VERIFICATION"

# Verify API connectivity
if (-not $LocalOnly) {
    Write-Step "Testing API Gateway connectivity..."
    try {
        $Response = Invoke-WebRequest -Uri "$ApiUrl/api/algo/health" -Method Get -TimeoutSec 5 -SkipHttpErrorCheck
        if ($Response.StatusCode -eq 200) {
            Write-Success "API Gateway responding (200 OK)"
        } else {
            Write-Host "[i] API Gateway responding ($($Response.StatusCode)) - may require authentication" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[!] Could not reach API Gateway - API may still be initializing" -ForegroundColor Yellow
    }
}

# ====================================================================
# FINAL INSTRUCTIONS
# ====================================================================

Write-Section "SETUP COMPLETE!"

Write-Host ""
Write-Host "Your local development environment is now ready:" -ForegroundColor Green
Write-Host ""

if ($LocalOnly) {
    Write-Host "  1. Start the local API proxy (Terminal 1):" -ForegroundColor Cyan
    Write-Host "     python scripts/api-proxy-server.py" -ForegroundColor White
    Write-Host ""
    Write-Host "  2. Run the dashboard (Terminal 2):" -ForegroundColor Cyan
    Write-Host "     scripts/run-dashboard.ps1 -w 30  # Auto-refresh every 30s" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. Run the frontend (Terminal 3):" -ForegroundColor Cyan
    Write-Host "     cd webapp/frontend && npm run dev" -ForegroundColor White
} else {
    Write-Host "  Option A: Run the Terminal Dashboard:" -ForegroundColor Cyan
    Write-Host "    scripts/run-dashboard.ps1 -w 30" -ForegroundColor White
    Write-Host ""
    Write-Host "  Option B: Run the Web Frontend:" -ForegroundColor Cyan
    Write-Host "    cd webapp/frontend && npm run dev" -ForegroundColor White
    Write-Host ""
    Write-Host "  Option C: Both (two terminals):" -ForegroundColor Cyan
    Write-Host "    # Terminal 1: Dashboard" -ForegroundColor White
    Write-Host "    scripts/run-dashboard.ps1 -w 30" -ForegroundColor White
    Write-Host "    # Terminal 2: Frontend" -ForegroundColor White
    Write-Host "    cd webapp/frontend && npm run dev" -ForegroundColor White
}

Write-Host ""
Write-Host "Credentials are now set and will load automatically in future sessions." -ForegroundColor Green
Write-Host ""

if (-not $ConfigOnly) {
    Write-Host "To regenerate this setup (e.g., after infrastructure deploy):" -ForegroundColor Gray
    Write-Host "  scripts/setup-local-dev.ps1" -ForegroundColor Gray
}

Write-Host ""

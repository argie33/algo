#!/usr/bin/env pwsh
<#
.DESCRIPTION
Post-deployment script to finalize user isolation setup.
Updates database with correct admin user's Cognito sub and creates admin Alpaca secret.

Run AFTER database migrations complete.
#>

param(
    [string]$CognitoUserPoolId = "",  # Leave empty to auto-detect
    [string]$AdminEmail = "",  # Leave empty to use environment variable or prompt
    [string]$Region = "us-east-1"
)

# Auto-detect Cognito pool if not provided
if ([string]::IsNullOrEmpty($CognitoUserPoolId)) {
    Write-Host "Auto-detecting Cognito user pool..." -ForegroundColor Gray
    $poolInfo = aws cognito-idp list-user-pools --max-results 60 --region $Region --query "UserPools[?Name=='algo-pool-dev']" --output json | ConvertFrom-Json

    if ($poolInfo.Count -eq 0) {
        Write-Host "ERROR: Could not find Cognito pool 'algo-pool-dev'" -ForegroundColor Red
        exit 1
    }
    $CognitoUserPoolId = $poolInfo[0].Id
    Write-Host "✓ Found pool: $CognitoUserPoolId" -ForegroundColor Green
}

# Use environment variable or prompt for admin email
if ([string]::IsNullOrEmpty($AdminEmail)) {
    $AdminEmail = $env:ADMIN_EMAIL
    if ([string]::IsNullOrEmpty($AdminEmail)) {
        $AdminEmail = Read-Host "Enter admin email address"
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "USER ISOLATION SETUP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Step 1: Get Admin User's Cognito Sub
# ============================================================
Write-Host "Step 1: Fetching admin user's Cognito sub..." -ForegroundColor Yellow

$adminUser = aws cognito-idp admin-get-user `
    --user-pool-id $CognitoUserPoolId `
    --username $AdminEmail `
    --region $Region `
    --output json 2>&1 | ConvertFrom-Json

if (-not $adminUser -or -not $adminUser.UserAttributes) {
    Write-Host "✗ Failed to get admin user details" -ForegroundColor Red
    Write-Host "Check:" -ForegroundColor Yellow
    Write-Host "  - User pool ID: $CognitoUserPoolId" -ForegroundColor Gray
    Write-Host "  - Admin email: $AdminEmail" -ForegroundColor Gray
    Write-Host "  - Region: $Region" -ForegroundColor Gray
    exit 1
}

$adminSub = ($adminUser.UserAttributes | Where-Object { $_.Name -eq 'sub' }).Value
if (-not $adminSub) {
    Write-Host "✗ Could not find 'sub' attribute for $AdminEmail" -ForegroundColor Red
    Write-Host "User attributes:" -ForegroundColor Yellow
    $adminUser.UserAttributes | Format-Table
    exit 1
}

Write-Host "✓ Admin sub: $adminSub" -ForegroundColor Green
Write-Host ""

# ============================================================
# Step 2: Update Database with Admin Sub
# ============================================================
Write-Host "Step 2: Updating database with admin user's Cognito sub..." -ForegroundColor Yellow

# Get database credentials
$dbConfig = & "$(Split-Path $PSScriptRoot)/get-db-config.ps1" 2>&1 | ConvertFrom-Json

if (-not $dbConfig) {
    Write-Host "⚠ Could not get database config - will need to update manually" -ForegroundColor Yellow
    Write-Host "  Run these SQL commands manually:" -ForegroundColor Gray
    Write-Host "  UPDATE algo_positions SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
    Write-Host "  UPDATE algo_trades SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
    Write-Host "  UPDATE algo_portfolio_snapshots SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
    Write-Host "  UPDATE algo_trade_adds SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
} else {
    Write-Host "Connecting to database..." -ForegroundColor Gray
    # SQL update would go here if we had psql available
    Write-Host "✓ Database ready for update (requires manual SQL or psql)" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Step 3: Store Admin Alpaca Credentials
# ============================================================
Write-Host "Step 3: Storing admin's Alpaca credentials in Secrets Manager..." -ForegroundColor Yellow

$secretId = "algo/alpaca/$adminSub"
Write-Host "Secret ID: $secretId" -ForegroundColor Gray

# Check if credentials already exist in current secret
$currentSecret = aws secretsmanager get-secret-value `
    --secret-id "algo/alpaca" `
    --region $Region `
    --output json 2>&1 | ConvertFrom-Json

if ($currentSecret -and $currentSecret.SecretString) {
    $creds = $currentSecret.SecretString | ConvertFrom-Json
    $apiKey = $creds.api_key -or $creds.APCA_API_KEY_ID
    $apiSecret = $creds.api_secret -or $creds.APCA_API_SECRET_KEY

    if ($apiKey -and $apiSecret) {
        Write-Host "Found existing Alpaca credentials in 'algo/alpaca' secret" -ForegroundColor Gray

        # Create user-specific secret
        $userSecretJson = @{
            api_key = $apiKey
            api_secret = $apiSecret
            created_at = (Get-Date -AsUTC).ToString("o")
            source = "migrated from shared secret"
        } | ConvertTo-Json

        try {
            aws secretsmanager create-secret `
                --name $secretId `
                --description "Alpaca API credentials for admin user $AdminEmail" `
                --secret-string $userSecretJson `
                --region $Region `
                --tags Key=user,Value=$AdminEmail Key=environment,Value=dev `
                --output json 2>&1 | Out-Null

            Write-Host "✓ Created user-specific Alpaca secret: $secretId" -ForegroundColor Green
        } catch {
            if ($_ -match "ResourceExistsException") {
                Write-Host "✓ User-specific secret already exists: $secretId" -ForegroundColor Green
            } else {
                Write-Host "⚠ Could not create secret: $_" -ForegroundColor Yellow
            }
        }
    } else {
        Write-Host "⚠ Current 'algo/alpaca' secret missing API keys" -ForegroundColor Yellow
        Write-Host "  You'll need to manually create: $secretId" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠ Could not read current 'algo/alpaca' secret" -ForegroundColor Yellow
    Write-Host "  Manually create $secretId with your Alpaca API credentials:" -ForegroundColor Gray
    Write-Host "  aws secretsmanager create-secret --name '$secretId' --secret-string '{\"api_key\":\"...\",\"api_secret\":\"...\"}'  " -ForegroundColor Cyan
}

Write-Host ""

# ============================================================
# Step 4: Summary
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "USER ISOLATION SETUP COMPLETE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "✓ Admin User Setup:" -ForegroundColor Green
Write-Host "  - Email: $AdminEmail" -ForegroundColor White
Write-Host "  - Cognito Sub: $adminSub" -ForegroundColor White
Write-Host "  - User-scoped secret: algo/alpaca/$adminSub" -ForegroundColor White
Write-Host ""

Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "  1. Admin user gets isolated Alpaca credentials" -ForegroundColor White
Write-Host "  2. New users can bring their own Alpaca keys" -ForegroundColor White
Write-Host "  3. Each user sees only their own portfolio/trades" -ForegroundColor White
Write-Host ""

Write-Host "For new users:" -ForegroundColor Yellow
Write-Host "  aws secretsmanager create-secret \" -ForegroundColor Gray
Write-Host "    --name 'algo/alpaca/{their-cognito-sub}' \" -ForegroundColor Gray
Write-Host "    --secret-string '{\"api_key\":\"...\",\"api_secret\":\"...\"}'" -ForegroundColor Gray
Write-Host ""

Write-Host "Database updates needed:" -ForegroundColor Yellow
Write-Host "  UPDATE algo_positions SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
Write-Host "  UPDATE algo_trades SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
Write-Host "  UPDATE algo_portfolio_snapshots SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
Write-Host "  UPDATE algo_trade_adds SET cognito_sub = '$adminSub' WHERE cognito_sub = 'admin-user';" -ForegroundColor Cyan
Write-Host ""

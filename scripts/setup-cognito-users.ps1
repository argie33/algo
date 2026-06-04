# Setup Cognito users and groups for algo trading platform
param(
    [string]$UserPoolId = "",  # Leave empty to auto-detect
    [string]$AdminEmail = "",  # Leave empty to use environment variable (required)
    [string]$TraderEmail = "",  # Leave empty to use environment variable (required)
    [string]$AwsRegion = "us-east-1",
    [string]$Environment = "dev"
)

# Load infrastructure names from Terraform outputs
$HelperScript = Join-Path (Split-Path $PSScriptRoot) "scripts" "get-terraform-outputs.ps1"
if (Test-Path $HelperScript) {
    . $HelperScript -Environment $Environment -Region $AwsRegion
}

$PoolName = $env:COGNITO_POOL_NAME
if ([string]::IsNullOrEmpty($PoolName)) { $PoolName = "algo-pool-$Environment" }

# Auto-detect Cognito pool if not provided
if ([string]::IsNullOrEmpty($UserPoolId)) {
    Write-Host "Auto-detecting Cognito user pool '$PoolName'..." -ForegroundColor Gray
    $poolInfo = aws cognito-idp list-user-pools --max-results 60 --region $AwsRegion --query "UserPools[?Name=='$PoolName']" --output json | ConvertFrom-Json

    if ($poolInfo.Count -eq 0) {
        Write-Host "ERROR: Could not find Cognito pool '$PoolName'" -ForegroundColor Red
        exit 1
    }
    $UserPoolId = $poolInfo[0].Id
    Write-Host "✓ Found pool: $UserPoolId" -ForegroundColor Green
}

# Use environment variables for email addresses (no defaults)
if ([string]::IsNullOrEmpty($AdminEmail)) {
    $AdminEmail = $env:ADMIN_EMAIL
    if ([string]::IsNullOrEmpty($AdminEmail)) {
        Write-Host "ERROR: ADMIN_EMAIL environment variable not set. Use: `$env:ADMIN_EMAIL='your@email.com'" -ForegroundColor Red
        exit 1
    }
}

if ([string]::IsNullOrEmpty($TraderEmail)) {
    $TraderEmail = $env:TRADER_EMAIL
    if ([string]::IsNullOrEmpty($TraderEmail)) {
        Write-Host "ERROR: TRADER_EMAIL environment variable not set. Use: `$env:TRADER_EMAIL='your@email.com'" -ForegroundColor Red
        exit 1
    }
}

Write-Host "========================================================================"
Write-Host "  COGNITO USER `& GROUP SETUP FOR ALGO TRADING PLATFORM"
Write-Host "========================================================================"
Write-Host ""
Write-Host "Configuration:"
Write-Host "  User Pool ID: $UserPoolId"
Write-Host "  Admin Email: $AdminEmail"
Write-Host "  Trader Email: $TraderEmail"
Write-Host "  AWS Region: $AwsRegion"

# Create admin group
Write-Host ""
Write-Host "[1] Creating Cognito Groups"
Write-Host "────────────────────────────────────────────────────────────────"
aws cognito-idp create-group --user-pool-id $UserPoolId --group-name admin --description "Full access: system diagnostics, admin dashboards, configuration" --region $AwsRegion 2>$null
Write-Host "✓ Admin group"

aws cognito-idp create-group --user-pool-id $UserPoolId --group-name trader --description "Personal portfolio access: trades, positions, performance" --region $AwsRegion 2>$null
Write-Host "✓ Trader group"

# Create users
Write-Host ""
Write-Host "[2] Creating/Verifying Users"
Write-Host "────────────────────────────────────────────────────────────────"
aws cognito-idp admin-create-user --user-pool-id $UserPoolId --username $AdminEmail --user-attributes Name=email,Value=$AdminEmail Name=email_verified,Value=true --message-action SUPPRESS --region $AwsRegion 2>$null
Write-Host "✓ Admin user: $AdminEmail"

aws cognito-idp admin-create-user --user-pool-id $UserPoolId --username $TraderEmail --user-attributes Name=email,Value=$TraderEmail Name=email_verified,Value=true --message-action SUPPRESS --region $AwsRegion 2>$null
Write-Host "✓ Trader user: $TraderEmail"

# Add users to groups
Write-Host ""
Write-Host "[3] Adding Users to Groups"
Write-Host "────────────────────────────────────────────────────────────────"
aws cognito-idp admin-add-user-to-group --user-pool-id $UserPoolId --username $AdminEmail --group-name admin --region $AwsRegion 2>$null
Write-Host "✓ $AdminEmail -> admin group"

aws cognito-idp admin-add-user-to-group --user-pool-id $UserPoolId --username $TraderEmail --group-name trader --region $AwsRegion 2>$null
Write-Host "✓ $TraderEmail -> trader group"

# Verify
Write-Host ""
Write-Host "[4] Verifying Setup"
Write-Host "────────────────────────────────────────────────────────────────"
$users = aws cognito-idp list-users --user-pool-id $UserPoolId --query 'Users[*].Username' --output text --region $AwsRegion
Write-Host "Registered users: $users"

Write-Host ""
Write-Host "========================================================================"
Write-Host "  SETUP COMPLETE"
Write-Host "========================================================================"
Write-Host ""
Write-Host "User Roles:"
Write-Host "  Admin:  $AdminEmail"
Write-Host "    - Full access to all endpoints"
Write-Host "    - System diagnostics, admin dashboards, configuration"
Write-Host ""
Write-Host "  Trader: $TraderEmail"
Write-Host "    - Personal portfolio access only"
Write-Host "    - Trades, positions, performance, public market data"
Write-Host ""
Write-Host "Next: Users can log in and dashboard will load with proper permissions"
Write-Host ""

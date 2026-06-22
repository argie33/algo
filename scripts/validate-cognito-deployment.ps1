param(
    [Parameter(Mandatory=$true)] [string]$EnvironmentName,
    [Parameter(Mandatory=$true)] [string]$CognitoUserPoolId,
    [Parameter(Mandatory=$true)] [string]$CognitoClientId,
    [Parameter(Mandatory=$false)] [string]$AwsRegion = "us-east-1"
)

# Validates Cognito configuration after Terraform apply.
# Blocks deployment if the user pool or client ID is missing or misconfigured.

$ErrorActionPreference = "Stop"

Write-Host "=== Cognito Deployment Validation ===" -ForegroundColor Cyan
Write-Host "Environment : $EnvironmentName"
Write-Host "User Pool ID: $CognitoUserPoolId"
Write-Host "Client ID   : $CognitoClientId"
Write-Host "Region      : $AwsRegion"
Write-Host ""

# 1. Verify user pool exists
Write-Host "Checking user pool exists..."
try {
    $pool = aws cognito-idp describe-user-pool `
        --user-pool-id $CognitoUserPoolId `
        --region $AwsRegion `
        --output json 2>&1 | ConvertFrom-Json
    $poolName = $pool.UserPool.Name
    Write-Host "[OK] User pool found: $poolName" -ForegroundColor Green
} catch {
    Write-Error "CRITICAL: Cognito user pool '$CognitoUserPoolId' not found in region $AwsRegion. Deployment blocked."
    exit 1
}

# 2. Verify client ID belongs to this pool
Write-Host "Checking client ID belongs to pool..."
try {
    $client = aws cognito-idp describe-user-pool-client `
        --user-pool-id $CognitoUserPoolId `
        --client-id $CognitoClientId `
        --region $AwsRegion `
        --output json 2>&1 | ConvertFrom-Json
    $clientName = $client.UserPoolClient.ClientName
    Write-Host "[OK] Client found: $clientName" -ForegroundColor Green
} catch {
    Write-Error "CRITICAL: Cognito client '$CognitoClientId' not found in pool '$CognitoUserPoolId'. Deployment blocked."
    exit 1
}

Write-Host ""
Write-Host "[OK] Cognito validation passed for $EnvironmentName environment." -ForegroundColor Green
exit 0

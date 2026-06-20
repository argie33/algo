#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Setting up dashboard Cognito authentication..." -ForegroundColor Cyan

if (-not $env:AWS_PROFILE) {
    $env:AWS_PROFILE = "algo-developer"
    Write-Host "Set AWS_PROFILE=algo-developer" -ForegroundColor Gray
}

Write-Host "Fetching dashboard credentials from Secrets Manager..." -ForegroundColor Gray
try {
    $SecretJson = aws secretsmanager get-secret-value `
        --secret-id algo/dashboard-config `
        --region us-east-1 `
        --query SecretString `
        --output text 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed: $SecretJson"
    }

    $Secret = $SecretJson | ConvertFrom-Json
} catch {
    Write-Host "ERROR: Could not fetch dashboard credentials from Secrets Manager" -ForegroundColor Red
    Write-Host "Make sure algo/dashboard-config secret exists with these fields:" -ForegroundColor Yellow
    Write-Host "  - cognito_username" -ForegroundColor Yellow
    Write-Host "  - cognito_password" -ForegroundColor Yellow
    exit 1
}

$CognitoUsername = $Secret.cognito_username
$CognitoPassword = $Secret.cognito_password
$ApiUrl = $Secret.api_url
$PoolId = $Secret.cognito_user_pool_id
$ClientId = $Secret.cognito_user_pool_client_id

if (-not ($CognitoUsername -and $CognitoPassword)) {
    Write-Host "ERROR: Missing cognito_username or cognito_password in secret" -ForegroundColor Red
    exit 1
}

$env:COGNITO_USERNAME = $CognitoUsername
$env:COGNITO_PASSWORD = $CognitoPassword
$env:DASHBOARD_API_URL = $ApiUrl
$env:COGNITO_USER_POOL_ID = $PoolId
$env:COGNITO_CLIENT_ID = $ClientId

Write-Host "Dashboard authentication configured:" -ForegroundColor Green
Write-Host "You can now run: python -m tools.dashboard" -ForegroundColor Green

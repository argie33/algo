#!/usr/bin/env pwsh
# Refresh local AWS credentials for the algo-developer profile.
# Reads IaC-managed credentials from Secrets Manager via AWS CLI (OIDC or local AWS profile).
#
# Usage: scripts/refresh-aws-credentials.ps1
#
# Requires: AWS CLI v2 configured with credentials or AWS_PROFILE set

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Profile = "algo-developer"
$Region  = "us-east-1"
$CredFile = "$HOME\.aws\credentials"

Write-Host "Refreshing $Profile credentials from Secrets Manager..." -ForegroundColor Cyan

# Fetch developer credentials from Secrets Manager
Write-Host "Fetching credentials from Secrets Manager..." -ForegroundColor Gray
$SecretJson = aws secretsmanager get-secret-value `
    --secret-id algo/developer-credentials `
    --region $Region `
    --query SecretString `
    --output text 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to fetch credentials from Secrets Manager.`nError: $SecretJson`n`nTroubleshooting:`n- Ensure AWS CLI is configured: aws sts get-caller-identity`n- Ensure OIDC role has Secrets Manager access`n- Check secret name: algo/developer-credentials"
    exit 1
}

# Parse the secret JSON
try {
    $Secret = $SecretJson | ConvertFrom-Json
} catch {
    Write-Error "Failed to parse credentials JSON: $_"
    exit 1
}

$AccessKeyId = $Secret.access_key_id
$SecretKey = $Secret.secret_access_key

if (-not $AccessKeyId -or -not $SecretKey) {
    Write-Error "Credentials missing from secret. Expected 'access_key_id' and 'secret_access_key' fields."
    exit 1
}

# Ensure ~/.aws directory exists
$AwsDir = Split-Path $CredFile -Parent
New-Item -ItemType Directory -Force -Path $AwsDir | Out-Null

# Read existing credentials and replace or add the algo-developer block
$Existing = if (Test-Path $CredFile) {
    $r = Get-Content $CredFile -Raw
    if ($r) { $r } else { "" }
} else {
    ""
}

$NewBlock = @"
[$Profile]
aws_access_key_id = $AccessKeyId
aws_secret_access_key = $SecretKey
region = $Region
"@

# Remove existing algo-developer block if present
$Pattern = "(?ms)\[$Profile\][^\[]*"
$Updated = if ($Existing -match $Pattern) {
    $Existing -replace $Pattern, ""
} else {
    $Existing
}

# Trim trailing whitespace and append new block
$Updated = $Updated.TrimEnd() + "`n`n" + $NewBlock + "`n"

# Write credentials file (UTF-8 without BOM — botocore rejects BOM in credentials files)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CredFile, $Updated, $utf8NoBom)

Write-Host "✓ Credentials written to $CredFile" -ForegroundColor Green

# Check credential status from the secret
if ($Secret.status) {
    if ($Secret.status -eq "dual_credentials_active") {
        Write-Host "`n[INFO] Grace period active" -ForegroundColor Yellow
        Write-Host "  Both old and new keys are valid" -ForegroundColor Yellow
        if ($Secret.old_key_cleanup_date) {
            Write-Host "  Old key cleanup date: $($Secret.old_key_cleanup_date)" -ForegroundColor Yellow
            Write-Host "  Action: Update credentials before cleanup date" -ForegroundColor Yellow
        }
    }
}

# Verify it works
Write-Host "`nVerifying credentials..." -ForegroundColor Gray
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region

# Try verification with a short delay for IAM consistency
$MaxRetries = 3
$Retry = 0
$Identity = $null

while ($Retry -lt $MaxRetries) {
    $Identity = aws sts get-caller-identity --profile $Profile 2>&1
    if ($LASTEXITCODE -eq 0) {
        break
    }
    $Retry++
    if ($Retry -lt $MaxRetries) {
        Write-Host "Waiting for credentials to propagate (attempt $($Retry + 1)/$MaxRetries)..." -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

if ($LASTEXITCODE -eq 0) {
    $IdentityObj = $Identity | ConvertFrom-Json
    $Arn = $IdentityObj.Arn
    $Account = $IdentityObj.Account

    Write-Host "`n[OK] Credentials verified successfully" -ForegroundColor Green
    Write-Host ('  Profile: ' + $Profile) -ForegroundColor Green
    Write-Host ('  IAM ARN: ' + $Arn) -ForegroundColor Green
    Write-Host ('  Account: ' + $Account) -ForegroundColor Green
    Write-Host ('  File: ' + $CredFile) -ForegroundColor Green
    Write-Host ('  Access Key: ' + $AccessKeyId) -ForegroundColor Green
} else {
    Write-Warning ('Credentials written to ' + $CredFile + ' but verification failed.')
    Write-Warning ('Details: ' + $Identity)
    Write-Warning ''
    Write-Warning 'The IAM key may need a moment to propagate (usually less than 1 minute).'
    Write-Warning ('Retry: aws sts get-caller-identity --profile ' + $Profile)
    exit 1
}

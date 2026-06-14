#!/usr/bin/env pwsh
# Refresh local AWS credentials for the algo-developer profile.
# Reads IaC-managed credentials from Secrets Manager via GitHub Actions OIDC.
#
# Usage: scripts/refresh-aws-credentials.ps1
#
# Requires: gh CLI authenticated (gh auth status)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Profile = "algo-developer"
$Region  = "us-east-1"
$CredFile = "$HOME\.aws\credentials"

Write-Host "Refreshing $Profile credentials from IaC (Secrets Manager)..." -ForegroundColor Cyan

# Get the current repository
$RepoPath = & git rev-parse --show-toplevel 2>$null
if (-not $RepoPath) {
    Write-Error "Not in a git repository. Run this script from the project root."
    exit 1
}

# Determine repo owner/name from git remote
$GitRemote = & git config --get remote.origin.url 2>$null
if ($GitRemote -match "github\.com[:/]([^/]+)/([^/\.]+)") {
    $Owner = $Matches[1]
    $Repo = $Matches[2]
} else {
    Write-Error "Could not determine GitHub repo from remote. Ensure 'origin' remote is set."
    exit 1
}

$Repository = "$Owner/$Repo"

# Trigger the credentials export workflow
Write-Host "Triggering refresh-dev-credentials workflow in $Repository..." -ForegroundColor Gray
gh workflow run refresh-dev-credentials.yml --repo $Repository 2>&1 | Write-Host

# Wait for the run to start
Start-Sleep -Seconds 2

# Get the run ID (newest first)
$RunId = gh run list `
    --workflow refresh-dev-credentials.yml `
    --repo $Repository `
    --limit 1 `
    --json databaseId `
    --jq ".[0].databaseId"

if (-not $RunId) {
    Write-Error "Could not find workflow run. Check: gh run list --workflow refresh-dev-credentials.yml --repo $Repository"
    exit 1
}

Write-Host "Workflow run ID: $RunId" -ForegroundColor Gray
Write-Host "Waiting for run to complete (this may take 10-20 seconds)..." -ForegroundColor Gray
gh run watch $RunId --repo $Repository --exit-status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Workflow run $RunId failed. Check: gh run view $RunId --repo $Repository"
    exit 1
}

# Download the credentials artifact
$TmpDir = Join-Path $env:TEMP "algo-aws-creds-$RunId"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

Write-Host "Downloading credentials artifact..." -ForegroundColor Gray
gh run download $RunId `
    --repo $Repository `
    --name dev-credentials `
    --dir $TmpDir 2>&1 | Write-Host

$ArtifactCreds = Join-Path $TmpDir "credentials"
if (-not (Test-Path $ArtifactCreds)) {
    Write-Error "Credentials artifact not found at $ArtifactCreds"
    exit 1
}

# Parse the downloaded credentials
$Content = Get-Content $ArtifactCreds -Raw
$AccessKeyId = if ($Content -match "aws_access_key_id\s*=\s*(\S+)") { $Matches[1] } else { $null }
$SecretKey   = if ($Content -match "aws_secret_access_key\s*=\s*(\S+)") { $Matches[1] } else { $null }

if (-not $AccessKeyId -or -not $SecretKey) {
    Write-Error "Could not parse credentials from artifact"
    exit 1
}

# Ensure ~/.aws directory exists
$AwsDir = Split-Path $CredFile -Parent
New-Item -ItemType Directory -Force -Path $AwsDir | Out-Null

# Read existing credentials and replace or add the algo-developer block
$Existing = if (Test-Path $CredFile) { $r = Get-Content $CredFile -Raw; if ($r) { $r } else { "" } } else { "" }

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

# Clean up temp dir
Remove-Item -Recurse -Force $TmpDir

# Verify it works
Write-Host "Verifying credentials..." -ForegroundColor Gray
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region

# Also check if dashboard credentials are available in Secrets Manager
Write-Host "Checking dashboard configuration in Secrets Manager..." -ForegroundColor Gray
$DashboardConfigJson = aws secretsmanager get-secret-value `
    --secret-id algo/dashboard-config `
    --region $Region `
    --query SecretString `
    --output text 2>&1

if ($LASTEXITCODE -eq 0 -and $DashboardConfigJson -and $DashboardConfigJson -ne "") {
    $DashboardConfig = $DashboardConfigJson | ConvertFrom-Json
    $HasApiUrl = [string]::IsNullOrWhiteSpace($DashboardConfig.api_url) -eq $false
    $HasPoolId = [string]::IsNullOrWhiteSpace($DashboardConfig.cognito_user_pool_id) -eq $false
    $HasClientId = [string]::IsNullOrWhiteSpace($DashboardConfig.cognito_user_pool_client_id) -eq $false

    if ($HasApiUrl -and $HasPoolId -and $HasClientId) {
        Write-Host "[OK] Dashboard config found in Secrets Manager:" -ForegroundColor Green
        Write-Host "  API URL: $($DashboardConfig.api_url)" -ForegroundColor Green
        Write-Host "  Cognito Pool: $($DashboardConfig.cognito_user_pool_id)" -ForegroundColor Green
        Write-Host "  Cognito Client: $($DashboardConfig.cognito_user_pool_client_id)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Dashboard config exists but is incomplete" -ForegroundColor Yellow
        Write-Host "  API URL: $(if ($HasApiUrl) { 'SET' } else { 'MISSING' })" -ForegroundColor Yellow
        Write-Host "  Cognito Pool: $(if ($HasPoolId) { 'SET' } else { 'MISSING' })" -ForegroundColor Yellow
        Write-Host "  Cognito Client: $(if ($HasClientId) { 'SET' } else { 'MISSING' })" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] Dashboard config NOT found in Secrets Manager" -ForegroundColor Yellow
    Write-Host "       This is normal if infrastructure hasn't been deployed yet." -ForegroundColor Yellow
}

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

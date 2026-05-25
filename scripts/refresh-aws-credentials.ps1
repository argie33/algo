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

# Trigger the credentials export workflow
Write-Host "Triggering refresh-dev-credentials workflow..." -ForegroundColor Gray
gh workflow run refresh-dev-credentials.yml --repo argie33/algo

# Wait for the run to start
Start-Sleep -Seconds 5

# Get the run ID
$RunId = gh run list `
    --workflow refresh-dev-credentials.yml `
    --repo argie33/algo `
    --limit 1 `
    --json databaseId `
    --jq ".[0].databaseId"

if (-not $RunId) {
    Write-Error "Could not find workflow run. Check: gh run list --workflow refresh-dev-credentials.yml"
    exit 1
}

Write-Host "Waiting for run $RunId to complete..." -ForegroundColor Gray
gh run watch $RunId --repo argie33/algo --exit-status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Workflow run $RunId failed. Check: gh run view $RunId"
    exit 1
}

# Download the credentials artifact
$TmpDir = Join-Path $env:TEMP "algo-aws-creds-$RunId"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

Write-Host "Downloading credentials artifact..." -ForegroundColor Gray
gh run download $RunId `
    --repo argie33/algo `
    --name dev-credentials `
    --dir $TmpDir

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
$Existing = if (Test-Path $CredFile) { Get-Content $CredFile -Raw } else { "" }

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
Set-Content -Path $CredFile -Value $Updated -Encoding UTF8

# Clean up temp dir
Remove-Item -Recurse -Force $TmpDir

# Verify it works
Write-Host "Verifying credentials..." -ForegroundColor Gray
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region
$Identity = aws sts get-caller-identity --profile $Profile 2>&1

if ($LASTEXITCODE -eq 0) {
    $Arn = ($Identity | ConvertFrom-Json).Arn
    Write-Host "Credentials valid. Identity: $Arn" -ForegroundColor Green
    Write-Host "Updated $CredFile [$Profile] with key $AccessKeyId" -ForegroundColor Green
} else {
    Write-Warning "Credentials written but verification failed: $Identity"
    Write-Warning "The key may need a moment to propagate. Try: aws sts get-caller-identity --profile $Profile"
}

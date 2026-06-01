#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verifies that the hardcoded CloudFront domain in terraform.tfvars matches the actual deployed domain.

.DESCRIPTION
Checks that frontend_origin and api_cors_allowed_origins in terraform.tfvars are current.
If CloudFront is recreated, this script alerts so the tfvars file can be updated manually.

.NOTES
Must be run after CloudFront deployment is complete.
Requires AWS CLI and credentials.
#>

param(
    [string]$DistributionName = "algo-frontend",
    [string]$TfvarsPath = "terraform/terraform.tfvars"
)

$ErrorActionPreference = "Stop"

Write-Host "CloudFront Domain Verification" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan

# Get actual CloudFront domain
Write-Host "`nFetching CloudFront distributions..."
try {
    $cfDistributions = aws cloudfront list-distributions --query "DistributionList.Items[*].[Id,DomainName,Comment]" --output json | ConvertFrom-Json

    if (-not $cfDistributions) {
        Write-Host "  ERROR: No CloudFront distributions found" -ForegroundColor Red
        exit 1
    }

    # Find distribution by comment or partial name match
    $actualDistribution = $cfDistributions | Where-Object {
        $_[2] -match "algo" -or $_[1] -match "algo"
    } | Select-Object -First 1

    if (-not $actualDistribution) {
        Write-Host "  ERROR: No 'algo' CloudFront distribution found" -ForegroundColor Red
        Write-Host "  Available distributions:"
        $cfDistributions | ForEach-Object { Write-Host "    - $($_[1]) (Comment: $($_[2]))" }
        exit 1
    }

    $actualDomain = "https://$($actualDistribution[1])"
    Write-Host "  Found: $($actualDistribution[1])" -ForegroundColor Green
    Write-Host "  Comment: $($actualDistribution[2])"
} catch {
    Write-Host "  ERROR: Failed to fetch CloudFront distributions" -ForegroundColor Red
    Write-Host "  $_"
    exit 1
}

# Get hardcoded domains from terraform.tfvars
Write-Host "`nReading hardcoded domains from $TfvarsPath..."
if (-not (Test-Path $TfvarsPath)) {
    Write-Host "  ERROR: $TfvarsPath not found" -ForegroundColor Red
    exit 1
}

$tfvarsContent = Get-Content $TfvarsPath -Raw
$frontendOriginMatch = $tfvarsContent | Select-String 'frontend_origin\s*=\s*"([^"]+)"' -AllMatches
$corsOriginMatch = $tfvarsContent | Select-String 'api_cors_allowed_origins\s*=\s*\[\s*"([^"]+)"' -AllMatches

if ($frontendOriginMatch.Matches.Count -eq 0) {
    Write-Host "  ERROR: Could not parse frontend_origin from $TfvarsPath" -ForegroundColor Red
    exit 1
}

$hardcodedFrontend = $frontendOriginMatch.Matches[0].Groups[1].Value
Write-Host "  frontend_origin: $hardcodedFrontend"

if ($corsOriginMatch.Matches.Count -eq 0) {
    Write-Host "  ERROR: Could not parse api_cors_allowed_origins from $TfvarsPath" -ForegroundColor Red
    exit 1
}

$hardcodedCors = $corsOriginMatch.Matches[0].Groups[1].Value
Write-Host "  api_cors_allowed_origins: $hardcodedCors"

# Compare
Write-Host "`nVerifying hardcoded domains match actual CloudFront..."
$mismatch = $false

if ($hardcodedFrontend -ne $actualDomain) {
    Write-Host "  ⚠️  MISMATCH: frontend_origin" -ForegroundColor Yellow
    Write-Host "      Expected: $actualDomain"
    Write-Host "      Got:      $hardcodedFrontend"
    $mismatch = $true
} else {
    Write-Host "  ✓ frontend_origin matches" -ForegroundColor Green
}

if ($hardcodedCors -ne $actualDomain) {
    Write-Host "  ⚠️  MISMATCH: api_cors_allowed_origins" -ForegroundColor Yellow
    Write-Host "      Expected: $actualDomain"
    Write-Host "      Got:      $hardcodedCors"
    $mismatch = $true
} else {
    Write-Host "  ✓ api_cors_allowed_origins matches" -ForegroundColor Green
}

if ($mismatch) {
    Write-Host "`n⚠️  ACTION REQUIRED:" -ForegroundColor Yellow
    Write-Host "  CloudFront domain has changed. Update terraform.tfvars:"
    Write-Host "  - Line 9:  frontend_origin = `"$actualDomain`""
    Write-Host "  - Line 19: api_cors_allowed_origins = [ `"$actualDomain`" ]"
    Write-Host "  After update, commit and re-deploy: git push main"
    exit 1
} else {
    Write-Host "`n✓ CloudFront domain verification passed" -ForegroundColor Green
    exit 0
}

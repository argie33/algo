#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify email address in AWS SES for sandbox testing.

.DESCRIPTION
Allows receiving emails in SES sandbox mode. After verification, you'll receive a
confirmation email - click the link to activate.

.PARAMETER Email
Email address to verify for SES sandbox testing (default: argeropolos@gmail.com)

.PARAMETER Region
AWS region (default: us-east-1)

.EXAMPLE
pwsh scripts/verify-ses-email.ps1 -Email argeropolos@gmail.com
#>

param(
    [string]$Email = "argeropolos@gmail.com",
    [string]$Region = "us-east-1"
)

Write-Host "Verifying email in SES sandbox: $Email" -ForegroundColor Cyan

try {
    # Send verification email
    $result = aws ses verify-email-identity `
        --email-addresses $Email `
        --region $Region 2>&1 | ConvertFrom-Json

    Write-Host "✓ Verification request sent!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Check $Email for a verification email from AWS"
    Write-Host "2. Click the verification link in that email"
    Write-Host "3. After verification, you can receive emails in SES sandbox mode"
    Write-Host "4. Try password reset again"
    Write-Host ""

    # Check if already verified
    $attributes = aws ses get-identity-verification-attributes `
        --identities $Email `
        --region $Region 2>&1

    if ($attributes -match "Success") {
        Write-Host "Status: Already verified!" -ForegroundColor Green
    } else {
        Write-Host "Status: Awaiting email verification" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

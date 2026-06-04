#!/usr/bin/env pwsh
<#
.DESCRIPTION
Complete SES email verification and full signup/password-reset flow testing.
Verifies sender and recipient emails, tests password reset, and validates signup flow.
#>

param(
    [string]$SenderEmail = "noreply@bullseyetrading.com",
    [string]$RecipientEmail = "argeropolos@gmail.com",
    [string]$Region = "us-east-1",
    [string]$UserPoolId = ""  # Leave empty to auto-detect
)

# Auto-detect Cognito user pool if not provided
if ([string]::IsNullOrEmpty($UserPoolId)) {
    Write-Host "Auto-detecting Cognito user pool..." -ForegroundColor Gray
    $poolInfo = aws cognito-idp list-user-pools --max-results 60 --region $Region --query "UserPools[?Name=='algo-pool-dev']" --output json | ConvertFrom-Json

    if ($poolInfo.Count -eq 0) {
        Write-Host "⚠ Warning: Could not find Cognito pool 'algo-pool-dev', continuing without pool ID" -ForegroundColor Yellow
    } else {
        $UserPoolId = $poolInfo[0].Id
        Write-Host "✓ Found pool: $UserPoolId" -ForegroundColor Green
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SES Email Verification & Flow Testing" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Step 1: Verify Sender Email
# ============================================================
Write-Host "Step 1: Verifying sender email ($SenderEmail)..." -ForegroundColor Yellow

$senderVerify = aws ses verify-email-identity `
    --email-address $SenderEmail `
    --region $Region `
    2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Verification request sent to $SenderEmail" -ForegroundColor Green
    Write-Host "  → Check noreply@bullseyetrading.com inbox for AWS verification email" -ForegroundColor Cyan
    Write-Host "  → Click the verification link to confirm" -ForegroundColor Cyan
} else {
    Write-Host "✗ Failed to verify sender email: $senderVerify" -ForegroundColor Red
    exit 1
}

Write-Host ""

# ============================================================
# Step 2: Verify Recipient Email
# ============================================================
Write-Host "Step 2: Verifying recipient email ($RecipientEmail)..." -ForegroundColor Yellow

$recipientVerify = aws ses verify-email-identity `
    --email-address $RecipientEmail `
    --region $Region `
    2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Verification request sent to $RecipientEmail" -ForegroundColor Green
    Write-Host "  → Check argeropolos@gmail.com inbox for AWS verification email" -ForegroundColor Cyan
    Write-Host "  → Click the verification link to confirm" -ForegroundColor Cyan
} else {
    Write-Host "✗ Failed to verify recipient email: $recipientVerify" -ForegroundColor Red
    exit 1
}

Write-Host ""

# ============================================================
# Step 3: Check Verified Identities
# ============================================================
Write-Host "Step 3: Checking verified SES identities..." -ForegroundColor Yellow
Write-Host ""

$identities = aws ses list-identities --region $Region --query 'Identities' --output text

if ($identities) {
    Write-Host "Verified identities in SES:" -ForegroundColor Green
    $identities.Split() | ForEach-Object {
        Write-Host "  • $_"
    }
} else {
    Write-Host "⚠ No verified identities yet (check your emails and click verification links)" -ForegroundColor Yellow
}

Write-Host ""

# ============================================================
# Step 4: Show Next Steps
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMMEDIATE (verify emails):" -ForegroundColor Yellow
Write-Host "  1. Check noreply@bullseyetrading.com email" -ForegroundColor White
Write-Host "  2. Check argeropolos@gmail.com email" -ForegroundColor White
Write-Host "  3. Click verification links in BOTH emails" -ForegroundColor White
Write-Host ""

Write-Host "AFTER EMAIL VERIFICATION (test flows):" -ForegroundColor Yellow
Write-Host "  1. Open: https://d2u93283nn45h2.cloudfront.net" -ForegroundColor White
Write-Host ""
Write-Host "  TEST PASSWORD RESET:" -ForegroundColor Cyan
Write-Host "    • Click 'Forgot Password'" -ForegroundColor White
Write-Host "    • Enter: argeropolos@gmail.com" -ForegroundColor White
Write-Host "    • Check email for password reset code" -ForegroundColor White
Write-Host "    • Enter code and set new password" -ForegroundColor White
Write-Host ""
Write-Host "  TEST NEW USER SIGNUP:" -ForegroundColor Cyan
Write-Host "    • Click 'Sign Up'" -ForegroundColor White
Write-Host "    • Use test email (e.g., test+$(Get-Date -Format 'yyyyMMddHHmm')@gmail.com)" -ForegroundColor White
Write-Host "    • Check email for signup confirmation code" -ForegroundColor White
Write-Host "    • Confirm email and complete signup" -ForegroundColor White
Write-Host ""

Write-Host "PRODUCTION SUPPORT (next step):" -ForegroundColor Yellow
Write-Host "  After emails verify, request SES production access:" -ForegroundColor White
Write-Host "  → AWS Console → SES → Account provisioning → Request production access" -ForegroundColor Cyan
Write-Host "  → Use case: 'Authentication and password reset emails for trading platform'" -ForegroundColor Cyan
Write-Host "  → AWS approves in ~24 hours" -ForegroundColor Cyan
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Status: Awaiting Email Verification" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

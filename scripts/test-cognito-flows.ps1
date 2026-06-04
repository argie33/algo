#!/usr/bin/env pwsh
<#
.DESCRIPTION
End-to-end test of Cognito password reset and signup flows.
Tests that emails are being sent correctly via SES.

Prerequisites:
  1. Both sender and recipient emails verified in SES
  2. Cognito Lambda has SES permissions
  3. User pool configured with custom email trigger
#>

param(
    [string]$ClientId = "",  # Leave empty to auto-detect
    [string]$UserPoolId = "",  # Leave empty to auto-detect
    [string]$Region = "us-east-1",
    [string]$TestEmail = "argeropolos@gmail.com",
    [string]$FrontendUrl = ""  # Leave empty to auto-detect
)

# Auto-detect Cognito pool
if ([string]::IsNullOrEmpty($UserPoolId)) {
    Write-Host "Auto-detecting Cognito user pool..." -ForegroundColor Gray
    $poolInfo = aws cognito-idp list-user-pools --max-results 60 --region $Region --query "UserPools[?Name=='algo-pool-dev']" --output json | ConvertFrom-Json

    if ($poolInfo.Count -eq 0) {
        Write-Host "ERROR: Could not find Cognito pool 'algo-pool-dev'" -ForegroundColor Red
        exit 1
    }
    $UserPoolId = $poolInfo[0].Id
    Write-Host "✓ Found pool: $UserPoolId" -ForegroundColor Green
}

# Auto-detect client ID
if ([string]::IsNullOrEmpty($ClientId)) {
    Write-Host "Auto-detecting Cognito app client..." -ForegroundColor Gray
    $clientInfo = aws cognito-idp list-user-pool-clients --user-pool-id $UserPoolId --max-results 60 --region $Region --query "UserPoolClients[?ClientName=='algo-app-dev']" --output json | ConvertFrom-Json

    if ($clientInfo.Count -eq 0) {
        Write-Host "⚠ Warning: Could not find client 'algo-app-dev', using first available client" -ForegroundColor Yellow
        $clientInfo = aws cognito-idp list-user-pool-clients --user-pool-id $UserPoolId --max-results 1 --region $Region --output json | ConvertFrom-Json
    }
    $ClientId = $clientInfo[0].ClientId
    Write-Host "✓ Found client: $ClientId" -ForegroundColor Green
}

# Auto-detect frontend URL
if ([string]::IsNullOrEmpty($FrontendUrl)) {
    Write-Host "Auto-detecting CloudFront frontend URL..." -ForegroundColor Gray
    $cfDomain = aws cloudfront list-distributions --region $Region --query "DistributionList.Items[0].DomainName" --output text 2>$null

    if ([string]::IsNullOrEmpty($cfDomain) -or $cfDomain -eq "None") {
        Write-Host "⚠ Warning: Could not find CloudFront distribution, using localhost fallback" -ForegroundColor Yellow
        $FrontendUrl = "http://localhost:5173"
    } else {
        $FrontendUrl = "https://$cfDomain"
        Write-Host "✓ Found frontend: $FrontendUrl" -ForegroundColor Green
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cognito Email Flow Testing" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Test 1: Password Reset Flow
# ============================================================
Write-Host "Test 1: Password Reset Flow" -ForegroundColor Yellow
Write-Host "================================" -ForegroundColor Yellow
Write-Host ""

Write-Host "What to do:" -ForegroundColor Cyan
Write-Host "  1. Open browser: $FrontendUrl" -ForegroundColor White
Write-Host "  2. Click 'Login' → 'Forgot Password'" -ForegroundColor White
Write-Host "  3. Enter email: $TestEmail" -ForegroundColor White
Write-Host "  4. Click 'Send Code'" -ForegroundColor White
Write-Host ""

Write-Host "Expected behavior:" -ForegroundColor Green
Write-Host "  ✓ Frontend shows: 'Reset code sent — check your email.'" -ForegroundColor White
Write-Host "  ✓ You receive email to $TestEmail" -ForegroundColor White
Write-Host "  ✓ Email contains password reset code" -ForegroundColor White
Write-Host "  ✓ Enter code and set new password" -ForegroundColor White
Write-Host ""

Write-Host "CloudWatch logs:" -ForegroundColor Cyan
Write-Host "  → /aws/lambda/algo-cognito-email-trigger-dev" -ForegroundColor Gray
Write-Host "  → Look for: 'CustomMessage_ForgotPassword'" -ForegroundColor Gray
Write-Host "  → Success: 'Email sent successfully to $TestEmail'" -ForegroundColor Gray
Write-Host ""

# ============================================================
# Test 2: New User Signup Flow
# ============================================================
Write-Host "Test 2: New User Signup Flow" -ForegroundColor Yellow
Write-Host "================================" -ForegroundColor Yellow
Write-Host ""

$testEmail = "test+$(Get-Date -Format 'yyyyMMddHHmm')@gmail.com"

Write-Host "What to do:" -ForegroundColor Cyan
Write-Host "  1. Open browser: $FrontendUrl" -ForegroundColor White
Write-Host "  2. Click 'Sign Up'" -ForegroundColor White
Write-Host "  3. Enter test email: $testEmail" -ForegroundColor White
Write-Host "  4. Click 'Create Account'" -ForegroundColor White
Write-Host ""

Write-Host "Expected behavior:" -ForegroundColor Green
Write-Host "  ✓ Frontend shows: 'Confirmation code sent to $testEmail'" -ForegroundColor White
Write-Host "  ✓ You receive email to $testEmail" -ForegroundColor White
Write-Host "  ✓ Email contains confirmation code" -ForegroundColor White
Write-Host "  ✓ Enter code and set password to complete signup" -ForegroundColor White
Write-Host ""

Write-Host "CloudWatch logs:" -ForegroundColor Cyan
Write-Host "  → /aws/lambda/algo-cognito-email-trigger-dev" -ForegroundColor Gray
Write-Host "  → Look for: 'CustomMessage_SignUp'" -ForegroundColor Gray
Write-Host "  → Success: 'Email sent successfully to $testEmail'" -ForegroundColor Gray
Write-Host ""

# ============================================================
# Verification Checklist
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Verification Checklist" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Prerequisites:" -ForegroundColor Yellow
@(
    "AWS credentials configured (check: 'aws sts get-caller-identity')",
    "SES sender email verified: noreply@bullseyetrading.com",
    "SES recipient email verified: $TestEmail",
    "Cognito email Lambda deployed and functional",
    "Frontend deployed and accessible"
) | ForEach-Object { Write-Host "  ☐ $_" }

Write-Host ""
Write-Host "After running tests:" -ForegroundColor Yellow
@(
    "Password reset email received at $TestEmail",
    "Password reset code works and email verifies",
    "New user signup email received at test address",
    "Signup code works and account created",
    "CloudWatch logs show no errors from Cognito Lambda",
    "SES sending statistics show sent=2 (reset + signup)"
) | ForEach-Object { Write-Host "  ☐ $_" }

Write-Host ""
Write-Host "If all checks pass:" -ForegroundColor Green
Write-Host "  ✓ Full new user flow is working" -ForegroundColor White
Write-Host "  ✓ Request SES production access for unrestricted sending" -ForegroundColor White
Write-Host ""

# ============================================================
# Commands to Check Status
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Useful Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Check verified SES identities:" -ForegroundColor Yellow
Write-Host '  aws ses list-identities --region '$Region -ForegroundColor Gray
Write-Host ""

Write-Host "Check SES sending statistics:" -ForegroundColor Yellow
Write-Host '  aws ses get-send-statistics --region '$Region -ForegroundColor Gray
Write-Host ""

Write-Host "Check Lambda logs (live):" -ForegroundColor Yellow
Write-Host '  aws logs tail /aws/lambda/algo-cognito-email-trigger-dev --follow --region '$Region -ForegroundColor Gray
Write-Host ""

Write-Host "Check specific Lambda invocation:" -ForegroundColor Yellow
Write-Host '  aws lambda invoke --function-name algo-cognito-email-trigger-dev --region '$Region' /tmp/out.json && cat /tmp/out.json' -ForegroundColor Gray
Write-Host ""

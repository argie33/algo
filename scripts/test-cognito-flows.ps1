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
    [string]$ClientId = "2gupf2mjl9pk5fq6e49ov1p89p",  # algo-web-app-dev
    [string]$UserPoolId = "us-east-1_XJpLb9SKX",
    [string]$Region = "us-east-1",
    [string]$TestEmail = "argeropolos@gmail.com",
    [string]$FrontendUrl = "https://d2u93283nn45h2.cloudfront.net"
)

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

#!/usr/bin/env pwsh
<#
.DESCRIPTION
Post-deployment verification workflow.
Runs immediately after GitHub Actions deployment completes.
Verifies SES emails and tests Cognito flows.

Run this script once GitHub Actions shows: status=completed, conclusion=success
#>

param(
    [string]$DeploymentRunId = "26859573339"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "POST-DEPLOYMENT VERIFICATION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Step 0: Verify Deployment Completed
# ============================================================
Write-Host "Step 0: Verifying deployment status..." -ForegroundColor Yellow

$run = gh run view --repo argie33/algo $DeploymentRunId --json status,conclusion | ConvertFrom-Json

if ($run.status -ne "completed") {
    Write-Host "✗ Deployment still in progress (status: $($run.status))" -ForegroundColor Red
    Write-Host "Please wait for deployment to complete before running this script." -ForegroundColor Yellow
    exit 1
}

if ($run.conclusion -ne "success") {
    Write-Host "✗ Deployment failed (conclusion: $($run.conclusion))" -ForegroundColor Red
    Write-Host "Check GitHub Actions logs: https://github.com/argie33/algo/actions/runs/$DeploymentRunId" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Deployment completed successfully" -ForegroundColor Green
Write-Host ""

# ============================================================
# Step 1: Refresh AWS Credentials
# ============================================================
Write-Host "Step 1: Refreshing AWS credentials..." -ForegroundColor Yellow
Write-Host "(This ensures new IAM permissions are active)" -ForegroundColor Gray

& scripts/refresh-aws-credentials.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Warning: Could not refresh credentials" -ForegroundColor Yellow
    Write-Host "Continuing anyway - permissions may be fresh already" -ForegroundColor Gray
}

Write-Host ""

# ============================================================
# Step 2: Verify SES Emails
# ============================================================
Write-Host "Step 2: Verifying SES emails..." -ForegroundColor Yellow
Write-Host "(Requests verification for sender and recipient)" -ForegroundColor Gray

& scripts/verify-ses-emails-and-test.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Email verification failed" -ForegroundColor Red
    exit 1
}

Write-Host ""

# ============================================================
# Step 3: Show Testing Guide
# ============================================================
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NEXT STEPS - MANUAL TESTING" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get CloudFront domain
Write-Host "Detecting frontend URL..." -ForegroundColor Gray
$frontendUrl = aws cloudfront list-distributions --region us-east-1 --query "DistributionList.Items[0].DomainName" --output text 2>$null
if ([string]::IsNullOrEmpty($frontendUrl) -or $frontendUrl -eq "None") {
    $frontendUrl = "<frontend-url>"
    Write-Host "⚠ Could not auto-detect CloudFront domain" -ForegroundColor Yellow
} else {
    $frontendUrl = "https://$frontendUrl"
    Write-Host "✓ Found frontend: $frontendUrl" -ForegroundColor Green
}

Write-Host ""
Write-Host "📧 STEP 1: Verify Emails (Check Inboxes)" -ForegroundColor Yellow
Write-Host "  ☐ Check noreply@bullseyetrading.com (or your sender email)" -ForegroundColor White
Write-Host "  ☐ Check argeropolos@gmail.com" -ForegroundColor White
Write-Host "  ☐ Click verification links in BOTH emails" -ForegroundColor White
Write-Host "  ⏱ Time: ~2 minutes" -ForegroundColor Gray
Write-Host ""

Write-Host "🔐 STEP 2: Test Password Reset" -ForegroundColor Yellow
Write-Host "  1. Open: $frontendUrl" -ForegroundColor White
Write-Host "  2. Click 'Login' → 'Forgot Password'" -ForegroundColor White
Write-Host "  3. Enter: argeropolos@gmail.com" -ForegroundColor White
Write-Host "  4. Check email for reset code" -ForegroundColor White
Write-Host "  5. Enter code and set new password" -ForegroundColor White
Write-Host "  ⏱ Time: ~3 minutes" -ForegroundColor Gray
Write-Host ""

Write-Host "👤 STEP 3: Test New User Signup" -ForegroundColor Yellow
Write-Host "  1. Open: $frontendUrl" -ForegroundColor White
Write-Host "  2. Click 'Sign Up'" -ForegroundColor White
Write-Host "  3. Enter email: test+$(Get-Date -Format 'yyyyMMddHHmm')@gmail.com" -ForegroundColor White
Write-Host "  4. Check email for confirmation code" -ForegroundColor White
Write-Host "  5. Enter code and complete signup" -ForegroundColor White
Write-Host "  ⏱ Time: ~3 minutes" -ForegroundColor Gray
Write-Host ""

Write-Host "🚀 STEP 4: Request SES Production Access" -ForegroundColor Yellow
Write-Host "  📍 AWS Console → SES → Account provisioning" -ForegroundColor White
Write-Host "  📍 Click: Request production access" -ForegroundColor White
Write-Host "  📍 Use case: 'Authentication and password reset emails for trading platform'" -ForegroundColor White
Write-Host "  ⏱ Time: AWS approves in ~24 hours" -ForegroundColor Gray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CloudWatch Logs (For Debugging)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Watch Lambda logs in real-time:" -ForegroundColor Yellow
Write-Host '  aws logs tail /aws/lambda/algo-cognito-email-trigger-dev --follow --region us-east-1' -ForegroundColor Gray
Write-Host ""
Write-Host "Look for:" -ForegroundColor Yellow
Write-Host "  ✓ 'CustomMessage_ForgotPassword'" -ForegroundColor Green
Write-Host "  ✓ 'CustomMessage_SignUp'" -ForegroundColor Green
Write-Host "  ✓ 'Email sent successfully'" -ForegroundColor Green
Write-Host ""
Write-Host "If you see errors:" -ForegroundColor Yellow
Write-Host "  ✗ 'Email address is not verified' → Click verification links" -ForegroundColor Red
Write-Host "  ✗ 'AccessDeniedException' → Wait 5 min and retry (IAM eventual consistency)" -ForegroundColor Red
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Status: Ready for Manual Testing" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

#!/usr/bin/env pwsh
# Check credential rotation status and tell developers what to do.
# Shows if rotation is in progress and whether they need to update.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Profile = "algo-developer"
$Region  = "us-east-1"

Write-Host "Checking credential rotation status..." -ForegroundColor Cyan

# Get credentials from Secrets Manager
try {
    $SecretJson = aws secretsmanager get-secret-value `
        --secret-id algo/developer-credentials `
        --region $Region `
        --query SecretString `
        --output text 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  Could not retrieve credential status from AWS (may need to run 'scripts/refresh-aws-credentials.ps1')" -ForegroundColor Yellow
        exit 1
    }

    $Secret = $SecretJson | ConvertFrom-Json
} catch {
    Write-Host "❌ Error reading secret: $_" -ForegroundColor Red
    exit 1
}

# Parse rotation info
$Status = $Secret.status
$RotationDate = $Secret.rotation_date
$CleanupDate = $Secret.old_key_cleanup_date
$GracePeriodDays = $Secret.grace_period_days
$CurrentKeyId = $Secret.access_key_id
$OldKeyId = $Secret.old_access_key_id

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Blue
Write-Host "CREDENTIAL ROTATION STATUS" -ForegroundColor Blue
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Blue

switch ($Status) {
    "dual_credentials_active" {
        Write-Host "Status: GRACE PERIOD ACTIVE" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Timeline:" -ForegroundColor Cyan
        Write-Host "  Rotation Date: $RotationDate"
        Write-Host "  Grace Period: $GracePeriodDays days"
        Write-Host "  Cleanup Date: $CleanupDate"
        Write-Host ""
        Write-Host "Current Situation:" -ForegroundColor Cyan
        Write-Host "  ✓ New credentials created"
        Write-Host "  ✓ Both old and new keys are valid"
        Write-Host "  ⚠️  Old key will be deleted on $CleanupDate"
        Write-Host ""
        Write-Host "Action Required:" -ForegroundColor Green
        Write-Host "  1. Run: scripts/refresh-aws-credentials.ps1"
        Write-Host "  2. Verify new credentials: aws sts get-caller-identity --profile $Profile"
        Write-Host "  3. Update any deployed services using these credentials"
        Write-Host ""
        Write-Host "Important:" -ForegroundColor Yellow
        Write-Host "  - You have until $CleanupDate to update"
        Write-Host "  - Old key becomes invalid on that date"
        Write-Host "  - If you still need old credentials, update before that date"
    }

    "active" {
        Write-Host "Status: NORMAL (Post-cleanup)" -ForegroundColor Green
        Write-Host ""
        Write-Host "Timeline:" -ForegroundColor Cyan
        Write-Host "  Rotation Date: $RotationDate"
        Write-Host "  Cleanup Date: $CleanupDate"
        Write-Host ""
        Write-Host "Current Situation:" -ForegroundColor Cyan
        Write-Host "  ✓ Old key has been deleted"
        Write-Host "  ✓ Only new credentials are active"
        Write-Host ""

        if ($Secret.old_key_deleted) {
            Write-Host "Cleanup Info:" -ForegroundColor Cyan
            Write-Host "  Old key deleted: $($Secret.old_key_deleted)"
        }
    }

    default {
        Write-Host "Status: UNKNOWN ($Status)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Your Current Credentials:" -ForegroundColor Cyan

# Check if user's local credentials match the latest
$env:AWS_PROFILE = $Profile
$env:AWS_DEFAULT_REGION = $Region

try {
    $LocalIdentity = aws sts get-caller-identity | ConvertFrom-Json
    Write-Host "  Using Key: (masked)" -ForegroundColor White
    Write-Host "  User ARN: $($LocalIdentity.Arn)" -ForegroundColor White
    Write-Host "  Account: $($LocalIdentity.Account)" -ForegroundColor White

    # Try to detect if using old or new key by comparing to what's in secrets
    # (This is a best-effort check - we can't directly compare key IDs from local creds)
    Write-Host ""
    Write-Host "Status: ✓ Credentials are valid" -ForegroundColor Green

    if ($Status -eq "dual_credentials_active" -and $CleanupDate) {
        Write-Host ""
        Write-Host "Recommendation:" -ForegroundColor Cyan
        Write-Host "  Update to new credentials before $CleanupDate" -ForegroundColor Yellow
        Write-Host "  Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Status: ❌ Credentials are NOT valid or cannot be verified" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix:" -ForegroundColor Yellow
    Write-Host "  1. Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    Write-Host "  2. Verify: aws sts get-caller-identity --profile $Profile" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Blue

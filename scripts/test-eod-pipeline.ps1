#!/usr/bin/env pwsh
<#
.SYNOPSIS
Manually trigger EOD pipeline to test full dataset loading and orchestrator phases.

.DESCRIPTION
This script:
1. Triggers the EOD pipeline Step Functions state machine
2. Waits for completion (optional)
3. Monitors execution in CloudWatch logs
4. Reports success/failure

Usage:
    .\scripts\test-eod-pipeline.ps1 -Wait
    .\scripts\test-eod-pipeline.ps1 -Watch  # Stream logs while running

.PARAMETER Wait
If specified, waits for pipeline to complete before exiting.

.PARAMETER Watch
If specified, tails CloudWatch logs while pipeline executes.

.PARAMETER DryRun
If specified, simulates the trigger without actually running it.
#>

param(
    [switch]$Wait,
    [switch]$Watch,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Load AWS credentials from PowerShell profile
if (-not $env:AWS_REGION) {
    $env:AWS_REGION = "us-east-1"
}

Write-Host "🚀 EOD Pipeline Diagnostic Trigger" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# Step 1: Find the EOD pipeline state machine
Write-Host "📋 Finding EOD pipeline state machine..." -ForegroundColor Yellow
try {
    $allStateMachines = aws stepfunctions list-state-machines `
        --region us-east-1 `
        2>$null | ConvertFrom-Json

    $stateMachines = $allStateMachines.stateMachines | Where-Object { $_.name -like "*EodBulk*" -or $_.name -like "*eod*" }

    if ($stateMachines.Count -eq 0) {
        Write-Host "❌ No EOD pipeline state machine found. Check if Terraform deployed it." -ForegroundColor Red
        exit 1
    }

    $stateMachine = $stateMachines[0]
    $smArn = $stateMachine.stateMachineArn
    $smName = $stateMachine.name

    Write-Host "   ✓ Found: $smName" -ForegroundColor Green
    Write-Host "   ARN: $smArn" -ForegroundColor Gray
} catch {
    Write-Host "❌ Failed to list state machines: $_" -ForegroundColor Red
    exit 1
}

# Step 2: Prepare input payload
Write-Host ""
Write-Host "📦 Preparing pipeline trigger..." -ForegroundColor Yellow

$input = @{
    "loader_mode" = "FULL_DATASET"
    "timestamp" = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
} | ConvertTo-Json

Write-Host "   Input: $input" -ForegroundColor Gray

# Step 3: Trigger execution
Write-Host ""
Write-Host "🔥 Triggering EOD pipeline..." -ForegroundColor Yellow

if ($DryRun) {
    Write-Host "   [DRY RUN] Would execute with input: $input" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To actually run, omit -DryRun flag" -ForegroundColor Yellow
    exit 0
}

try {
    $execution = aws stepfunctions start-execution `
        --state-machine-arn $smArn `
        --name "test-$(Get-Date -Format 'HHmmss')" `
        --input $input `
        --region us-east-1 `
        2>$null | ConvertFrom-Json

    $executionArn = $execution.executionArn
    Write-Host "   ✓ Execution started" -ForegroundColor Green
    Write-Host "   ARN: $executionArn" -ForegroundColor Gray
} catch {
    Write-Host "❌ Failed to trigger execution: $_" -ForegroundColor Red
    exit 1
}

# Step 4: Optional - wait and monitor
if ($Wait -or $Watch) {
    Write-Host ""
    Write-Host "⏳ Monitoring execution..." -ForegroundColor Yellow

    $maxWait = 14400  # 4 hours for EOD pipeline
    $elapsed = 0
    $checkInterval = 30

    while ($elapsed -lt $maxWait) {
        Start-Sleep -Seconds $checkInterval

        try {
            $status = aws stepfunctions describe-execution `
                --execution-arn $executionArn `
                --region us-east-1 `
                2>$null | ConvertFrom-Json

            $currentStatus = $status.status
            $elapsed += $checkInterval
            $elapsed_min = [math]::Round($elapsed / 60, 1)

            Write-Host "   [$elapsed_min min] Status: $currentStatus" -ForegroundColor Cyan

            if ($currentStatus -eq "SUCCEEDED") {
                Write-Host ""
                Write-Host "✅ Pipeline completed successfully!" -ForegroundColor Green
                break
            } elseif ($currentStatus -eq "FAILED") {
                Write-Host ""
                Write-Host "❌ Pipeline failed!" -ForegroundColor Red
                Write-Host "   Cause: $($status.cause)" -ForegroundColor Gray
                exit 1
            }
        } catch {
            Write-Host "⚠️  Error checking status: $_" -ForegroundColor Yellow
        }
    }

    if ($elapsed -ge $maxWait) {
        Write-Host ""
        Write-Host "⏱️  Pipeline still running after $([math]::Round($maxWait/3600, 1)) hours" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "💡 To wait for completion, run: .\scripts\test-eod-pipeline.ps1 -Wait" -ForegroundColor Cyan
    Write-Host "💡 To stream logs, run: .\scripts\test-eod-pipeline.ps1 -Watch" -ForegroundColor Cyan
}

# Step 5: Summary
Write-Host ""
Write-Host "📊 Dashboard:" -ForegroundColor Yellow
Write-Host "   CloudWatch: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1" -ForegroundColor Gray
Write-Host "   Step Functions: https://console.aws.amazon.com/states/home?region=us-east-1" -ForegroundColor Gray
Write-Host ""
Write-Host "Execution ARN: $executionArn" -ForegroundColor Gray

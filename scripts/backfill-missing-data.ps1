#Requires -Version 5.1
<#
.SYNOPSIS
Backfill 6 days of missing data by invoking the EOD Step Functions pipeline.

.DESCRIPTION
After EventBridge Scheduler was down for 6 days (2026-06-28 to 2026-07-04),
data loaders stopped running. This script manually invokes the Step Functions
EOD pipeline to backfill all missing data.

Pipeline will:
1. Load stock prices and technical data
2. Load financial metrics (quality, growth, value, etc)
3. Compute scores
4. Load signals
5. Trigger algo orchestrator

.EXAMPLE
./backfill-missing-data.ps1
#>

param(
    [string]$AwsRegion = "us-east-1",
    [string]$StateMachineArn = "",  # Will be fetched from terraform outputs if empty
    [string]$ProjectName = "algo",
    [string]$Environment = "dev"
)

$ErrorActionPreference = "Stop"

Write-Host "🔄 Backfilling 6 days of missing data (2026-06-28 to 2026-07-04)" -ForegroundColor Yellow

# Get Step Functions EOD pipeline ARN from terraform outputs
if ([string]::IsNullOrEmpty($StateMachineArn)) {
    Write-Host "📋 Fetching Step Functions state machine ARN from terraform..." -ForegroundColor Cyan

    Push-Location terraform
    try {
        $StateMachineArn = terraform output -raw eod_state_machine_arn 2>$null
    } catch {
        Write-Host "❌ Could not get state machine ARN from terraform outputs" -ForegroundColor Red
        Write-Host "   Make sure terraform has been applied successfully" -ForegroundColor Red
        exit 1
    } finally {
        Pop-Location
    }
}

if ([string]::IsNullOrEmpty($StateMachineArn)) {
    Write-Host "❌ State machine ARN is empty" -ForegroundColor Red
    exit 1
}

Write-Host "✅ State machine: $StateMachineArn" -ForegroundColor Green

# Invoke the Step Functions execution
Write-Host "🚀 Invoking Step Functions EOD pipeline..." -ForegroundColor Cyan

$ExecutionInput = @{
    backfill_days = 6
    backfill_reason = "EventBridge scheduler outage (2026-06-28 to 2026-07-04)"
    timestamp = [DateTime]::UtcNow.ToString("o")
} | ConvertTo-Json

try {
    $Execution = aws stepfunctions start-execution `
        --state-machine-arn $StateMachineArn `
        --input $ExecutionInput `
        --region $AwsRegion `
        --output json | ConvertFrom-Json

    $ExecutionArn = $Execution.executionArn
    Write-Host "✅ Execution started: $ExecutionArn" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to start Step Functions execution" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}

# Monitor execution
Write-Host ""
Write-Host "📊 Monitoring execution status..." -ForegroundColor Cyan
$MaxWaitSeconds = 3600  # 1 hour timeout
$CheckInterval = 15     # Check every 15 seconds
$ElapsedSeconds = 0

do {
    $Status = aws stepfunctions describe-execution `
        --execution-arn $ExecutionArn `
        --region $AwsRegion `
        --output json | ConvertFrom-Json

    $StatusValue = $Status.status
    $Timestamp = (Get-Date).ToString("HH:mm:ss")

    switch ($StatusValue) {
        "SUCCEEDED" {
            Write-Host "✅ [$Timestamp] Pipeline execution SUCCEEDED" -ForegroundColor Green
            Write-Host "📈 Data backfill complete - loaders finished successfully"
            exit 0
        }
        "FAILED" {
            Write-Host "❌ [$Timestamp] Pipeline execution FAILED" -ForegroundColor Red
            Write-Host "Error: $($Status.cause)"
            exit 1
        }
        "TIMED_OUT" {
            Write-Host "⏱️  [$Timestamp] Pipeline execution TIMED OUT" -ForegroundColor Yellow
            exit 1
        }
        "ABORTED" {
            Write-Host "⛔ [$Timestamp] Pipeline execution ABORTED" -ForegroundColor Red
            exit 1
        }
        "RUNNING" {
            Write-Host "⏳ [$Timestamp] Pipeline still running..." -ForegroundColor Cyan
        }
    }

    if ($ElapsedSeconds -gt $MaxWaitSeconds) {
        Write-Host "⏱️  Timeout waiting for execution (1 hour)" -ForegroundColor Yellow
        Write-Host "Execution is still running. You can check its status at:" -ForegroundColor Cyan
        Write-Host "https://console.aws.amazon.com/states/home?region=$AwsRegion#/executions" -ForegroundColor Cyan
        exit 1
    }

    Start-Sleep -Seconds $CheckInterval
    $ElapsedSeconds += $CheckInterval
} while ($true)

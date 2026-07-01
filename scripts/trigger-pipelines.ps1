# Manual Pipeline Trigger Script
# Use this to manually start data loading pipelines if scheduled execution has failed

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("eod", "morning", "afternoon", "preclose", "all")]
    [string]$Pipeline,

    [string]$Environment = "dev",
    [string]$AWSRegion = "us-east-1",
    [string]$ProjectName = "algo",
    [switch]$DryRun
)

Write-Host "=== Pipeline Trigger Script ===" -ForegroundColor Green
Write-Host "Pipeline: $Pipeline | Environment: $Environment | Dry Run: $DryRun`n"

# Verify AWS CLI is available
try {
    $null = aws --version
} catch {
    Write-Host "ERROR: AWS CLI not found. Install it with: pip install awscli" -ForegroundColor Red
    exit 1
}

# Get account ID first
$accountId = aws sts get-caller-identity --query Account --output text

# Map pipeline names to state machine ARNs
$pipelineMap = @{
    "eod"      = "arn:aws:states:$AWSRegion`:$accountId`:stateMachine:$ProjectName-eod-pipeline-$Environment"
    "morning"  = "arn:aws:states:$AWSRegion`:$accountId`:stateMachine:$ProjectName-morning-prep-$Environment"
    "afternoon" = "arn:aws:states:$AWSRegion`:$accountId`:stateMachine:$ProjectName-intraday-afternoon-update-$Environment"
    "preclose" = "arn:aws:states:$AWSRegion`:$accountId`:stateMachine:$ProjectName-intraday-preclose-update-$Environment"
}

function Trigger-Pipeline {
    param(
        [string]$PipelineName,
        [string]$StateMachineArn
    )

    Write-Host "→ Triggering $PipelineName pipeline..." -ForegroundColor Cyan

    # Use ARN directly
    $arn = $StateMachineArn

    $executionName = "manual-trigger-$PipelineName-$(Get-Date -Format 'HHmmss')"
    $input = @{
        execution_name = $executionName
        triggered_by = "manual-recovery-script"
        timestamp = (Get-Date -AsUTC).ToString("o")
    } | ConvertTo-Json -Compress

    Write-Host "  State Machine: $arn"
    Write-Host "  Execution Name: $executionName"
    Write-Host "  Input: $input"

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would execute command:" -ForegroundColor Yellow
        Write-Host "  aws stepfunctions start-execution --state-machine-arn '$arn' --name '$executionName' --input '$input' --region $AWSRegion"
        return
    }

    try {
        $result = aws stepfunctions start-execution `
            --state-machine-arn $arn `
            --name $executionName `
            --input $input `
            --region $AWSRegion `
            --output json 2>&1

        if ($LASTEXITCODE -eq 0) {
            $resultJson = $result | ConvertFrom-Json
            Write-Host "  ✓ SUCCESS - Execution ARN: $($resultJson.executionArn)" -ForegroundColor Green
            Write-Host "  Started at: $($resultJson.startDate)"
            return $resultJson.executionArn
        } else {
            Write-Host "  ERROR: $result" -ForegroundColor Red
            return $null
        }
    } catch {
        Write-Host "  EXCEPTION: $_" -ForegroundColor Red
        return $null
    }
}

# Trigger requested pipelines
$triggeredArns = @()

if ($Pipeline -eq "all") {
    foreach ($p in @("eod", "morning", "afternoon", "preclose")) {
        $arn = Trigger-Pipeline -PipelineName $p -StateMachineArn $pipelineMap[$p]
        if ($arn) {
            $triggeredArns += @{ name = $p; arn = $arn }
        }
    }
} else {
    $arn = Trigger-Pipeline -PipelineName $Pipeline -StateMachineArn $pipelineMap[$Pipeline]
    if ($arn) {
        $triggeredArns += @{ name = $Pipeline; arn = $arn }
    }
}

# Monitor executions if not dry-run
if ($triggeredArns.Count -gt 0 -and -not $DryRun) {
    Write-Host "`n=== Monitoring Executions ===" -ForegroundColor Yellow
    Write-Host "Press Ctrl+C to stop monitoring`n"

    foreach ($exec in $triggeredArns) {
        Write-Host "Watching $($exec.name)..." -ForegroundColor Cyan

        $maxWaitMinutes = 60
        $startTime = Get-Date
        $lastStatus = ""

        while ($true) {
            $elapsed = New-TimeSpan -Start $startTime -End (Get-Date)
            if ($elapsed.TotalMinutes -gt $maxWaitMinutes) {
                Write-Host "  Timeout: Execution taking >$maxWaitMinutes minutes" -ForegroundColor Yellow
                break
            }

            try {
                $execStatus = aws stepfunctions describe-execution `
                    --execution-arn $exec.arn `
                    --region $AWSRegion `
                    --output json 2>&1 | ConvertFrom-Json

                $status = $execStatus.status

                if ($status -ne $lastStatus) {
                    $color = if ($status -eq "SUCCEEDED") { "Green" } elseif ($status -eq "FAILED") { "Red" } else { "Yellow" }
                    Write-Host "  [$status] $($execStatus.name) - $($execStatus.input)" -ForegroundColor $color
                    $lastStatus = $status
                }

                if ($status -in @("SUCCEEDED", "FAILED", "TIMED_OUT")) {
                    if ($status -eq "FAILED") {
                        Write-Host "  Error: $($execStatus.cause)" -ForegroundColor Red
                    }
                    break
                }

                Start-Sleep -Seconds 5
            } catch {
                Write-Host "  Error monitoring execution: $_" -ForegroundColor Red
                break
            }
        }
    }
}

Write-Host "`n=== Trigger Complete ===" -ForegroundColor Green

# Print follow-up actions
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Monitor pipeline execution in AWS console"
Write-Host "2. Check CloudWatch Logs for any errors"
Write-Host "3. Verify data freshness after execution completes"
Write-Host "4. If failures occur, run: ./diagnose-infrastructure.ps1"

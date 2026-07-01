# Emergency Pipeline Verification & Recovery
# Checks if Step Functions pipelines are actually executing
# Run this immediately when data staleness is detected

param(
    [string]$Environment = "dev",
    [string]$AWSRegion = "us-east-1",
    [string]$ProjectName = "algo",
    [int]$HoursThreshold = 6  # Alert if no execution in last N hours
)

Write-Host "=== EMERGENCY PIPELINE VERIFICATION ===" -ForegroundColor Red
Write-Host "Checking if Step Functions pipelines are executing..."
Write-Host "This is the ROOT CAUSE CHECK for data staleness issues.`n"

# Helper to run AWS CLI
function Invoke-AWS {
    param([string]$Command, [string]$Description)
    Write-Host "→ $Description..." -ForegroundColor Cyan
    try {
        $result = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -eq 0) { return $result } else { Write-Host "  ERROR: $result" -ForegroundColor Red; return $null }
    } catch { Write-Host "  EXCEPTION: $_" -ForegroundColor Red; return $null }
}

# Get account ID
$accountId = Invoke-AWS "aws sts get-caller-identity --query Account --output text" "Getting AWS account ID"
if (!$accountId) { exit 1 }

# Define pipelines to check
$pipelines = @(
    @{ name = "eod-pipeline"; description = "EOD data pipeline (prices, technicals, metrics, signals, orchestrator)"; schedule = "4:05 PM ET"; schedule_rule = "algo-eod-pipeline-dev" },
    @{ name = "morning-prep-pipeline"; description = "Morning prep pipeline (before 9:30 AM ET market open)"; schedule = "2:00 AM ET"; schedule_rule = "algo-morning-pipeline-dev" }
)

$criticalIssues = @()

foreach ($pipeline in $pipelines) {
    Write-Host "`n=== Checking $($pipeline.name) ===" -ForegroundColor Yellow
    Write-Host "Description: $($pipeline.description)"
    Write-Host "Scheduled: $($pipeline.schedule)"

    # 1. Check if EventBridge Scheduler rule exists and is ENABLED
    Write-Host "  1. Checking EventBridge Scheduler rule..." -ForegroundColor Cyan
    $schedulerRule = Invoke-AWS `
        "aws scheduler get-schedule-group --name default --region $AWSRegion 2>&1; aws scheduler get-schedule --name $($pipeline.schedule_rule) --region $AWSRegion --output json" `
        "Checking scheduler rule $($pipeline.schedule_rule)"

    if (!$schedulerRule) {
        $criticalIssues += "❌ CRITICAL: Scheduler rule '$($pipeline.schedule_rule)' does not exist or is not accessible"
        Write-Host "    ❌ SCHEDULER RULE MISSING OR NOT ACCESSIBLE" -ForegroundColor Red
        continue
    }

    try {
        $scheduleJson = $schedulerRule | ConvertFrom-Json
        $state = $scheduleJson.State
        Write-Host "    State: $state" -ForegroundColor (if ($state -eq "ENABLED") { "Green" } else { "Red" })
        if ($state -ne "ENABLED") {
            $criticalIssues += "❌ CRITICAL: Scheduler rule '$($pipeline.schedule_rule)' is DISABLED - pipelines won't fire"
        }
    } catch {
        Write-Host "    Error parsing scheduler state" -ForegroundColor Red
    }

    # 2. Check recent Step Functions executions
    Write-Host "  2. Checking Step Functions execution history..." -ForegroundColor Cyan
    $stateMachineArn = "arn:aws:states:$AWSRegion`:$accountId`:stateMachine:$ProjectName-$($pipeline.name)-$Environment"

    $executions = Invoke-AWS `
        "aws stepfunctions list-executions --state-machine-arn $stateMachineArn --region $AWSRegion --max-results 10 --output json" `
        "Listing recent executions"

    if (!$executions) {
        $criticalIssues += "❌ CRITICAL: Cannot query Step Functions - State Machine may not exist or permissions denied"
        Write-Host "    ❌ CANNOT QUERY EXECUTIONS" -ForegroundColor Red
        continue
    }

    try {
        $execJson = $executions | ConvertFrom-Json
        $recentExec = $execJson.executions | Select-Object -First 1

        if (!$recentExec) {
            $criticalIssues += "❌ CRITICAL: NO RECENT EXECUTIONS for $($pipeline.name) - scheduler may not be triggering"
            Write-Host "    ❌ NO EXECUTIONS FOUND" -ForegroundColor Red
        } else {
            $startTime = [DateTime]::Parse($recentExec.startDate)
            $hoursAgo = [math]::Round(((Get-Date) - $startTime).TotalHours, 1)
            $statusColor = if ($recentExec.status -eq "SUCCEEDED") { "Green" } elseif ($recentExec.status -eq "FAILED") { "Red" } else { "Yellow" }

            Write-Host "    Last Execution: $hoursAgo hours ago" -ForegroundColor $statusColor
            Write-Host "    Status: $($recentExec.status)" -ForegroundColor $statusColor

            if ($recentExec.status -eq "FAILED") {
                $criticalIssues += "❌ CRITICAL: Last execution FAILED - check Step Functions logs for error details"
            }

            if ($hoursAgo -gt $HoursThreshold) {
                $criticalIssues += "❌ CRITICAL: No successful execution in last $HoursThreshold hours - data stale by design"
            }
        }
    } catch {
        Write-Host "    Error parsing executions" -ForegroundColor Red
    }
}

# Summary
Write-Host "`n=== CRITICAL ISSUES FOUND ===" -ForegroundColor Red
if ($criticalIssues.Count -eq 0) {
    Write-Host "✅ Pipelines appear to be executing normally" -ForegroundColor Green
} else {
    foreach ($issue in $criticalIssues) {
        Write-Host $issue
    }

    Write-Host "`n=== IMMEDIATE RECOVERY STEPS ===" -ForegroundColor Yellow
    Write-Host "1. If scheduler rule is DISABLED:"
    Write-Host "   ./scripts/enable-scheduler-rules.ps1"
    Write-Host ""
    Write-Host "2. If Step Functions is failing:"
    Write-Host "   - Check CloudWatch Logs: /aws/states/$ProjectName-eod-pipeline-$Environment"
    Write-Host "   - Run: ./scripts/diagnose-infrastructure.ps1"
    Write-Host ""
    Write-Host "3. If no recent executions:"
    Write-Host "   - Manually trigger: ./scripts/trigger-pipelines.ps1 -Pipeline eod"
    Write-Host "   - Monitor: ./scripts/trigger-pipelines.ps1 -Pipeline eod (will show progress)"
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Total Issues: $($criticalIssues.Count)"
Write-Host "Recovery Status: $(if ($criticalIssues.Count -eq 0) { '✅ READY' } else { '❌ NEEDS INTERVENTION' })"

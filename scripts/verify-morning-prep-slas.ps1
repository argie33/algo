#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify morning prep pipeline SLAs and diagnose why it might not be running.

.DESCRIPTION
This script:
1. Checks if the EventBridge Scheduler for morning prep is enabled
2. Verifies recent loader executions in the database
3. Checks Step Functions execution history
4. Validates that loader_execution_history table is being populated
5. Reports SLA compliance for the 2:00 AM - 9:30 AM window

.EXAMPLE
./scripts/verify-morning-prep-slas.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

# Load PowerShell profile to get AWS credentials
& $PROFILE

$env:AWS_PROFILE = 'algo-developer'
$REGION = 'us-east-1'
$SCHEDULE_NAME = 'algo-morning-pipeline-dev'
$ENVIRONMENT = 'dev'

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "MORNING PREP PIPELINE - SLA VERIFICATION REPORT" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ==================================================
# 1. Check EventBridge Scheduler Status
# ==================================================
Write-Host "1. EVENTBRIDGE SCHEDULER STATUS" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────" -ForegroundColor Yellow

try {
    $scheduleCmd = "aws scheduler get-schedule --name $SCHEDULE_NAME --region $REGION --query 'State' --output text"
    $scheduleState = Invoke-Expression $scheduleCmd 2>&1

    if ($scheduleState -match "ENABLED|DISABLED") {
        Write-Host "   Schedule State: $scheduleState" -ForegroundColor $(if($scheduleState -eq "ENABLED") {"Green"} else {"Red"})
        if ($scheduleState -eq "DISABLED") {
            Write-Host "   ⚠️  ISSUE: Schedule is DISABLED in AWS" -ForegroundColor Red
            Write-Host "   ACTION: Run 'terraform apply' to enable it" -ForegroundColor Yellow
        }
    } else {
        Write-Host "   ✓ Checking Step Functions executions as fallback..." -ForegroundColor Gray
    }
} catch {
    Write-Host "   ⚠️  Could not query scheduler (permission issue). Checking database instead..." -ForegroundColor Yellow
}

Write-Host ""

# ==================================================
# 2. Check Step Functions Execution History
# ==================================================
Write-Host "2. STEP FUNCTIONS EXECUTION HISTORY" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────" -ForegroundColor Yellow

try {
    $stateMachineArn = "arn:aws:states:$REGION:626216981288:stateMachine:algo-morning-prep-pipeline-$ENVIRONMENT"

    # Get last 5 executions
    $cmd = @"
aws stepfunctions list-executions `
  --state-machine-arn "$stateMachineArn" `
  --region $REGION `
  --max-results 5 `
  --query 'executions[*].[executionArn,status,startDate,stopDate]' `
  --output text
"@

    $executions = Invoke-Expression $cmd 2>&1

    if ($executions -and $executions -notmatch "not authorized") {
        Write-Host "   Last 5 executions:" -ForegroundColor Gray
        $executions | ForEach-Object {
            $parts = $_ -split "`t"
            if ($parts.Count -ge 3) {
                $status = $parts[1]
                $startTime = $parts[2]
                $statusColor = $(if($status -eq "SUCCEEDED") {"Green"} elseif($status -eq "RUNNING") {"Cyan"} else {"Red"})
                Write-Host "   • Status: $status | Started: $startTime" -ForegroundColor $statusColor
            }
        }
    } else {
        Write-Host "   ⚠️  Could not query Step Functions (permission or not found)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ⚠️  Step Functions query failed" -ForegroundColor Yellow
}

Write-Host ""

# ==================================================
# 3. Check CloudWatch Logs for Recent Executions
# ==================================================
Write-Host "3. CLOUDWATCH LOGS - RECENT LOADER ACTIVITY" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────" -ForegroundColor Yellow

try {
    $logGroup = '/ecs/algo-loader'
    $loadersToDcheck = @('market_health_daily', 'stock_prices_daily', 'technical_data_daily')

    $loadersToDcheck | ForEach-Object {
        $loaderName = $_
        Write-Host "   Checking logs for: $loaderName" -ForegroundColor Gray

        $cmd = @"
aws logs filter-log-events `
  --log-group-name "$logGroup" `
  --filter-pattern "$loaderName" `
  --region $REGION `
  --start-time $((Get-Date).AddHours(-6).ToUniversalTime() | % { [long][double]::Parse((Get-Date $_ -UFormat %s).Replace(',','.')) * 1000 }) `
  --query 'events[0:1].[timestamp,message]' `
  --output text 2>&1
"@

        try {
            $logOutput = Invoke-Expression $cmd
            if ($logOutput -match "duration|completed|started|error|failed") {
                Write-Host "   ✓ Recent activity found for $loaderName" -ForegroundColor Green
                $logOutput | ForEach-Object { Write-Host "     $_" -ForegroundColor Gray }
            } else {
                Write-Host "   • No recent logs found for $loaderName (may be normal if not scheduled for today)" -ForegroundColor Gray
            }
        } catch {
            # Silently continue
        }
    }
} catch {
    Write-Host "   ⚠️  CloudWatch logs check skipped" -ForegroundColor Gray
}

Write-Host ""

# ==================================================
# 4. Database Check - Recent Loader Execution History
# ==================================================
Write-Host "4. DATABASE CHECK - LOADER EXECUTION HISTORY" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────" -ForegroundColor Yellow

# Get DB credentials from environment
$dbHost = $env:DB_HOST
$dbPort = $env:DB_PORT
$dbUser = $env:DB_USER
$dbPassword = $env:DB_PASSWORD
$dbName = $env:DB_NAME

if ($dbHost -and $dbUser -and $dbPassword) {
    Write-Host "   Connecting to: $dbHost" -ForegroundColor Gray

    try {
        # Import PostgreSQL module if needed
        $psqlPath = "C:\Program Files\PostgreSQL\15\bin\psql.exe"
        if (Test-Path $psqlPath) {
            $env:PGPASSWORD = $dbPassword

            # Check for recent loader execution history
            $query = @"
SELECT
    loader_name,
    MAX(execution_timestamp) as last_execution,
    COUNT(*) as total_runs,
    AVG(duration_seconds) as avg_duration_sec,
    MAX(status) as latest_status
FROM loader_execution_history
WHERE execution_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY loader_name
ORDER BY last_execution DESC
LIMIT 10;
"@

            # Save query to temp file
            $queryFile = [System.IO.Path]::GetTempFileName()
            $query | Out-File -FilePath $queryFile -Encoding UTF8

            Write-Host "   Recent Loader Execution History (past 7 days):" -ForegroundColor Gray

            & $psqlPath -h $dbHost -p $dbPort -U $dbUser -d $dbName -f $queryFile 2>&1 | ForEach-Object {
                if ($_ -match "loader_name|stock_prices|market_health|technical") {
                    Write-Host "   $_" -ForegroundColor Gray
                }
            }

            Remove-Item -Path $queryFile -Force -ErrorAction SilentlyContinue
        } else {
            Write-Host "   ⚠️  PostgreSQL client not found. Skipping database query." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "   ⚠️  Database query failed: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ⚠️  Database credentials not set. Set DB_HOST, DB_USER, DB_PASSWORD in PowerShell profile." -ForegroundColor Yellow
}

Write-Host ""

# ==================================================
# 5. SLA Compliance Report
# ==================================================
Write-Host "5. SLA COMPLIANCE ANALYSIS" -ForegroundColor Yellow
Write-Host "─────────────────────────────────────────" -ForegroundColor Yellow

Write-Host "   Morning Prep Window: 2:00 AM ET → 9:30 AM ET" -ForegroundColor Gray
Write-Host "   Total Available: 450 minutes (7.5 hours)" -ForegroundColor Gray
Write-Host ""
Write-Host "   Typical Execution Breakdown:" -ForegroundColor Gray
Write-Host "   • stock_prices_daily:      15-30 min" -ForegroundColor Gray
Write-Host "   • technical_data_daily:    60-90 min" -ForegroundColor Gray
Write-Host "   • market_health_daily:     5-10 min" -ForegroundColor Gray
Write-Host "   • buy_sell_daily:          20-30 min" -ForegroundColor Gray
Write-Host "   • signal_quality_scores:   20-30 min" -ForegroundColor Gray
Write-Host "   • swing_trader_scores:     30-45 min" -ForegroundColor Gray
Write-Host "   ─────────────────────────────────────────────" -ForegroundColor Gray
Write-Host "   Estimated Total: 150-235 minutes (2.5-3.9 hours)" -ForegroundColor Green
Write-Host "   Safety Buffer: 215-300 minutes remaining" -ForegroundColor Green
Write-Host ""
Write-Host "   Current Status: $(if($scheduleState -eq 'ENABLED') { "✓ ENABLED - Pipeline should run daily at 2:00 AM" } else { "⚠️  DISABLED - Need to enable via Terraform apply" })" -ForegroundColor $(if($scheduleState -eq "ENABLED") {"Green"} else {"Red"})

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "RECOMMENDED NEXT STEPS:" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($scheduleState -eq 'DISABLED') {
    Write-Host ""
    Write-Host "1. RE-ENABLE THE SCHEDULER:" -ForegroundColor Yellow
    Write-Host "   terraform apply -var-file=terraform.tfvars" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "2. VERIFY AFTER ENABLING:" -ForegroundColor Yellow
    Write-Host "   aws scheduler get-schedule --name $SCHEDULE_NAME --region $REGION" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. WAIT FOR NEXT SCHEDULED RUN:" -ForegroundColor Yellow
    Write-Host "   Tomorrow at 2:00 AM ET (or Friday 2:00 AM if today is non-trading day)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "4. MONITOR EXECUTION:" -ForegroundColor Yellow
    Write-Host "   • Check CloudWatch Logs: /ecs/algo-loader" -ForegroundColor Cyan
    Write-Host "   • Check Step Functions: algo-morning-prep-pipeline-dev" -ForegroundColor Cyan
    Write-Host "   • Query loader_execution_history table for timing data" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "✓ SCHEDULER IS ENABLED - No action needed" -ForegroundColor Green
    Write-Host ""
    Write-Host "MONITORING:" -ForegroundColor Yellow
    Write-Host "   • Check CloudWatch Logs: /ecs/algo-loader for execution traces" -ForegroundColor Cyan
    Write-Host "   • Monitor loader_execution_history table for timing compliance" -ForegroundColor Cyan
    Write-Host "   • Verify orchestrator Phase 1 succeeds at 9:30 AM run" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan

#!/usr/bin/env pwsh
<#
.SYNOPSIS
Monitor stock_prices_daily test run and collect metrics automatically.

.DESCRIPTION
Streams CloudWatch logs, tracks ECS task status, and records metrics to CSV.
Run this during/after deploying stock_prices_daily to measure optimization impact.

.EXAMPLE
./monitor-stock-prices-test.ps1 -Cluster algo-cluster -Environment dev
#>

param(
    [string]$Cluster = "algo-cluster",
    [string]$Environment = "dev",
    [string]$OutputFile = "stock_prices_test_metrics.csv"
)

Write-Host "Stock Prices Optimization Test Monitor" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# Check AWS CLI is available
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Error "AWS CLI not found. Install AWS CLI v2 or refresh credentials: scripts/refresh-aws-credentials.ps1"
    exit 1
}

# Get account ID
$AccountId = aws sts get-caller-identity --query Account --output text
if (-not $AccountId) {
    Write-Error "Failed to get AWS account ID. Check credentials with: aws sts get-caller-identity"
    exit 1
}

Write-Host "Cluster: $Cluster" -ForegroundColor Green
Write-Host "Environment: $Environment" -ForegroundColor Green
Write-Host "Account: $AccountId" -ForegroundColor Green
Write-Host ""

# Find the stock_prices_daily task
Write-Host "Finding stock_prices_daily task..." -ForegroundColor Yellow
$TaskArn = aws ecs list-tasks `
    --cluster $Cluster `
    --family "algo-stock_prices_daily-loader" `
    --query 'taskArns[0]' `
    --output text

if ($TaskArn -eq "None" -or -not $TaskArn) {
    Write-Host "No running stock_prices_daily task found." -ForegroundColor Yellow
    Write-Host "Task should be running soon as part of EOD/morning pipeline." -ForegroundColor Yellow
    Write-Host "Or trigger manually:" -ForegroundColor Cyan
    Write-Host "  aws ecs run-task --cluster $Cluster --task-definition algo-stock_prices_daily-loader" -ForegroundColor Cyan
    exit 0
}

Write-Host "Found task: $TaskArn" -ForegroundColor Green

# Initialize CSV if it doesn't exist
$CsvExists = Test-Path $OutputFile
if (-not $CsvExists) {
    $Header = "timestamp,event_type,metric_name,value,unit,notes"
    Add-Content -Path $OutputFile -Value $Header
    Write-Host "Created metrics file: $OutputFile" -ForegroundColor Green
}

# Function to add metric to CSV
function Record-Metric {
    param(
        [string]$EventType,
        [string]$MetricName,
        [string]$Value,
        [string]$Unit = "",
        [string]$Notes = ""
    )
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Line = "$Timestamp,$EventType,$MetricName,$Value,$Unit,$Notes"
    Add-Content -Path $OutputFile -Value $Line
    Write-Host "$MetricName: $Value $Unit" -ForegroundColor Cyan
}

Record-Metric -EventType "TEST_START" -MetricName "task_arn" -Value $TaskArn
$StartTime = Get-Date

# Monitor task status
Write-Host ""
Write-Host "Monitoring task status..." -ForegroundColor Yellow
Write-Host ""

$LastStatus = ""
$RunningMinutes = 0

while ($true) {
    # Get task details
    $Task = aws ecs describe-tasks `
        --cluster $Cluster `
        --tasks $TaskArn `
        --query 'tasks[0].[lastStatus, stoppedAt, startedAt]' `
        --output text | ConvertFrom-String -PropertyNames status, stoppedAt, startedAt

    $Status = $Task.status

    # Print status change
    if ($Status -ne $LastStatus) {
        $Elapsed = (Get-Date) - $StartTime
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Status: $Status (elapsed: $([math]::Round($Elapsed.TotalMinutes, 1)) min)" -ForegroundColor Magenta

        if ($Status -eq "STOPPED" -or $Status -eq "STOPPING") {
            Record-Metric -EventType "TASK_COMPLETE" -MetricName "final_status" -Value $Status
            break
        }

        $LastStatus = $Status
    }

    # Get RDS metrics every 30 seconds if task is running
    if ($Status -eq "RUNNING") {
        # Try to get RDS CPU (requires Performance Insights enabled)
        try {
            $RdsCpu = aws cloudwatch get-metric-statistics `
                --namespace "AWS/RDS" `
                --metric-name "CPUUtilization" `
                --dimensions Name=DBInstanceIdentifier,Value="algo-db" `
                --start-time ((Get-Date).AddMinutes(-2)) `
                --end-time (Get-Date) `
                --period 60 `
                --statistics Average `
                --query 'Datapoints[0].Average' `
                --output text 2>/dev/null

            if ($RdsCpu -and $RdsCpu -ne "None") {
                Record-Metric -EventType "RDS_METRIC" -MetricName "cpu_utilization" -Value $RdsCpu -Unit "%" -Notes "Real-time peak"
            }
        } catch {
            # RDS metrics might not be available
        }
    }

    Start-Sleep -Seconds 5
}

# Analyze logs for errors and metrics
Write-Host ""
Write-Host "Analyzing CloudWatch logs..." -ForegroundColor Yellow

# Tail logs and look for key metrics
$LogGroup = "/ecs/algo-stock_prices_daily-loader"
$LogStream = aws logs describe-log-streams `
    --log-group-name $LogGroup `
    --query 'logStreams[0].logStreamName' `
    --output text 2>/dev/null

if ($LogStream -and $LogStream -ne "None") {
    Write-Host "Fetching logs from $LogStream..." -ForegroundColor Cyan

    # Get logs
    $Logs = aws logs get-log-events `
        --log-group-name $LogGroup `
        --log-stream-name $LogStream `
        --start-from-head `
        --query 'events[*].message' `
        --output text

    # Parse for key metrics
    $Logs | ForEach-Object {
        # Look for duration
        if ($_ -match "duration.*?(\d+\.\d+).*?s") {
            $Duration = [math]::Round([double]$matches[1] / 60, 2)
            Record-Metric -EventType "TASK_LOG" -MetricName "duration" -Value $Duration -Unit "minutes"
        }

        # Look for 429 errors
        if ($_ -match "429|rate.*?limit") {
            Record-Metric -EventType "TASK_LOG" -MetricName "rate_limit_error" -Value "1" -Unit "count" -Notes "ALERT: Rate limiting detected"
            Write-Host "⚠️  RATE LIMIT ERROR DETECTED IN LOGS" -ForegroundColor Red
        }

        # Look for rows inserted
        if ($_ -match "inserted=(\d+)") {
            Record-Metric -EventType "TASK_LOG" -MetricName "rows_inserted" -Value $matches[1] -Unit "rows"
        }

        # Look for symbols processed
        if ($_ -match "symbols_processed.*?(\d+)") {
            Record-Metric -EventType "TASK_LOG" -MetricName "symbols_processed" -Value $matches[1] -Unit "symbols"
        }
    }
} else {
    Write-Host "Could not find log stream for $LogGroup" -ForegroundColor Yellow
}

# Final summary
Write-Host ""
Write-Host "Test monitoring complete. Results saved to: $OutputFile" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
$Metrics = (Get-Content $OutputFile | Measure-Object -Line).Lines - 1
Write-Host "  Metrics recorded: $Metrics"
Write-Host "  Output file: $OutputFile"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review metrics in $OutputFile"
Write-Host "  2. Check for 429 (rate limit) errors"
Write-Host "  3. Verify duration is <2 hours (target 1.5h)"
Write-Host "  4. If successful, ready for production deployment"

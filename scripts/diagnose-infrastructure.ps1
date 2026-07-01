# Infrastructure Diagnostics Script
# Purpose: Identify why scheduled jobs have stopped running
# Run this to gather data for AWS infrastructure troubleshooting

param(
    [string]$Environment = "dev",
    [string]$AWSRegion = "us-east-1",
    [string]$ProjectName = "algo"
)

Write-Host "=== Infrastructure Diagnostics ===" -ForegroundColor Green
Write-Host "Environment: $Environment | Region: $AWSRegion | Project: $ProjectName`n"

# Helper function to check AWS CLI availability
function Test-AWSCli {
    try {
        $null = aws --version
        return $true
    } catch {
        Write-Host "ERROR: AWS CLI not found. Install it or run: pip install awscli" -ForegroundColor Red
        return $false
    }
}

if (-not (Test-AWSCli)) {
    exit 1
}

# Helper function to run AWS commands with error handling
function Invoke-AWSCommand {
    param(
        [string]$Command,
        [string]$Description
    )

    Write-Host "→ $Description..." -ForegroundColor Cyan
    try {
        $result = Invoke-Expression $Command 2>&1
        if ($LASTEXITCODE -eq 0) {
            return $result
        } else {
            Write-Host "  ERROR: $result" -ForegroundColor Red
            return $null
        }
    } catch {
        Write-Host "  EXCEPTION: $_" -ForegroundColor Red
        return $null
    }
}

# 1. Check EventBridge Scheduler Rules
Write-Host "`n=== 1. EventBridge Scheduler Rules ===" -ForegroundColor Yellow

$schedules = Invoke-AWSCommand `
    "aws scheduler list-schedules --region $AWSRegion --output json" `
    "Listing all EventBridge Scheduler schedules"

if ($schedules) {
    $schedulesJson = $schedules | ConvertFrom-Json
    $pipelineSchedules = $schedulesJson.Schedules | Where-Object { $_.Name -like "*$ProjectName*" }

    if ($pipelineSchedules) {
        Write-Host "`nFound $($pipelineSchedules.Count) pipeline schedules:" -ForegroundColor Green
        foreach ($schedule in $pipelineSchedules) {
            $state = $schedule.State
            $stateColor = if ($state -eq "ENABLED") { "Green" } else { "Red" }
            Write-Host "  [$state] $($schedule.Name)" -ForegroundColor $stateColor
            Write-Host "    Schedule: $($schedule.ScheduleExpression)"
            Write-Host "    Timezone: $($schedule.ScheduleExpressionTimezone)"
        }
    } else {
        Write-Host "  No pipeline schedules found!" -ForegroundColor Red
    }
} else {
    Write-Host "  Failed to query schedules" -ForegroundColor Red
}

# 2. Check Step Functions Executions
Write-Host "`n=== 2. Step Functions Recent Executions ===" -ForegroundColor Yellow

$eodPipelineName = "$ProjectName-eod-pipeline-$Environment"
$executions = Invoke-AWSCommand `
    "aws stepfunctions list-executions --state-machine-arn arn:aws:states:$AWSRegion`:`(aws sts get-caller-identity --query Account --output text)`:stateMachine:$eodPipelineName --region $AWSRegion --max-results 5 --output json" `
    "Listing last 5 EOD pipeline executions"

if ($executions) {
    try {
        $executionsJson = $executions | ConvertFrom-Json
        if ($executionsJson.executions.Count -gt 0) {
            Write-Host "`nLast 5 executions:" -ForegroundColor Green
            foreach ($exec in $executionsJson.executions) {
                $statusColor = if ($exec.status -eq "FAILED") { "Red" } elseif ($exec.status -eq "SUCCEEDED") { "Green" } else { "Yellow" }
                $duration = [math]::Round(($exec.stopDate - $exec.startDate).TotalMinutes, 1)
                Write-Host "  [$($exec.status)] $($exec.name) - Started: $($exec.startDate)" -ForegroundColor $statusColor
                if ($exec.stopDate) {
                    Write-Host "    Duration: ${duration} min"
                }
            }
        } else {
            Write-Host "  No recent executions found - scheduler may not have fired!" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Failed to parse executions" -ForegroundColor Red
    }
} else {
    Write-Host "  Failed to query executions" -ForegroundColor Red
}

# 3. Check RDS Instance Status
Write-Host "`n=== 3. RDS Database Status ===" -ForegroundColor Yellow

$rdsInstance = Invoke-AWSCommand `
    "aws rds describe-db-instances --db-instance-identifier algo-db --region $AWSRegion --output json" `
    "Checking RDS instance status"

if ($rdsInstance) {
    try {
        $rdsJson = $rdsInstance | ConvertFrom-Json
        if ($rdsJson.DBInstances.Count -gt 0) {
            $db = $rdsJson.DBInstances[0]
            $statusColor = if ($db.DBInstanceStatus -eq "available") { "Green" } else { "Red" }
            Write-Host "  [$($db.DBInstanceStatus)] $($db.DBInstanceIdentifier)" -ForegroundColor $statusColor
            Write-Host "    Endpoint: $($db.Endpoint.Address):$($db.Endpoint.Port)"
            Write-Host "    Engine: $($db.Engine) $($db.EngineVersion)"
            Write-Host "    Class: $($db.DBInstanceClass)"
            Write-Host "    Allocated Storage: $($db.AllocatedStorage) GB"
        } else {
            Write-Host "  No RDS instance found!" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Failed to parse RDS response" -ForegroundColor Red
    }
} else {
    Write-Host "  Failed to query RDS" -ForegroundColor Red
}

# 4. Check DynamoDB Lock Tables
Write-Host "`n=== 4. DynamoDB Lock Tables ===" -ForegroundColor Yellow

$lockTables = @(
    "orchestrator-locks",
    "loader-locks",
    "loader-status"
)

foreach ($tablePrefix in $lockTables) {
    $tableName = "$ProjectName-$tablePrefix-$Environment"
    $table = Invoke-AWSCommand `
        "aws dynamodb describe-table --table-name $tableName --region $AWSRegion --output json" `
        "Checking $tableName status"

    if ($table) {
        try {
            $tableJson = $table | ConvertFrom-Json
            $status = $tableJson.Table.TableStatus
            $statusColor = if ($status -eq "ACTIVE") { "Green" } else { "Red" }
            Write-Host "  [$status] $tableName" -ForegroundColor $statusColor
            Write-Host "    Items: $($tableJson.Table.ItemCount)"
            Write-Host "    Read Capacity: $($tableJson.Table.ProvisionedThroughput.ReadCapacityUnits)"
            Write-Host "    Write Capacity: $($tableJson.Table.ProvisionedThroughput.WriteCapacityUnits)"
        } catch {
            Write-Host "  Failed to parse table info" -ForegroundColor Red
        }
    } else {
        Write-Host "  Table not found or not accessible" -ForegroundColor Red
    }
}

# 5. Check CloudWatch Logs for Recent Errors
Write-Host "`n=== 5. CloudWatch Logs (Last 2 hours) ===" -ForegroundColor Yellow

$logGroup = "/aws/states/$ProjectName-eod-pipeline-$Environment"
$twoHoursAgo = [int]([DateTime]::UtcNow.Subtract([TimeSpan]::FromHours(2)).UnixTimeMilliseconds)

$logs = Invoke-AWSCommand `
    "aws logs filter-log-events --log-group-name '$logGroup' --start-time $twoHoursAgo --region $AWSRegion --output json" `
    "Checking Step Functions logs for errors"

if ($logs) {
    try {
        $logsJson = $logs | ConvertFrom-Json
        $errors = $logsJson.events | Where-Object { $_.message -like "*error*" -or $_.message -like "*failed*" -or $_.message -like "*ERROR*" }

        if ($errors.Count -gt 0) {
            Write-Host "  Found $($errors.Count) error messages:" -ForegroundColor Red
            foreach ($error in $errors | Select-Object -First 5) {
                Write-Host "    - $($error.message)" -ForegroundColor Red
            }
        } else {
            Write-Host "  No errors in recent logs" -ForegroundColor Green
        }
    } catch {
        Write-Host "  Failed to parse logs" -ForegroundColor Red
    }
} else {
    Write-Host "  Failed to query logs" -ForegroundColor Red
}

# 6. Check IAM Permissions
Write-Host "`n=== 6. IAM Role Permissions ===" -ForegroundColor Yellow

$schedulerRole = Invoke-AWSCommand `
    "aws iam list-role-policies --role-name $ProjectName-eventbridge-scheduler-role-$Environment --region $AWSRegion --output json" `
    "Checking EventBridge Scheduler role policies"

if ($schedulerRole) {
    try {
        $rolesJson = $schedulerRole | ConvertFrom-Json
        if ($rolesJson.PolicyNames.Count -gt 0) {
            Write-Host "  EventBridge Scheduler role policies:" -ForegroundColor Green
            foreach ($policy in $rolesJson.PolicyNames) {
                Write-Host "    ✓ $policy"
            }
        } else {
            Write-Host "  WARNING: No inline policies found!" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Failed to parse IAM policies" -ForegroundColor Red
    }
} else {
    Write-Host "  Failed to query IAM role" -ForegroundColor Red
}

Write-Host "`n=== Diagnostics Complete ===" -ForegroundColor Green
Write-Host "`nNext steps if infrastructure is down:" -ForegroundColor Cyan
Write-Host "1. Verify RDS is running (not stopped by cost-save scheduler)"
Write-Host "2. Check EventBridge Scheduler rules are ENABLED"
Write-Host "3. Verify IAM roles have correct permissions"
Write-Host "4. Manually trigger EOD pipeline if needed: invoke-stepfunction.ps1"

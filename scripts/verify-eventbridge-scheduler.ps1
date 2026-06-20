#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify EventBridge Scheduler integration with Step Functions is working.

.DESCRIPTION
Checks that:
1. All scheduler schedules are in ENABLED state
2. IAM role has required permissions
3. Step Functions state machines are accessible
4. CloudWatch Log Group exists for scheduler output

.EXAMPLE
./scripts/verify-eventbridge-scheduler.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Verifying EventBridge Scheduler Integration..." -ForegroundColor Cyan

# Check if AWS CLI is available
try {
    $AwsVersion = aws --version 2>&1
    Write-Host "OK: AWS CLI $AwsVersion" -ForegroundColor Green
} catch {
    Write-Host "FAIL: AWS CLI not available or not configured" -ForegroundColor Red
    exit 1
}

$Region = "us-east-1"
$Project = "algo"
$Environment = "dev"

# 1. Check scheduler schedules
Write-Host "`n[1/4] Checking EventBridge Scheduler Schedules..." -ForegroundColor Yellow
$Schedules = @(
    "$Project-morning-pipeline-$Environment",
    "$Project-afternoon-update-pipeline-$Environment",
    "$Project-preclose-update-pipeline-$Environment",
    "$Project-eod-pipeline-$Environment"
)

foreach ($ScheduleName in $Schedules) {
    try {
        $Schedule = aws scheduler get-schedule --name $ScheduleName --region $Region --output json 2>$null | ConvertFrom-Json
        if ($Schedule.State -eq "ENABLED") {
            Write-Host "  ✓ $ScheduleName: ENABLED" -ForegroundColor Green
        } else {
            Write-Host "  ✗ $ScheduleName: $($Schedule.State) (should be ENABLED)" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ✗ $ScheduleName: NOT FOUND" -ForegroundColor Red
    }
}

# 2. Check Step Functions state machines
Write-Host "`n[2/4] Checking Step Functions State Machines..." -ForegroundColor Yellow
$StateMachines = @(
    "$Project-eod-pipeline-$Environment",
    "$Project-morning-prep-pipeline-$Environment",
    "$Project-intraday-afternoon-update-$Environment",
    "$Project-intraday-preclose-update-$Environment"
)

foreach ($SMName in $StateMachines) {
    try {
        $SM = aws stepfunctions list-state-machines --region $Region --output json 2>$null | ConvertFrom-Json |
            Select-Object -ExpandProperty stateMachines |
            Where-Object { $_.name -eq $SMName }

        if ($SM) {
            $Status = $SM.stateMachineArn
            Write-Host "  ✓ $SMName: $($Status.Split(':')[-1])" -ForegroundColor Green
        } else {
            Write-Host "  ✗ $SMName: NOT FOUND" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ✗ $SMName: ERROR - $_" -ForegroundColor Red
    }
}

# 3. Check CloudWatch Log Group
Write-Host "`n[3/4] Checking CloudWatch Log Group..." -ForegroundColor Yellow
try {
    $LogGroup = aws logs describe-log-groups --log-group-name-prefix "/aws/scheduler/$Project-pipeline" --region $Region --output json 2>$null | ConvertFrom-Json
    if ($LogGroup.logGroups) {
        $LG = $LogGroup.logGroups[0]
        Write-Host "  ✓ Log Group: $($LG.logGroupName)" -ForegroundColor Green
        Write-Host "    - Retention: $($LG.retentionInDays) days" -ForegroundColor Cyan
    } else {
        Write-Host "  ✗ Log Group NOT FOUND (will be created on first deployment)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ ERROR checking log group: $_" -ForegroundColor Red
}

# 4. Check IAM role permissions
Write-Host "`n[4/4] Checking IAM Role Permissions..." -ForegroundColor Yellow
try {
    $RoleName = "$Project-eventbridge-scheduler-$Environment"
    $Policy = aws iam get-role-policy --role-name $RoleName --policy-name "$Project-eventbridge-scheduler-policy" --region $Region --output json 2>$null | ConvertFrom-Json

    if ($Policy.RolePolicyDocument) {
        $Statements = $Policy.RolePolicyDocument.Statement
        Write-Host "  ✓ IAM Role: $RoleName" -ForegroundColor Green

        # Check for required permissions
        $Perms = @("states:StartExecution", "logs:CreateLogDelivery", "lambda:InvokeFunction", "ecs:RunTask", "iam:PassRole")
        foreach ($Perm in $Perms) {
            $Found = $Statements | Where-Object { $_.Action -contains $Perm -or $_.Action -like "*$Perm*" }
            if ($Found) {
                Write-Host "    ✓ Has permission: $Perm" -ForegroundColor Green
            } else {
                Write-Host "    ✗ Missing permission: $Perm" -ForegroundColor Red
            }
        }
    }
} catch {
    Write-Host "  ✗ ERROR: Could not verify IAM role" -ForegroundColor Red
}

Write-Host "`n[Summary] EventBridge Scheduler verification complete." -ForegroundColor Cyan
Write-Host "Next steps: Deploy terraform changes with 'terraform apply' if any issues found above." -ForegroundColor Cyan

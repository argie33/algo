#!/usr/bin/env pwsh
<#
.SYNOPSIS
Deploy CloudWatch monitoring dashboard for SLA compliance tracking.

.DESCRIPTION
Creates a comprehensive CloudWatch dashboard showing:
- Data freshness (age of price_daily, technical_data_daily, swing_trader_scores)
- Loader execution timing (stock_prices_daily, technical_data_daily, market_health_daily)
- Morning prep completion status (started, in-progress, completed)
- Orchestrator success rate (4 daily runs at 9:30 AM, 1 PM, 3 PM, 5:30 PM)
- RDS connection count and CPU utilization
- API Lambda concurrent executions and error rate

The dashboard is readable at a glance to identify SLA violations quickly.
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$AwsProfile = "algo-developer",

    [Parameter(Mandatory=$false)]
    [string]$DashboardName = "algo-sla-monitoring",

    [Parameter(Mandatory=$false)]
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

Write-Host "Deploying SLA monitoring dashboard..." -ForegroundColor Cyan

# Dashboard body JSON configuration
$dashboardBody = @{
    widgets = @(
        # Row 1: Data Freshness Indicators
        @{
            type = "metric"
            properties = @{
                metrics = @(
                    @( "AWS/RDS", "DatabaseConnections", @{ stat = "Average"; label = "RDS Connections" } ),
                    @( "AWS/RDS", "CPUUtilization", @{ stat = "Average"; label = "RDS CPU %" } )
                )
                period = 300
                stat = "Average"
                region = $Region
                title = "RDS Database Health"
                yAxis = @{ left = @{ min = 0 } }
            }
            x = 0
            y = 0
            width = 12
            height = 6
        },

        # Row 1: API Lambda Metrics
        @{
            type = "metric"
            properties = @{
                metrics = @(
                    @( "AWS/Lambda", "ConcurrentExecutions", @{ dimensions = @{ FunctionName = "algo-api-dev" }; stat = "Average" } ),
                    @( "AWS/Lambda", "Errors", @{ dimensions = @{ FunctionName = "algo-api-dev" }; stat = "Sum" } ),
                    @( "AWS/Lambda", "Duration", @{ dimensions = @{ FunctionName = "algo-api-dev" }; stat = "Average" } )
                )
                period = 300
                stat = "Average"
                region = $Region
                title = "API Lambda Performance"
                yAxis = @{ left = @{ min = 0 } }
            }
            x = 12
            y = 0
            width = 12
            height = 6
        },

        # Row 2: Orchestrator Execution Success
        @{
            type = "log"
            properties = @{
                query = @"
fields @timestamp, overall_status
| filter ispresent(overall_status)
| stats count(*) as total_runs, count(if(overall_status='success', 1)) as successful_runs by bin(5m)
| fields @timestamp, successful_runs, total_runs
| sort @timestamp desc
| limit 20
"@
                region = $Region
                title = "Orchestrator Success Rate (5-min windows)"
                queryId = "sla-orchestrator-success"
            }
            x = 0
            y = 6
            width = 12
            height = 6
        },

        # Row 2: Data Freshness Status
        @{
            type = "log"
            properties = @{
                query = @"
fields @timestamp, loader_name, execution_timestamp, duration_seconds, status
| filter loader_name in ['stock_prices_daily', 'technical_data_daily', 'market_health_daily', 'swing_trader_scores']
| stats max(execution_timestamp) as latest_execution, max(duration_seconds) as max_duration by loader_name
| sort latest_execution desc
"@
                region = $Region
                title = "Loader Execution Status (Latest Run)"
                queryId = "sla-loader-status"
            }
            x = 12
            y = 6
            width = 12
            height = 6
        },

        # Row 3: Morning Prep SLA Compliance
        @{
            type = "metric"
            properties = @{
                metrics = @(
                    @( "AWS/States", "ExecutionsFailed", @{ dimensions = @{ StateMachineArn = "arn:aws:states:us-east-1:*:stateMachine:algo-morning-prep-pipeline-dev" }; stat = "Sum" } ),
                    @( "AWS/States", "ExecutionsSucceeded", @{ dimensions = @{ StateMachineArn = "arn:aws:states:us-east-1:*:stateMachine:algo-morning-prep-pipeline-dev" }; stat = "Sum" } ),
                    @( "AWS/States", "ExecutionTime", @{ dimensions = @{ StateMachineArn = "arn:aws:states:us-east-1:*:stateMachine:algo-morning-prep-pipeline-dev" }; stat = "Average" } )
                )
                period = 300
                stat = "Average"
                region = $Region
                title = "Morning Prep Pipeline (Step Functions)"
                yAxis = @{ left = @{ min = 0 } }
            }
            x = 0
            y = 12
            width = 12
            height = 6
        },

        # Row 3: EventBridge Scheduler Status
        @{
            type = "log"
            properties = @{
                query = @"
fields @timestamp, @message
| filter @logStream like /scheduler/
| stats count(*) as scheduler_events by bin(5m)
| sort @timestamp desc
| limit 10
"@
                region = $Region
                title = "EventBridge Scheduler Events (5-min windows)"
                queryId = "sla-scheduler-events"
            }
            x = 12
            y = 12
            width = 12
            height = 6
        },

        # Row 4: Critical Alerts Text
        @{
            type = "text"
            properties = @{
                markdown = @"
## SLA Monitoring Guide

### Green Indicators (All Good)
- **RDS Connections**: < 200 (plenty of headroom, max 500)
- **RDS CPU**: < 30% (healthy resource utilization)
- **API Lambda Errors**: 0 per 5-min (no failures)
- **Orchestrator Success**: 100% (all 4 daily runs succeed)
- **Loader Status**: All completed within SLA (<4 hours total for morning prep)
- **Data Freshness**: All critical tables ≤ 1 trading day old

### Yellow Indicators (Watch Closely)
- **RDS Connections**: 200-350 (approaching saturation)
- **RDS CPU**: 30-60% (significant load)
- **API Lambda Errors**: 1-5 per 5-min (minor issues)
- **Orchestrator Success**: 75-99% (occasional failures)
- **Loader Timing**: 3.5-4.5 hours (tight to SLA window)
- **Data Freshness**: 1-3 trading days old

### Red Indicators (Action Required)
- **RDS Connections**: > 350 (risk of pool exhaustion)
- **RDS CPU**: > 60% (high load, consider scaling)
- **API Lambda Errors**: > 10 per 5-min (systemic failures)
- **Orchestrator Success**: < 75% (frequent failures)
- **Loader Timing**: > 4.5 hours (exceeds SLA window)
- **Data Freshness**: > 3 trading days old (data stale, trading at risk)

### Common Issues & Resolution

**Morning prep didn't start at 2:00 AM:**
1. Check EventBridge scheduler: `aws scheduler get-schedule --name algo-morning-pipeline-dev`
2. If State=DISABLED: Re-enable via Terraform: `terraform apply`
3. Check Step Functions: `aws stepfunctions list-executions --state-machine-arn arn:aws:states:...`

**Data is stale:**
1. Check loader_execution_history: Which loaders failed?
2. Check CloudWatch logs for /ecs/algo-loader
3. If connection errors: Run `scripts/refresh-aws-credentials.ps1`
4. If specific loader slow: Check RDS CPU and slow query logs

**API Lambda errors spiking:**
1. Check Lambda timeout (should be 30+ seconds)
2. Check RDS connection count (might be exhausted)
3. Check RDS slow queries (might be blocking API)
4. Restart Lambda if hung: `aws lambda invoke --function-name algo-api-dev --payload '{}' /dev/null`

"@
            }
            x = 0
            y = 18
            width = 24
            height = 12
        }
    )
} | ConvertTo-Json -Depth 10

# Save dashboard body to temp file
$tempFile = [System.IO.Path]::GetTempFileName()
$dashboardBody | Out-File -FilePath $tempFile -Encoding UTF8

try {
    Write-Host "Deploying dashboard: $DashboardName" -ForegroundColor Yellow

    # Deploy dashboard
    $result = aws cloudwatch put-dashboard `
        --dashboard-name $DashboardName `
        --dashboard-body "file://$tempFile" `
        --profile $AwsProfile `
        --region $Region 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "SUCCESS: Dashboard deployed successfully!" -ForegroundColor Green
        Write-Host "Dashboard URL: https://console.aws.amazon.com/cloudwatch/home?region=$Region#dashboards:name=$DashboardName"
    } else {
        Write-Host "FAILED: Could not deploy dashboard" -ForegroundColor Red
        Write-Host $result
        exit 1
    }
}
finally {
    # Cleanup
    Remove-Item -Force $tempFile -ErrorAction SilentlyContinue
}

Write-Host "`nDashboard deployment complete!" -ForegroundColor Green
Write-Host "The dashboard provides real-time SLA monitoring and can be accessed at:" -ForegroundColor Cyan
Write-Host "https://console.aws.amazon.com/cloudwatch/home?region=$Region#dashboards:name=$DashboardName" -ForegroundColor Cyan

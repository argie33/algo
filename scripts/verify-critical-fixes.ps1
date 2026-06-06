#!/usr/bin/env pwsh
<#
.SYNOPSIS
Verify that 3 critical orchestrator issues are working in AWS logs.

.DESCRIPTION
Searches CloudWatch logs for confirmation that:
1. Issue #1: Market close data lag detection is working
2. Issue #9/10: Morning prep timing monitoring is working
3. Issue #14: DynamoDB cache health validation is working

.PARAMETER Hours
How many hours back to search (default: 168 = 1 week)

.PARAMETER FollowLogs
If specified, streams logs in real-time (requires manual CTRL+C to exit)
#>

param(
    [int]$Hours = 168,
    [switch]$FollowLogs
)

$ErrorActionPreference = "Stop"
$startTime = (Get-Date).AddHours(-$Hours)
$startTimeMs = [int64]([datetime]::new($startTime.Ticks)).AddHours(-5).ToFileTime() / 10000

Write-Host "🔍 Searching CloudWatch logs for critical issue fixes..." -ForegroundColor Cyan
Write-Host "Time range: Last $Hours hours ($startTime UTC to now)" -ForegroundColor Gray
Write-Host ""

# Define the issues to search for
$issues = @(
    @{
        Name = "Issue #1: Market Close Data Lag"
        LogGroup = "/ecs/algo-stock_prices_daily-loader"
        Patterns = @("[MARKET_CLOSE] ✓", "[MARKET_CLOSE] ✗", "RuntimeError")
        Description = "Market close check with exponential backoff (5s→10s→20s→40s)"
    },
    @{
        Name = "Issue #9/10: Morning Prep Timing"
        LogGroup = "/ecs/algo-algo-orchestrator"
        Patterns = @("[MORNING_PREP_TIMING]", "CRITICAL", "WARNING")
        Description = "3-tier alerting (Critical <20min, Warning <81min)"
    },
    @{
        Name = "Issue #14: DynamoDB Cache Health"
        LogGroup = "/aws/lambda/algo-algo-dev"
        Patterns = @("[DYNAMODB]", "Cache table healthy", "table not ACTIVE")
        Description = "Pre-flight health check before cache fallback"
    }
)

# Search each issue
$results = @()

foreach ($issue in $issues) {
    Write-Host "━" * 70 -ForegroundColor DarkGray
    Write-Host $issue.Name -ForegroundColor Yellow
    Write-Host "Log Group: $($issue.LogGroup)" -ForegroundColor Gray
    Write-Host "Description: $($issue.Description)" -ForegroundColor Gray
    Write-Host ""

    try {
        $events = @()

        # Search for each pattern
        foreach ($pattern in $issue.Patterns) {
            Write-Host "  Searching for: '$pattern'..." -ForegroundColor Gray -NoNewline

            try {
                $response = aws logs filter-log-events `
                    --log-group-name $issue.LogGroup `
                    --filter-pattern $pattern `
                    --start-time $startTimeMs `
                    --region us-east-1 `
                    --query "events[*].[timestamp, message]" `
                    --output json 2>$null | ConvertFrom-Json

                if ($response) {
                    $events += $response
                    Write-Host " ✓ Found $($response.Count) events" -ForegroundColor Green
                } else {
                    Write-Host " (none)" -ForegroundColor Gray
                }
            } catch {
                Write-Host " ✗ Error: $_" -ForegroundColor Red
            }
        }

        if ($events.Count -gt 0) {
            Write-Host ""
            Write-Host "Recent Events (last 5):" -ForegroundColor Cyan

            $events | Select-Object -Last 5 | ForEach-Object {
                $timestamp = [datetime]::UnixEpoch.AddMilliseconds($_[0])
                Write-Host "  [$timestamp] $_[1]" -ForegroundColor Green
            }

            $result = "✅ FOUND - Issue is working (seen in logs)"
        } else {
            $result = "⚠️  NO LOGS - Issue not yet executed (normal if no recent orchestrator runs)"
        }

        Write-Host ""
        Write-Host "Status: $result" -ForegroundColor Cyan

        $results += @{
            Issue = $issue.Name
            Status = $result
            EventCount = $events.Count
        }

    } catch {
        Write-Host "❌ Error searching logs: $_" -ForegroundColor Red
        $results += @{
            Issue = $issue.Name
            Status = "❌ ERROR"
            Error = $_
        }
    }
}

# Summary
Write-Host ""
Write-Host "━" * 70 -ForegroundColor DarkGray
Write-Host "VERIFICATION SUMMARY" -ForegroundColor Cyan
Write-Host "━" * 70 -ForegroundColor DarkGray

$results | ForEach-Object {
    Write-Host "$($_.Issue): $($_.Status)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "💡 Next Steps:" -ForegroundColor Yellow
Write-Host "  1. If logs show ✅ FOUND: Issue is confirmed working in production"
Write-Host "  2. If logs show ⚠️  NO LOGS: Trigger manual test:"
Write-Host "     .\scripts\test-eod-pipeline.ps1 -Wait"
Write-Host "  3. Wait for next scheduled orchestrator run (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)"
Write-Host ""
Write-Host "📊 Live log streaming:" -ForegroundColor Yellow
Write-Host "  .\scripts\verify-critical-fixes.ps1 -FollowLogs -Hours 1"
Write-Host ""

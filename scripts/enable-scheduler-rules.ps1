# Emergency: Enable All Scheduler Rules
# Use this if EventBridge Scheduler rules have been accidentally disabled

param(
    [string]$Environment = "dev",
    [string]$AWSRegion = "us-east-1",
    [string]$ProjectName = "algo",
    [switch]$DryRun
)

Write-Host "=== ENABLING EVENTBRIDGE SCHEDULER RULES ===" -ForegroundColor Green
Write-Host "Environment: $Environment | Region: $AWSRegion"
Write-Host "Dry Run: $DryRun`n"

# Rules that must be ENABLED for pipelines to work
$requiredRules = @(
    @{ name = "$ProjectName-eod-pipeline-$Environment"; description = "EOD data pipeline (4:05 PM ET)" },
    @{ name = "$ProjectName-morning-pipeline-$Environment"; description = "Morning prep pipeline (2:00 AM ET)" },
    @{ name = "$ProjectName-afternoon-update-pipeline-$Environment"; description = "Afternoon update (12:50 PM ET)" },
    @{ name = "$ProjectName-preclose-update-pipeline-$Environment"; description = "Pre-close update (2:50 PM ET)" }
)

# Also check orchestrator rules
$orchestratorRules = @(
    @{ name = "$ProjectName-algo-schedule-morning-$Environment"; description = "Morning orchestrator (9:30 AM ET)" },
    @{ name = "$ProjectName-algo-schedule-afternoon-$Environment"; description = "Afternoon orchestrator (1:00 PM ET)" },
    @{ name = "$ProjectName-algo-schedule-preclose-$Environment"; description = "Pre-close orchestrator (3:00 PM ET)" }
)

$allRules = $requiredRules + $orchestratorRules
$enabledCount = 0
$disabledCount = 0

foreach ($rule in $allRules) {
    Write-Host "Checking: $($rule.description)" -ForegroundColor Cyan
    Write-Host "  Rule: $($rule.name)"

    # Check current status
    try {
        $status = aws scheduler get-schedule `
            --name $rule.name `
            --region $AWSRegion `
            --query 'State' `
            --output text 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ⚠️  Not found or inaccessible" -ForegroundColor Yellow
            continue
        }

        if ($status -eq "ENABLED") {
            Write-Host "  ✅ Already ENABLED" -ForegroundColor Green
            $enabledCount++
        } else {
            Write-Host "  ⚠️  Currently $status - ENABLING..." -ForegroundColor Yellow

            if ($DryRun) {
                Write-Host "    [DRY RUN] Would execute: aws scheduler update-schedule --name $($rule.name) --state ENABLED" -ForegroundColor Yellow
            } else {
                $result = aws scheduler update-schedule `
                    --name $rule.name `
                    --state ENABLED `
                    --region $AWSRegion 2>&1

                if ($LASTEXITCODE -eq 0) {
                    Write-Host "    ✅ ENABLED successfully" -ForegroundColor Green
                    $enabledCount++
                } else {
                    Write-Host "    ❌ Failed to enable: $result" -ForegroundColor Red
                }
            }
        }
    } catch {
        Write-Host "  ❌ Error: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Green
Write-Host "Enabled: $enabledCount"
Write-Host "Status: $(if ($DryRun) { '[DRY RUN] No changes made' } else { 'Rules enabled successfully' })"
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Verify pipelines are firing: ./scripts/verify-pipeline-execution.ps1"
Write-Host "2. Monitor data freshness in RDS"
Write-Host "3. If still not working: ./scripts/diagnose-infrastructure.ps1"

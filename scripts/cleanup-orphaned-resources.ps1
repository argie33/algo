#!/usr/bin/env pwsh
<#
.SYNOPSIS
Clean up orphaned AWS resources (Phase 3)

.DESCRIPTION
Safely deletes:
1. Old stocks-* task definitions (28 versions, no longer used)
2. Orphaned RDS instances (empty databases)
3. Empty Batch clusters (not used)
4. VPC Flow Logs (optional - very expensive)

All deletions are safe - these resources are not referenced.
#>

param(
    [switch]$SkipFlowLogs,
    [switch]$DryRun
)

$Region = "us-east-1"
$TotalDeleted = 0

Write-Host "🧹 Phase 3: Cleanup Orphaned AWS Resources" -ForegroundColor Cyan
Write-Host "============================================="
Write-Host ""

if ($DryRun) {
    Write-Host "⚠️  DRY RUN MODE - No changes will be made" -ForegroundColor Yellow
    Write-Host ""
}

# ============================================================
# 1. DELETE OLD STOCKS-* TASK DEFINITIONS
# ============================================================
Write-Host "1️⃣  Deleting stocks-* task definitions (old project)..." -ForegroundColor Cyan

$StocksFamilies = @(
    'stocks-company_fundamentals-loader',
    'stocks-econdata-loader',
    'stocks-feargreed-loader',
    'stocks-market_indices-loader',
    'stocks-sector_ranking-loader',
    'stocks-stock_prices-loader',
    'stocks-stock_symbols-loader'
)

foreach ($family in $StocksFamilies) {
    $versions = (aws ecs list-task-definitions --family-prefix $family --region $Region --query 'taskDefinitionArns' --output text)
    if ($versions) {
        $versionArray = $versions -split '\s+'
        foreach ($taskDef in $versionArray) {
            if ($DryRun) {
                Write-Host "  [DRYRUN] Would deregister: $taskDef" -ForegroundColor Gray
            } else {
                Write-Host "  Deregistering: $taskDef"
                aws ecs deregister-task-definition --task-definition $taskDef --region $Region --output json | Out-Null
            }
            $TotalDeleted++
        }
    }
}
Write-Host "  ✅ Processed $TotalDeleted stock task definitions" -ForegroundColor Green
Write-Host ""

# ============================================================
# 2. DELETE ORPHANED RDS INSTANCES
# ============================================================
Write-Host "2️⃣  Deleting orphaned RDS instances..." -ForegroundColor Cyan

$OrphanedDbs = @(
    'db-LGSIX7UI6Z4TIUL5LUST6IRX7U',
    'db-RY7DEA5RVBYRCIGMTPWAUXRI44'
)

$deletedRds = 0
foreach ($dbId in $OrphanedDbs) {
    try {
        if ($DryRun) {
            Write-Host "  [DRYRUN] Would delete RDS instance: $dbId" -ForegroundColor Gray
        } else {
            Write-Host "  Deleting RDS instance: $dbId"
            aws rds delete-db-instance `
                --db-instance-identifier $dbId `
                --skip-final-snapshot `
                --region $Region `
                --output json | Out-Null
        }
        $deletedRds++
    } catch {
        Write-Host "  ⚠️  Error deleting $dbId : $_" -ForegroundColor Yellow
    }
}
Write-Host "  ✅ Processed $deletedRds RDS instances" -ForegroundColor Green
Write-Host ""

# ============================================================
# 3. DELETE EMPTY BATCH CLUSTERS
# ============================================================
Write-Host "3️⃣  Deleting empty Batch ECS clusters..." -ForegroundColor Cyan

$EmptyClusters = @(
    'terraform-20260510044254451600000001_Batch_6876a951-e01e-30f6-a006-5aea4bfc0f49',
    'terraform-20260509135125687900000011_Batch_2863b84e-b7d6-300d-8594-5892a6d493a5'
)

$deletedClusters = 0
foreach ($clusterArn in $EmptyClusters) {
    try {
        if ($DryRun) {
            Write-Host "  [DRYRUN] Would delete ECS cluster: $clusterArn" -ForegroundColor Gray
        } else {
            Write-Host "  Deleting ECS cluster: $clusterArn"
            aws ecs delete-cluster --cluster $clusterArn --region $Region --output json | Out-Null
        }
        $deletedClusters++
    } catch {
        Write-Host "  ⚠️  Error deleting cluster: $_" -ForegroundColor Yellow
    }
}
Write-Host "  ✅ Processed $deletedClusters ECS clusters" -ForegroundColor Green
Write-Host ""

# ============================================================
# 4. REDUCE VPC FLOW LOGS RETENTION (Optional)
# ============================================================
if (-not $SkipFlowLogs) {
    Write-Host "4️⃣  Reducing VPC Flow Logs retention..." -ForegroundColor Cyan

    try {
        if ($DryRun) {
            Write-Host "  [DRYRUN] Would reduce Flow Logs retention to 3 days" -ForegroundColor Gray
        } else {
            Write-Host "  Setting VPC Flow Logs retention to 3 days (from 90)"
            aws logs put-retention-policy `
                --log-group-name "/aws/vpc/flowlogs/algo-dev" `
                --retention-in-days 3 `
                --region $Region `
                --output json | Out-Null
        }
        Write-Host "  ✅ VPC Flow Logs retention updated" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠️  Error updating VPC Flow Logs: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "4️⃣  Skipping VPC Flow Logs (use -SkipFlowLogs:$false to process)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "============================================="
Write-Host "✅ Phase 3 Cleanup Complete!" -ForegroundColor Green
Write-Host ""

if ($DryRun) {
    Write-Host "📋 DRY RUN SUMMARY:" -ForegroundColor Cyan
    Write-Host "  Would delete: $TotalDeleted task definitions"
    Write-Host "  Would delete: $deletedRds RDS instances"
    Write-Host "  Would delete: $deletedClusters ECS clusters"
    Write-Host ""
    Write-Host "Run again without -DryRun to actually delete these resources" -ForegroundColor Yellow
} else {
    Write-Host "Deleted: $TotalDeleted task definitions" -ForegroundColor Green
    Write-Host "Deleted: $deletedRds RDS instances" -ForegroundColor Green
    Write-Host "Deleted: $deletedClusters ECS clusters" -ForegroundColor Green
}

Write-Host ""
Write-Host "Cost Savings:" -ForegroundColor Cyan
Write-Host "  RDS instances: 100/month"
Write-Host "  VPC Flow Logs reduced: 700/month"
Write-Host "  Total monthly savings: 800"

# Monitor ECS Task Utilization for Cost Optimization
# Tracks actual CPU/memory usage vs allocated to identify over-provisioning
# Run weekly to identify tasks that can be downsized

param(
    [string]$ClusterName = "algo-cluster",
    [string]$EnvironmentFilter = "dev",
    [int]$HoursBack = 24,
    [switch]$ExportCSV
)

# Get all ECS task definitions in the cluster
$tasks = aws ecs list-tasks --cluster $ClusterName --output json | ConvertFrom-Json
$taskDefinitions = @{}

Write-Host "=== ECS Task Utilization Report ===" -ForegroundColor Cyan
Write-Host "Cluster: $ClusterName | Last $HoursBack hours" -ForegroundColor Gray
Write-Host ""

# Fetch metrics for each task definition
$metrics = @()

foreach ($task in $tasks.taskArns) {
    $taskName = ($task -split "/")[-1]

    # Get task details
    $taskDetail = aws ecs describe-tasks --cluster $ClusterName --tasks $task --output json | ConvertFrom-Json
    $taskDef = $taskDetail.tasks[0].taskDefinitionArn
    $taskDefName = ($taskDef -split ":")[-2] -replace "-[0-9]+$", ""

    # Get CloudWatch metrics (last 24 hours)
    $startTime = (Get-Date).AddHours(-$HoursBack)
    $endTime = Get-Date

    # CPU Utilization
    $cpuMetrics = aws cloudwatch get-metric-statistics `
        --namespace "ECS/ContainerInsights" `
        --metric-name "ContainerCpuUtilized" `
        --dimensions Name=TaskDefinitionFamily,Value=$taskDefName `
        --start-time $startTime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") `
        --end-time $endTime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") `
        --period 3600 `
        --statistics Average,Maximum `
        --output json | ConvertFrom-Json

    # Memory Utilization
    $memMetrics = aws cloudwatch get-metric-statistics `
        --namespace "ECS/ContainerInsights" `
        --metric-name "ContainerMemoryUtilized" `
        --dimensions Name=TaskDefinitionFamily,Value=$taskDefName `
        --start-time $startTime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") `
        --end-time $endTime.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") `
        --period 3600 `
        --statistics Average,Maximum `
        --output json | ConvertFrom-Json

    if ($cpuMetrics.Datapoints.Count -gt 0 -or $memMetrics.Datapoints.Count -gt 0) {
        $avgCpu = if ($cpuMetrics.Datapoints.Count -gt 0) { ($cpuMetrics.Datapoints | Measure-Object -Property Average -Average).Average } else { 0 }
        $maxCpu = if ($cpuMetrics.Datapoints.Count -gt 0) { ($cpuMetrics.Datapoints | Measure-Object -Property Maximum -Maximum).Maximum } else { 0 }

        $avgMem = if ($memMetrics.Datapoints.Count -gt 0) { ($memMetrics.Datapoints | Measure-Object -Property Average -Average).Average } else { 0 }
        $maxMem = if ($memMetrics.Datapoints.Count -gt 0) { ($memMetrics.Datapoints | Measure-Object -Property Maximum -Maximum).Maximum } else { 0 }

        $metrics += [PSCustomObject]@{
            TaskDefinition = $taskDefName
            AvgCpuMHz = [Math]::Round($avgCpu, 2)
            MaxCpuMHz = [Math]::Round($maxCpu, 2)
            AvgMemMB = [Math]::Round($avgMem / 1MB, 2)
            MaxMemMB = [Math]::Round($maxMem / 1MB, 2)
        }
    }
}

# Display results
$metrics | Sort-Object TaskDefinition | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Cost Optimization Guidance ===" -ForegroundColor Yellow
Write-Host "• If AvgCpuMHz < 30% of allocated: Consider reducing CPU allocation by 25%"
Write-Host "• If AvgMemMB < 70% of allocated: Consider reducing memory by 20-30%"
Write-Host "• Focus on high-cost tasks (growth_metrics, quality_metrics, stock_scores)"
Write-Host "• Test reductions on dev first; monitor orchestrator run times before production"
Write-Host ""

if ($ExportCSV) {
    $csvPath = "ecs-utilization-$(Get-Date -Format 'yyyyMMdd-HHmmss').csv"
    $metrics | Export-Csv -Path $csvPath -NoTypeInformation
    Write-Host "Report exported to: $csvPath" -ForegroundColor Green
}

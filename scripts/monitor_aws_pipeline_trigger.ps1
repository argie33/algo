#!/usr/bin/env pwsh
# Monitor the AWS pipeline execution and verify data arrival in RDS

$ExecutionArn = "arn:aws:states:us-east-1:626216981288:execution:algo-computed-metrics-pipeline-dev:manual-trigger-1782997142"
$Region = "us-east-1"
$CheckInterval = 30 # seconds

function Get-ExecutionStatus {
    $status = aws stepfunctions describe-execution `
        --execution-arn $ExecutionArn `
        --region $Region `
        --query '{status: status, startDate: startDate, stopDate: stopDate}' `
        --output json | ConvertFrom-Json
    return $status
}

function Get-ElapsedTime {
    param($startDate, $stopDate)

    if ($null -eq $stopDate) {
        $elapsed = (Get-Date).ToUniversalTime() - $startDate
    } else {
        $elapsed = $stopDate - $startDate
    }

    return $elapsed
}

function Test-AwsData {
    try {
        $result = python3 << 'PYTHON_EOF'
import psycopg2
import json

try:
    conn = psycopg2.connect(
        host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
        port=5432,
        database="algo_prod",
        user="algo_admin",
        password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe",
        sslmode="require"
    )

    cur = conn.cursor()

    # Check metric tables
    cur.execute("""
        SELECT
            'quality_metrics' as table_name,
            COUNT(*) as total,
            COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as with_score
        FROM quality_metrics
        UNION ALL
        SELECT
            'growth_metrics',
            COUNT(*),
            COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END)
        FROM growth_metrics
        UNION ALL
        SELECT
            'value_metrics',
            COUNT(*),
            COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END)
        FROM value_metrics
        UNION ALL
        SELECT
            'stock_scores',
            COUNT(*),
            COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END)
        FROM stock_scores
    """)

    result = {}
    for row in cur.fetchall():
        table, total, with_score = row
        result[table] = {"total": total, "with_score": with_score}

    cur.close()
    conn.close()

    print(json.dumps(result))

except Exception as e:
    print(json.dumps({"error": str(e)}))
PYTHON_EOF
        return $result | ConvertFrom-Json
    } catch {
        return $null
    }
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "AWS PIPELINE EXECUTION MONITOR" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Execution: $ExecutionArn" -ForegroundColor Gray
Write-Host ""

$startTime = Get-Date
$lastStatus = $null

while ($true) {
    $status = Get-ExecutionStatus
    $elapsed = Get-ElapsedTime $startTime

    # Display status
    if ($status.status -ne $lastStatus.status) {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Status: $($status.status)" -ForegroundColor $(
            switch ($status.status) {
                "RUNNING" { "Yellow" }
                "SUCCEEDED" { "Green" }
                "FAILED" { "Red" }
                "TIMED_OUT" { "Red" }
                default { "Gray" }
            }
        )
    }

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Elapsed: $($elapsed.TotalMinutes.ToString('F1')) minutes" -NoNewline

    # Check AWS data
    $data = Test-AwsData
    if ($null -ne $data -and $null -eq $data.error) {
        $qualityTotal = $data.quality_metrics.total
        $qualityScore = $data.quality_metrics.with_score
        Write-Host " | Quality Metrics: $qualityScore / $qualityTotal rows" -ForegroundColor Gray
    } else {
        Write-Host " | AWS: Not yet available" -ForegroundColor Gray
    }

    # Check if complete
    if ($status.status -in @("SUCCEEDED", "FAILED", "TIMED_OUT")) {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Pipeline Complete: $($status.status)" -ForegroundColor $(
            switch ($status.status) {
                "SUCCEEDED" { "Green" }
                default { "Red" }
            }
        )

        # Final verification
        if ($status.status -eq "SUCCEEDED") {
            Write-Host ""
            Write-Host "Running final data verification..." -ForegroundColor Cyan
            $finalData = Test-AwsData
            if ($null -ne $finalData -and $null -eq $finalData.error) {
                Write-Host ""
                Write-Host "✓ AWS Data Summary:" -ForegroundColor Green
                foreach ($table in @("quality_metrics", "growth_metrics", "value_metrics", "stock_scores")) {
                    $t = $finalData.$table
                    if ($null -ne $t) {
                        $pct = if ($t.total -gt 0) { [math]::Round(($t.with_score / $t.total) * 100, 1) } else { 0 }
                        Write-Host "  $table`: $($t.with_score) / $($t.total) ($pct%)" -ForegroundColor Green
                    }
                }
            }
        }
        break
    }

    $lastStatus = $status
    Start-Sleep -Seconds $CheckInterval
}

Write-Host ""
Write-Host "Monitor complete" -ForegroundColor Cyan
Write-Host ""

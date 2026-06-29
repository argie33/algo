#!/usr/bin/env pwsh
<#
.SYNOPSIS
Monitor daily data refresh cycle and trigger next phase when upstream completes.

.DESCRIPTION
Waits for value_metrics loader to complete, then triggers stock_scores rebuild
with live metric data. Designed to run as a background monitoring job.

.EXAMPLE
./scripts/monitor-daily-refresh.ps1

.NOTES
This script monitors the value_metrics background task and triggers stock_scores
when complete. Use in conjunction with CI/CD orchestration or as manual monitoring.
#>

param(
    [int]$CheckIntervalSeconds = 60,
    [int]$TimeoutSeconds = 14400  # 4 hour timeout
)

$startTime = Get-Date
$taskOutputPath = "C:\Users\arger\AppData\Local\Temp\claude\C--Users-arger-code-algo\25fa9595-be40-419b-852f-f7ea5e440c33\tasks\bgeowzuc4.output"

Write-Host "Starting daily refresh monitor"
Write-Host "- Watching: value_metrics (parallelism=1)"
Write-Host "- Check interval: $CheckIntervalSeconds seconds"
Write-Host "- Timeout: $TimeoutSeconds seconds (4 hours)"
Write-Host ""

while ($true) {
    $elapsed = (Get-Date) - $startTime

    if ($elapsed.TotalSeconds -gt $TimeoutSeconds) {
        Write-Host "ERROR: Timeout after $TimeoutSeconds seconds"
        exit 1
    }

    # Check if output file exists and has meaningful content
    if (Test-Path $taskOutputPath) {
        $content = Get-Content $taskOutputPath -ErrorAction SilentlyContinue
        if ($content) {
            $lineCount = @($content).Count
            $lastLine = $content[-1]

            # Check for completion indicators
            if ($lastLine -match "(success|COMPLETED|RuntimeError|FAILED)" -and $lineCount -gt 50) {
                Write-Host ""
                Write-Host "=========================================="
                Write-Host "value_metrics loader completed!"
                Write-Host "=========================================="
                Write-Host ""
                Write-Host "Last 10 lines of output:"
                $content | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" }

                if ($lastLine -match "RuntimeError|FAILED") {
                    Write-Host ""
                    Write-Host "ERROR: value_metrics failed. Check output above."
                    exit 1
                }

                Write-Host ""
                Write-Host "Triggering stock_scores rebuild with live metrics..."
                Write-Host ""

                # Trigger stock_scores with live metrics
                cd C:\Users\arger\code\algo
                python3 loaders/load_stock_scores.py --parallelism 1

                Write-Host ""
                Write-Host "Daily refresh cycle complete!"
                exit 0
            }

            # Progress indicator
            if ($lineCount % 10 -eq 0) {
                $pct = [math]::Min(100, [int]($lineCount / 100 * 100))
                Write-Host "[$pct%] ${elapsed.TotalSeconds.ToString('F0')}s elapsed - $lineCount lines in output"
            }
        }
    }

    # Check every N seconds
    Start-Sleep -Seconds $CheckIntervalSeconds
}

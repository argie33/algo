Set-Location "C:\Users\arger\code\algo"
$logPath = "logs\recovery_chain_20260817.log"
$lockPath = "$env:TEMP\algo-scheduler.lock"
$metricsPid = 27236

function Wait-ForLockFree {
    while (Test-Path $lockPath) {
        Start-Sleep -Seconds 30
    }
}

function Run-PipelineWithRetry {
    param([string]$PipelineName)
    # The lock can free momentarily between one scheduler invocation exiting and the next
    # one (re)acquiring it - a bare single attempt right after Test-Path can lose that race
    # and exit 1 immediately, silently skipping this pipeline. Retry instead of treating one
    # lost race as "done". Single sequential chain (not multiple competing watcher scripts)
    # so there's no race between pipelines either - see 2026-08-17 cleanup notes below.
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        Wait-ForLockFree
        "[WATCHER] attempt ${attempt}: running $PipelineName pipeline at $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $logPath
        python scripts/local_loader_scheduler.py --now $PipelineName *>> $logPath
        $code = $LASTEXITCODE
        "[WATCHER] $PipelineName pipeline attempt $attempt exited $code at $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $logPath
        if ($code -eq 0) { return $true }
        Start-Sleep -Seconds 15
    }
    "[WATCHER] $PipelineName pipeline still failing after 5 attempts - giving up, check the log above for the real error" | Out-File -Append -Encoding utf8 $logPath
    return $false
}

"[WATCHER] started $(Get-Date -Format o), waiting on metrics pipeline pid $metricsPid" | Out-File -Append -Encoding utf8 $logPath
Wait-Process -Id $metricsPid -ErrorAction SilentlyContinue
"[WATCHER] metrics pipeline (pid $metricsPid) exited at $(Get-Date -Format o), starting recovery chain: signals -> reference -> morning" | Out-File -Append -Encoding utf8 $logPath

# Replaces two separately-launched watcher scripts (_wait_and_run_signals.ps1 and
# _wait_and_run_reference_then_morning.ps1) that were both live and both waiting on this same
# lock at once: signals had no retry-on-lock-loss, reference did, so whichever won the race
# left the other to fail silently with zero retry - reproducing the exact "signals sat FAILED
# for hours with nothing retrying it" bug from earlier today, just one pipeline later. One
# sequential chain has no race to lose.
Run-PipelineWithRetry -PipelineName "signals" | Out-Null
Run-PipelineWithRetry -PipelineName "reference" | Out-Null
Run-PipelineWithRetry -PipelineName "morning" | Out-Null

"[WATCHER] recovery chain complete at $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 $logPath

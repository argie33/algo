# Setup Windows Task Scheduler for algo loaders (MON-FRI)
# Mimics AWS EventBridge schedule: 2 AM ET (morning) + 4:05 PM ET (signals/EOD) + 7 PM ET (metrics)

$algoPath = "C:\Users\arger\code\algo"
$taskFolder = "\algo"

Write-Host "Setting up Windows Task Scheduler for algo data loaders..."
Write-Host "================================"

# BUG FIX (2026-07-21): New-ScheduledTaskTrigger -At fires at the machine's LOCAL wall-clock
# time - there is no timezone parameter. This script previously hardcoded "02:00"/"16:05"/
# "19:00" directly as -At values as if they were already local, but those are the *Eastern*
# times from the header comment above. Confirmed live on this dev machine (Windows timezone:
# Central Standard Time, `Get-TimeZone`): morning-pipeline's registered NextRunTime was
# 2:00 AM Central = 3:00 AM ET, a full hour later than the intended 2 AM ET - and every
# other trigger below was off by the same hour. Compute each trigger's correct LOCAL time
# from the intended ET wall-clock time instead of hardcoding one machine's offset, so this
# stays correct on any dev machine's timezone (and across DST, since both zones move
# together for any US timezone).
$easternTz = [System.TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
function Convert-EasternTimeToLocal {
    param([int]$Hour, [int]$Minute)
    $easternWallClock = [DateTime]::SpecifyKind([DateTime]::Today.AddHours($Hour).AddMinutes($Minute), [DateTimeKind]::Unspecified)
    $utc = [System.TimeZoneInfo]::ConvertTimeToUtc($easternWallClock, $easternTz)
    return $utc.ToLocalTime().ToString("HH:mm")
}
$morningLocalTime = Convert-EasternTimeToLocal -Hour 2 -Minute 0
$signalsLocalTime = Convert-EasternTimeToLocal -Hour 16 -Minute 5
$metricsLocalTime = Convert-EasternTimeToLocal -Hour 19 -Minute 0
Write-Host "[INFO] Local machine timezone: $((Get-TimeZone).Id)"
Write-Host "[INFO] ET 02:00 -> local $morningLocalTime | ET 16:05 -> local $signalsLocalTime | ET 19:00 -> local $metricsLocalTime"

# Resolve a fully-qualified python.exe path. Task Scheduler's execution context does
# NOT inherit the interactive user's PATH, so a bare "python" action fails immediately
# with ERROR_FILE_NOT_FOUND (0x80070002) - this silently broke the daily 2 AM/4:05 PM
# auto-refresh (confirmed via Get-ScheduledTaskInfo: LastTaskResult=2147942402), which is
# why price_daily/technical_data_daily/buy_sell_daily went stale for days at a time.
try {
    $pythonCmd = Get-Command python -ErrorAction Stop
    $pythonExe = $pythonCmd.Source
    Write-Host "[OK] Python found: $pythonExe"
} catch {
    Write-Host "[FAIL] Python not found. Ensure python.exe is in PATH."
    exit 1
}

# NOTE: Task folders are created implicitly by Register-ScheduledTask -TaskPath if they
# don't exist - Get-ScheduledTaskFolder is not a real ScheduledTasks cmdlet (it never
# existed; the previous version of this script always threw here, silently, on every run).
#
# NOTE: Registration deliberately omits -RunLevel Highest - it requires the *registering*
# process to already be elevated (Access Denied otherwise), and the task itself doesn't
# need admin rights (just local Postgres + localhost API calls). Default run level
# (Limited) works fine for a non-elevated dev shell.

# Task 1: Morning loader pipeline (2:00 AM ET, MON-FRI)
Write-Host ""
Write-Host "Task 1: Morning Pipeline (2:00 AM ET, MON-FRI)"
Write-Host "  - Loads prices, technical indicators, market status"

# BUG FIX: this previously called run_local_orchestrator.py, which is the *trading*
# orchestrator (Phases 1-9: signal generation, risk gates, reconciliation) - it consumes
# whatever data is already in the DB, it does not fetch fresh prices/technicals itself.
# Confirmed live: running it did NOT move price_daily/technical_data_daily off their stale
# date. scripts/local_loader_scheduler.py --now morning is the actual data-refresh
# pipeline (load_prices.py, load_technical_indicators.py, etc - see its own docstring).
$morningAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/local_loader_scheduler.py --now morning" `
    -WorkingDirectory $algoPath

# BUG FIX: -Daily and -DaysOfWeek are mutually exclusive parameter sets in
# New-ScheduledTaskTrigger ("Parameter set cannot be resolved"). A per-weekday schedule
# needs -Weekly -DaysOfWeek, not -Daily -DaysOfWeek. The previous version's trigger
# construction always threw, so $morningTrigger was never assigned and every
# Register-ScheduledTask call below failed with "argument is null or empty" - silently,
# since the failure wasn't checked before printing "[OK] ... scheduled".
$morningTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At $morningLocalTime `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

$morningSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskPath "$taskFolder\" -TaskName "morning-pipeline" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskPath "$taskFolder\" -TaskName "morning-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing morning task"
} else {
    Write-Host "[INFO] No existing morning task found"
}

Register-ScheduledTask `
    -TaskName "morning-pipeline" `
    -TaskPath $taskFolder `
    -Action $morningAction `
    -Trigger $morningTrigger `
    -Settings $morningSettings `
    -Description "Load stock prices, technical indicators, market status (morning pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Morning task scheduled for 2:00 AM ET (MON-FRI)"

# Task 2: Signals/EOD loader pipeline (4:05 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 2: Signals Pipeline (4:05 PM ET, MON-FRI)"
Write-Host "  - Re-fetches closing prices/technicals, then recomputes stock scores, trading signals, risk metrics"

# BUG FIX: same issue as Task 1 - run_local_orchestrator.py --afternoon runs the trading
# orchestrator's afternoon phase set against whatever's already in the DB, it doesn't
# refresh prices/technicals/stock_scores/buy_sell_daily itself.
# local_loader_scheduler.py's "signals" pipeline is the actual EOD data-refresh job (see its
# own LOADERS["signals"] definition - closing prices through sector_industry_daily). Until
# 2026-07-21 this task called "--now metrics", which bundled the fast price-driven signal
# loaders together with slow SEC/EDGAR fundamentals fetches; "metrics" now covers ONLY the
# slow fundamentals (Task 3 below) and never re-fetches closing prices at all, so pointing
# this task at it would have silently stopped refreshing buy_sell_daily/stock_scores entirely.
$signalsAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/local_loader_scheduler.py --now signals" `
    -WorkingDirectory $algoPath

$signalsTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At $signalsLocalTime `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

$signalsSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskPath "$taskFolder\" -TaskName "afternoon-pipeline" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskPath "$taskFolder\" -TaskName "afternoon-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing afternoon task"
} else {
    Write-Host "[INFO] No existing afternoon task found"
}

Register-ScheduledTask `
    -TaskName "afternoon-pipeline" `
    -TaskPath $taskFolder `
    -Action $signalsAction `
    -Trigger $signalsTrigger `
    -Settings $signalsSettings `
    -Description "Re-fetch closing prices/technicals, recompute stock scores and trading signals (signals/EOD pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Signals task scheduled for 4:05 PM ET (MON-FRI)"

# Task 3: Metrics/fundamentals loader pipeline (7:00 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 3: Metrics Pipeline (7:00 PM ET, MON-FRI)"
Write-Host "  - Refreshes slow SEC/EDGAR fundamentals: financial statements, 13F, insider, positioning, value/quality/growth"

# ADDED 2026-07-21: previously there was no scheduled task for the slow SEC/EDGAR fundamentals
# refresh at all - only start_dashboard_dev.py's manual, completeness-gated invocation covered
# it. A pure Task-Scheduler-only setup (no one ever running start_dashboard_dev.py) would never
# refresh financial statements/13F/insider/positioning/value-quality-growth data.
$metricsAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/local_loader_scheduler.py --now metrics" `
    -WorkingDirectory $algoPath

$metricsTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At $metricsLocalTime `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

$metricsSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew

if (Get-ScheduledTask -TaskPath "$taskFolder\" -TaskName "evening-pipeline" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskPath "$taskFolder\" -TaskName "evening-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing evening task"
} else {
    Write-Host "[INFO] No existing evening task found"
}

Register-ScheduledTask `
    -TaskName "evening-pipeline" `
    -TaskPath $taskFolder `
    -Action $metricsAction `
    -Trigger $metricsTrigger `
    -Settings $metricsSettings `
    -Description "Refresh SEC/EDGAR fundamentals: financial statements, 13F, insider, positioning, value/quality/growth (metrics pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Metrics task scheduled for 7:00 PM ET (MON-FRI)"

# List created tasks
Write-Host ""
Write-Host "================================"
Write-Host "Scheduled Tasks Created:"
Get-ScheduledTask -TaskPath "$taskFolder\" | Select-Object -Property TaskName, @{Name="Schedule";Expression={$_.Triggers[0].StartBoundary}} | Format-Table

Write-Host ""
Write-Host "[SUCCESS] Task Scheduler setup complete!"
Write-Host "The loaders will run automatically on MON-FRI at 2:00 AM, 4:05 PM, and 7:00 PM ET"
Write-Host ""
Write-Host "To view/manage tasks, open Task Scheduler (Win+R > taskschd.msc)"
Write-Host "Tasks are under: Task Scheduler Library > algo"

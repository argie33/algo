# Setup Windows Task Scheduler for algo loaders (MON-FRI)
# Mimics AWS EventBridge schedule: 2 AM ET (morning) + 4:05 PM ET (afternoon)

$algoPath = "C:\Users\arger\code\algo"
$taskFolder = "\algo"

Write-Host "Setting up Windows Task Scheduler for algo data loaders..."
Write-Host "================================"

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
    -At "02:00" `
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

# Task 2: Afternoon/EOD loader pipeline (4:05 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 2: Afternoon Pipeline (4:05 PM ET, MON-FRI)"
Write-Host "  - Loads quality/growth/value scores, signals, risk metrics"

# BUG FIX: same issue as Task 1 - run_local_orchestrator.py --afternoon runs the trading
# orchestrator's afternoon phase set against whatever's already in the DB, it doesn't
# refresh financial statements/positioning/quality/growth/value/stock_scores itself.
# local_loader_scheduler.py's "metrics" pipeline is the actual EOD data-refresh job
# (see its own LOADERS["metrics"] definition - financial statements through buy_sell_daily).
$afternoonAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/local_loader_scheduler.py --now metrics" `
    -WorkingDirectory $algoPath

$afternoonTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At "16:05" `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

$afternoonSettings = New-ScheduledTaskSettingsSet `
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
    -Action $afternoonAction `
    -Trigger $afternoonTrigger `
    -Settings $afternoonSettings `
    -Description "Load quality/growth/value scores, trading signals, risk metrics (afternoon pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Afternoon task scheduled for 4:05 PM ET (MON-FRI)"

# List created tasks
Write-Host ""
Write-Host "================================"
Write-Host "Scheduled Tasks Created:"
Get-ScheduledTask -TaskPath "$taskFolder\" | Select-Object -Property TaskName, @{Name="Schedule";Expression={$_.Triggers[0].StartBoundary}} | Format-Table

Write-Host ""
Write-Host "[SUCCESS] Task Scheduler setup complete!"
Write-Host "The loaders will run automatically on MON-FRI at 2:00 AM and 4:05 PM ET"
Write-Host ""
Write-Host "To view/manage tasks, open Task Scheduler (Win+R > taskschd.msc)"
Write-Host "Tasks are under: Task Scheduler Library > algo"

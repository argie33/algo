# Setup Windows Task Scheduler for algo loaders (MON-FRI)
# Mimics AWS EventBridge schedule: 2 AM ET (morning) + 4:05 PM ET (signals/EOD) + 7 PM ET (metrics)
#   + 11:30 PM ET (reference) - see Task 4 below, added 2026-08-17.

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
$referenceLocalTime = Convert-EasternTimeToLocal -Hour 23 -Minute 30
Write-Host "[INFO] Local machine timezone: $((Get-TimeZone).Id)"
Write-Host "[INFO] ET 02:00 -> local $morningLocalTime | ET 16:05 -> local $signalsLocalTime | ET 19:00 -> local $metricsLocalTime | ET 23:30 -> local $referenceLocalTime"

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

# BUG FIX (2026-08-17): Register-ScheduledTask below never specified -Principal, so Windows
# silently defaulted every task to LogonType=Interactive - which only runs while the
# registering user has an active, unlocked desktop session at trigger time. Live-confirmed:
# morning-pipeline fired dead-on-schedule at 2:00 AM today (Get-ScheduledTaskInfo
# LastRunTime) but scripts/local_loader_scheduler.py never even started - zero trace in
# logs/scheduler_invocations.log, which tees this process's own stdout from its very first
# line - meaning Task Scheduler failed to launch python.exe at all (no one is logged into an
# unlocked session at 2 AM). This is why the "automated" cadence never actually loaded data.
# S4U runs the task whether the user is logged on or not, without needing a stored password
# (requires the "Log on as a batch job" right, normally already granted to the registering
# account by Task Scheduler). -WakeToRun lets the 2 AM trigger wake a sleeping machine.
# NOTE: registering a task with an explicit -Principal requires an ELEVATED (Run as
# Administrator) PowerShell session - Access Denied otherwise. Run this script elevated.
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

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

# ADDED 2026-08-17: these tasks fail-fast (no built-in wait/block) if
# algo-scheduler.lock is held by another pipeline at trigger time - confirmed live this
# session (afternoon-pipeline/evening-pipeline's one real trigger both failed outright on lock
# contention with zero retry, requiring a human to notice hours later and hand-launch a watcher
# script). -RestartCount/-RestartInterval makes Task Scheduler itself retry a failed run a few
# times before giving up, covering the common case where the previous pipeline is still
# finishing a few minutes past this one's trigger time.
$morningSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 20)

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
    -Principal $taskPrincipal `
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
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 20)

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
    -Principal $taskPrincipal `
    -Description "Re-fetch closing prices/technicals, recompute stock scores and trading signals (signals/EOD pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Signals task scheduled for 4:05 PM ET (MON-FRI)"

# Task 3: Metrics/fundamentals loader pipeline (7:00 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 3: Metrics Pipeline (7:00 PM ET, MON-FRI)"
Write-Host "  - Refreshes slow SEC/EDGAR fundamentals: financial statements, 13F, insider, positioning, value/quality/growth"

# ADDED 2026-07-21: previously there was no scheduled task for the slow SEC/EDGAR fundamentals
# refresh at all - only a manual, completeness-gated `local_loader_scheduler.py --now metrics`
# invocation covered it. A pure Task-Scheduler-only setup (no one ever running that manually)
# would never refresh financial statements/13F/insider/positioning/value-quality-growth data.
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
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 20)

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
    -Principal $taskPrincipal `
    -Description "Refresh SEC/EDGAR fundamentals: financial statements, 13F, insider, positioning, value/quality/growth (metrics pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Metrics task scheduled for 7:00 PM ET (MON-FRI)"

# Task 4: Reference/slow-changing loader pipeline (11:30 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 4: Reference Pipeline (11:30 PM ET, MON-FRI)"
Write-Host "  - Refreshes company profile, institutional/insider holdings, SEC filings, short interest,"
Write-Host "    segment info/metrics, earnings calendar (SEC), index constituents, economic/sentiment data, dividends"

# ADDED 2026-08-17: PIPELINES["reference"] in local_loader_scheduler.py has 15 real loaders
# (company_info, profile, institutional, insider_holdings, insider_velocity, sec_reports,
# short_interest, segment_info, segment_metrics, earnings_sec, constituents, economic, naaim,
# aaii, dividends) but this script never registered a scheduled task for it at all - unlike
# morning/signals/metrics, "reference" had no automation to even be broken (LogonType or
# otherwise). Confirmed live: sec_segment_info, sec_segment_metrics, dividend_data,
# current_reports_8k, and stock_symbols - all "reference" pipeline outputs - were sitting
# FAILED for days with nothing ever queued to refresh them. Scheduled after "evening" (metrics,
# 7 PM ET) and well before "morning" (2 AM ET) so it doesn't compete with either for the
# scheduler lock on a normal day; -RestartCount below covers the case where metrics is still
# running late.
$referenceAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/local_loader_scheduler.py --now reference" `
    -WorkingDirectory $algoPath

$referenceTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -At $referenceLocalTime `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday

$referenceSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew `
    -WakeToRun `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 20)

if (Get-ScheduledTask -TaskPath "$taskFolder\" -TaskName "reference-pipeline" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskPath "$taskFolder\" -TaskName "reference-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing reference task"
} else {
    Write-Host "[INFO] No existing reference task found"
}

Register-ScheduledTask `
    -TaskName "reference-pipeline" `
    -TaskPath $taskFolder `
    -Action $referenceAction `
    -Trigger $referenceTrigger `
    -Settings $referenceSettings `
    -Principal $taskPrincipal `
    -Description "Refresh slow-changing reference data: company profile, institutional/insider holdings, SEC filings, short interest, segment info/metrics, earnings calendar, constituents, economic/sentiment, dividends (reference pipeline)" `
    -ErrorAction Stop | Out-Null

Write-Host "[OK] Reference task scheduled for 11:30 PM ET (MON-FRI)"

# BUG FIX (2026-08-17): the actual trading orchestrator's own scheduled tasks
# (AlgoTrading_Orchestrator_930AM/1PM/3PM, under \AlgoTrading\ - registered separately from
# this script, no repo script ever managed them) were live-confirmed to have the exact same
# LogonType=Interactive gap as the loader tasks above, PLUS -Daily triggers (fire 7 days/week;
# harmless today only because orchestrator.py's own market-hours guard no-ops on weekends, but
# still wrong). Re-registering them here too so one elevated run of this script fixes every
# algo-related scheduled task, not just the 3 data-loader ones.
#
# BUG FIX (2026-08-17, later same day): the "Times/actions preserved exactly from the existing
# tasks... local wall-clock, not ET-converted" note this comment used to have was itself the
# same off-by-a-DST-hour bug as the loader triggers above, just not yet fixed for these three.
# scripts/run_local_orchestrator.py's own docstring states production's real schedule in ET:
# "morning 9:30 AM ET, afternoon 1:00 PM ET, preclose 3:00 PM ET" - which is exactly what these
# task names (930AM/1PM/3PM) encode, so `At` below must be ET-converted like the loader triggers,
# not literal local time (was firing every session ~1h later in ET than the name promises).
# NOTE: this fixes clock math only. It does NOT address a separate, independently-noticed
# mapping question - the "_3PM" task invokes `--evening` (production's monitor-only, always
# dry_run=True session per lambda_function.py's MONITOR_ONLY_RUN_IDENTIFIERS) rather than
# `--preclose` (a live-order-submitting session, which is what runs at 3 PM ET in production) -
# left untouched here since it changes which sessions place real paper orders, not just when a
# task fires; needs a deliberate human call, not a mechanical timezone fix.
#
# FIXED 2026-08-17 (deliberate human call made, per the note above): production actually
# schedules 4 sessions (terraform/modules/services/2x-daily-orchestrator.tf) - morning
# 9:30 AM ET, afternoon 1:00 PM ET, preclose 3:00 PM ET, evening 5:30 PM ET. Per
# run_local_orchestrator.py's own docstring, morning/afternoon/preclose place real (paper)
# orders via LIVE_TRADING_RUN_IDENTIFIERS; only evening is monitor-only (dry_run=True,
# enforced in run_local_orchestrator.py regardless of ORCHESTRATOR_DRY_RUN). The old 3-task
# setup below ran --evening (monitor-only, no real orders) in the 3PM slot instead of
# --preclose - meaning the real 3PM preclose session (which places real paper orders) never
# ran locally at all, and evening ran 2.5 hours early under the wrong session's clock
# alignment. Now matches production exactly: 4 tasks, --preclose restored to its real 3PM
# slot, --evening moved to its own real 5:30 PM slot.
$orchestratorTaskFolder = "\AlgoTrading"
$orchestrator930Local = Convert-EasternTimeToLocal -Hour 9 -Minute 30
$orchestrator1pmLocal = Convert-EasternTimeToLocal -Hour 13 -Minute 0
$orchestrator3pmLocal = Convert-EasternTimeToLocal -Hour 15 -Minute 0
$orchestrator530pmLocal = Convert-EasternTimeToLocal -Hour 17 -Minute 30
Write-Host "[INFO] ET 09:30 -> local $orchestrator930Local | ET 13:00 -> local $orchestrator1pmLocal | ET 15:00 -> local $orchestrator3pmLocal | ET 17:30 -> local $orchestrator530pmLocal"
$orchestratorTasks = @(
    @{ Name = "AlgoTrading_Orchestrator_930AM"; At = $orchestrator930Local;   Args = "scripts/run_local_orchestrator.py";           Desc = "Trading orchestrator - morning phases (real orders)" },
    @{ Name = "AlgoTrading_Orchestrator_1PM";   At = $orchestrator1pmLocal;   Args = "scripts/run_local_orchestrator.py --afternoon"; Desc = "Trading orchestrator - afternoon phases (real orders)" },
    @{ Name = "AlgoTrading_Orchestrator_3PM";   At = $orchestrator3pmLocal;   Args = "scripts/run_local_orchestrator.py --preclose";  Desc = "Trading orchestrator - preclose phases (real orders)" },
    @{ Name = "AlgoTrading_Orchestrator_530PM"; At = $orchestrator530pmLocal; Args = "scripts/run_local_orchestrator.py --evening";   Desc = "Trading orchestrator - evening phases (monitor-only, dry_run)" }
)

Write-Host ""
Write-Host "Fixing trading orchestrator tasks (LogonType + MON-FRI only)..."

foreach ($t in $orchestratorTasks) {
    $action = New-ScheduledTaskAction -Execute $pythonExe -Argument $t.Args -WorkingDirectory $algoPath
    $trigger = New-ScheduledTaskTrigger -Weekly -At $t.At -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries:$false `
        -Compatibility Win8 `
        -MultipleInstances IgnoreNew `
        -WakeToRun

    if (Get-ScheduledTask -TaskPath "$orchestratorTaskFolder\" -TaskName $t.Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskPath "$orchestratorTaskFolder\" -TaskName $t.Name -Confirm:$false
        Write-Host "[OK] Replaced existing $($t.Name)"
    } else {
        Write-Host "[INFO] No existing $($t.Name) found"
    }

    Register-ScheduledTask `
        -TaskName $t.Name `
        -TaskPath $orchestratorTaskFolder `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $taskPrincipal `
        -Description $t.Desc `
        -ErrorAction Stop | Out-Null

    Write-Host "[OK] $($t.Name) scheduled for $($t.At) local, MON-FRI"
}

# List created tasks
Write-Host ""
Write-Host "================================"
Write-Host "Scheduled Tasks Created:"
Get-ScheduledTask -TaskPath "$taskFolder\" | Select-Object -Property TaskName, @{Name="Schedule";Expression={$_.Triggers[0].StartBoundary}} | Format-Table
Get-ScheduledTask -TaskPath "$orchestratorTaskFolder\" | Select-Object -Property TaskName, @{Name="Schedule";Expression={$_.Triggers[0].StartBoundary}} | Format-Table

Write-Host ""
Write-Host "[SUCCESS] Task Scheduler setup complete!"
Write-Host "The loaders will run automatically on MON-FRI at 2:00 AM, 4:05 PM, 7:00 PM, and 11:30 PM ET"
Write-Host "The trading orchestrator will run automatically on MON-FRI at 9:30 AM, 1:00 PM, 3:00 PM (all real orders), and 5:30 PM ET (monitor-only)"
Write-Host ""
Write-Host "To view/manage tasks, open Task Scheduler (Win+R > taskschd.msc)"
Write-Host "Tasks are under: Task Scheduler Library > algo, and Task Scheduler Library > AlgoTrading"

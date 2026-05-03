#Requires -Version 5.1
<#
.SYNOPSIS
    Install Windows Task Scheduler entries for the algo daily pipeline.

.DESCRIPTION
    Creates two scheduled tasks:
      AlgoEODPipeline   — runs run_eod_pipeline.cmd weekdays at 17:30 (5:30pm),
                          after market close (eastern time approx; adjust for
                          your local TZ if needed).
      AlgoPatrolMorning — runs run_patrol.cmd weekdays at 09:25.

    Logs go to %USERPROFILE%\algo_logs\.

    Run this script ONCE to install. Subsequent runs are idempotent — existing
    tasks are updated.

    To remove later:
        schtasks /delete /tn AlgoEODPipeline /f
        schtasks /delete /tn AlgoPatrolMorning /f
#>

param(
    [string]$AlgoDir = "C:\Users\arger\code\algo",
    [string]$EodTime = "17:30",
    [string]$PatrolTime = "09:25"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $AlgoDir)) {
    Write-Error "Algo dir not found: $AlgoDir"
    exit 1
}

$eodCmd = Join-Path $AlgoDir "run_eod_pipeline.cmd"
$patrolCmd = Join-Path $AlgoDir "run_patrol.cmd"

foreach ($p in @($eodCmd, $patrolCmd)) {
    if (-not (Test-Path $p)) {
        Write-Error "Wrapper script missing: $p"
        exit 1
    }
}

$LogDir = Join-Path $env:USERPROFILE "algo_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "Algo dir:  $AlgoDir"
Write-Host "Log dir:   $LogDir"
Write-Host ""

$daysOfWeek = "Monday","Tuesday","Wednesday","Thursday","Friday"

# --- TASK 1: EOD pipeline ---
$eodAction = New-ScheduledTaskAction -Execute $eodCmd -WorkingDirectory $AlgoDir
$eodTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $daysOfWeek -At $EodTime
$eodSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "AlgoEODPipeline" `
    -Description "End-of-day algo data refresh + orchestrator (weekdays $EodTime)" `
    -Action $eodAction -Trigger $eodTrigger -Settings $eodSettings `
    -RunLevel Limited -Force | Out-Null

Write-Host "[OK] AlgoEODPipeline scheduled (weekdays $EodTime)"

# --- TASK 2: Pre-market patrol ---
$patrolAction = New-ScheduledTaskAction -Execute $patrolCmd -WorkingDirectory $AlgoDir
$patrolTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $daysOfWeek -At $PatrolTime
$patrolSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "AlgoPatrolMorning" `
    -Description "Pre-market data patrol (weekdays $PatrolTime)" `
    -Action $patrolAction -Trigger $patrolTrigger -Settings $patrolSettings `
    -RunLevel Limited -Force | Out-Null

Write-Host "[OK] AlgoPatrolMorning scheduled (weekdays $PatrolTime)"

Write-Host ""
Get-ScheduledTask -TaskName "Algo*" | Select-Object TaskName, State |
    Format-Table -AutoSize

Write-Host "Logs land in: $LogDir"

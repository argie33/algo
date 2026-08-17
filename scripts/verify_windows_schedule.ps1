# Verify Windows Task Scheduler configuration for the algo loader/orchestrator tasks.
#
# Read-only - does not require an elevated (Run as Administrator) session, unlike
# setup_windows_schedule.ps1's Register-ScheduledTask/Set-ScheduledTask calls. Run this
# any time to catch configuration drift before it causes a silent missed run.
#
# ADDED 2026-08-17: live-reproduced same day - AlgoTrading_Orchestrator_930AM's LogonType
# was fixed to S4U earlier in the day, then found reverted to Interactive-only hours later
# (likely a concurrent session re-running an older/non-elevated copy of
# setup_windows_schedule.ps1, which silently no-ops on Access Denied rather than failing
# loud enough to notice). That drift meant the 9:30 AM ET trading orchestrator run never
# fires unless someone happens to be logged into an unlocked desktop at trigger time - with
# zero visible warning until someone checks `schtasks /query` by hand. Separately, 7 of the
# 8 tasks still had StopIfGoingOnBatteries=True, which killed the live 3PM preclose run
# mid-execution the same day (Kernel-Power log showed an AC/battery flip at the exact
# trigger+37min mark). Both classes of drift are silent - nothing surfaces them except
# comparing live task state against what setup_windows_schedule.ps1 intends. This script is
# that comparison, meant to be run periodically (or whenever "did today's run actually
# fire?" comes up) rather than trusting Task Scheduler's "Ready"/"Enabled" state, which says
# nothing about LogonType or battery behavior.
#
# Usage: powershell -File scripts\verify_windows_schedule.ps1

$expectedTasks = @(
    @{ Path = "\algo\"; Name = "morning-pipeline" }
    @{ Path = "\algo\"; Name = "afternoon-pipeline" }
    @{ Path = "\algo\"; Name = "evening-pipeline" }
    @{ Path = "\algo\"; Name = "reference-pipeline" }
    @{ Path = "\AlgoTrading\"; Name = "AlgoTrading_Orchestrator_930AM" }
    @{ Path = "\AlgoTrading\"; Name = "AlgoTrading_Orchestrator_1PM" }
    @{ Path = "\AlgoTrading\"; Name = "AlgoTrading_Orchestrator_3PM" }
    @{ Path = "\AlgoTrading\"; Name = "AlgoTrading_Orchestrator_530PM" }
)

$anyFailed = $false

Write-Host "Checking $($expectedTasks.Count) algo scheduled tasks against expected config..."
Write-Host "(expected: LogonType=S4U, DontStopIfGoingOnBatteries, Enabled)"
Write-Host "================================"

foreach ($t in $expectedTasks) {
    $task = Get-ScheduledTask -TaskPath $t.Path -TaskName $t.Name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "[MISSING] $($t.Path)$($t.Name) - task not registered at all"
        $anyFailed = $true
        continue
    }

    $issues = @()
    if ($task.Principal.LogonType -ne "S4U") {
        $issues += "LogonType=$($task.Principal.LogonType) (expected S4U - task only fires while someone is logged into an unlocked desktop)"
    }
    if ($task.Settings.StopIfGoingOnBatteries) {
        $issues += "StopIfGoingOnBatteries=True (a battery/AC power-source flip mid-run will TerminateProcess this task)"
    }
    if ($task.State -eq "Disabled") {
        $issues += "State=Disabled"
    }

    if ($issues.Count -eq 0) {
        Write-Host "[OK] $($t.Path)$($t.Name)"
    } else {
        $anyFailed = $true
        Write-Host "[DRIFT] $($t.Path)$($t.Name):"
        foreach ($issue in $issues) {
            Write-Host "    - $issue"
        }
    }
}

Write-Host "================================"
if ($anyFailed) {
    Write-Host "[FAIL] Drift detected. Fix with an ELEVATED (Run as Administrator) PowerShell:"
    Write-Host "  cd $(Split-Path -Parent $PSScriptRoot)"
    Write-Host "  .\scripts\setup_windows_schedule.ps1"
    exit 1
} else {
    Write-Host "[OK] All tasks match expected configuration."
    exit 0
}

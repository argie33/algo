# Setup Windows Task Scheduler for algo loaders (MON-FRI)
# Mimics AWS EventBridge schedule: 2 AM ET (morning) + 4:05 PM ET (afternoon)

$algoPath = "C:\Users\arger\code\algo"
$pythonExe = "python"
$taskFolder = "\algo"

Write-Host "Setting up Windows Task Scheduler for algo data loaders..."
Write-Host "================================"

# Verify Python is available
try {
    $pythonVersion = & python --version 2>&1
    Write-Host "[OK] Python found: $pythonVersion"
} catch {
    Write-Host "[FAIL] Python not found. Ensure python.exe is in PATH."
    exit 1
}

# Create task folder if it doesn't exist
Write-Host "Creating task folder '$taskFolder'..."
try {
    $folder = Get-ScheduledTaskFolder -Path $taskFolder -ErrorAction Stop 2>$null
    Write-Host "[OK] Task folder already exists"
} catch {
    # Folder doesn't exist, create it
    $rootFolder = Get-ScheduledTaskFolder -Path "\" -ErrorAction Stop
    $newFolder = $rootFolder.CreateFolder($taskFolder.TrimStart("\"), $null)
    Write-Host "[OK] Task folder created: $newFolder.Path"
}

# Task 1: Morning orchestrator (2:00 AM ET, MON-FRI)
Write-Host ""
Write-Host "Task 1: Morning Pipeline (2:00 AM ET, MON-FRI)"
Write-Host "  - Loads prices, technical indicators, market status"

$morningTaskName = "algo\morning-pipeline"
$morningAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/run_local_orchestrator.py --morning" `
    -WorkingDirectory $algoPath

$morningTrigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "02:00 AM" `
    -DaysOfWeek "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"

$morningSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew

try {
    $existingTask = Get-ScheduledTask -TaskPath $taskFolder -TaskName "morning-pipeline" -ErrorAction Stop 2>$null
    Unregister-ScheduledTask -TaskPath $taskFolder -TaskName "morning-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing morning task"
} catch {
    Write-Host "[INFO] No existing morning task found"
}

Register-ScheduledTask `
    -TaskName "morning-pipeline" `
    -TaskPath $taskFolder `
    -Action $morningAction `
    -Trigger $morningTrigger `
    -Settings $morningSettings `
    -RunLevel Highest `
    -Description "Load stock prices, technical indicators, market status (morning pipeline)"

Write-Host "[OK] Morning task scheduled for 2:00 AM ET (MON-FRI)"

# Task 2: Afternoon orchestrator (4:05 PM ET, MON-FRI)
Write-Host ""
Write-Host "Task 2: Afternoon Pipeline (4:05 PM ET, MON-FRI)"
Write-Host "  - Loads quality/growth/value scores, signals, risk metrics"

$afternoonTaskName = "algo\afternoon-pipeline"
$afternoonAction = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "scripts/run_local_orchestrator.py --afternoon" `
    -WorkingDirectory $algoPath

$afternoonTrigger = New-ScheduledTaskTrigger `
    -Daily `
    -At "16:05" `
    -DaysOfWeek "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"

$afternoonSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries:$false `
    -Compatibility Win8 `
    -MultipleInstances IgnoreNew

try {
    $existingTask = Get-ScheduledTask -TaskPath $taskFolder -TaskName "afternoon-pipeline" -ErrorAction Stop 2>$null
    Unregister-ScheduledTask -TaskPath $taskFolder -TaskName "afternoon-pipeline" -Confirm:$false
    Write-Host "[OK] Replaced existing afternoon task"
} catch {
    Write-Host "[INFO] No existing afternoon task found"
}

Register-ScheduledTask `
    -TaskName "afternoon-pipeline" `
    -TaskPath $taskFolder `
    -Action $afternoonAction `
    -Trigger $afternoonTrigger `
    -Settings $afternoonSettings `
    -RunLevel Highest `
    -Description "Load quality/growth/value scores, trading signals, risk metrics (afternoon pipeline)"

Write-Host "[OK] Afternoon task scheduled for 4:05 PM ET (MON-FRI)"

# List created tasks
Write-Host ""
Write-Host "================================"
Write-Host "Scheduled Tasks Created:"
Get-ScheduledTask -TaskPath $taskFolder | Select-Object -Property TaskName, @{Name="Schedule";Expression={$_.Triggers[0].StartBoundary}} | Format-Table

Write-Host ""
Write-Host "[SUCCESS] Task Scheduler setup complete!"
Write-Host "The loaders will run automatically on MON-FRI at 2:00 AM and 4:05 PM ET"
Write-Host ""
Write-Host "To view/manage tasks, open Task Scheduler (Win+R > taskschd.msc)"
Write-Host "Tasks are under: Task Scheduler Library > algo"

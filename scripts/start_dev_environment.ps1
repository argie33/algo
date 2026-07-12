# Start local development environment with dev_server + dashboard
# Usage: .\scripts\start_dev_environment.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Starting Algo Dev Environment" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if dev_server is already running
$devServerRunning = $false
try {
    $response = curl.exe -s -H "Authorization: Bearer dev-admin" http://localhost:3001/api/sectors -ErrorAction SilentlyContinue
    if ($response) {
        Write-Host "[OK] Dev server already running on port 3001" -ForegroundColor Green
        $devServerRunning = $true
    }
}
catch {
    # Dev server not running, we'll start it
}

if (-not $devServerRunning) {
    Write-Host "[INFO] Starting dev_server on port 3001..." -ForegroundColor Yellow

    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "python3"
    $processInfo.Arguments = "api-pkg/dev_server.py"
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $false
    $processInfo.RedirectStandardError = $false
    $processInfo.CreateNoWindow = $false

    $process = [System.Diagnostics.Process]::Start($processInfo)
    $devServerPID = $process.Id
    Write-Host "[OK] Dev server started (PID: $devServerPID)" -ForegroundColor Green
    Start-Sleep -Seconds 3
}

# Wait for dev_server to be responsive
Write-Host "[INFO] Waiting for dev_server to respond..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$devServerReady = $false

while ($attempt -lt $maxAttempts) {
    try {
        $response = curl.exe -s -H "Authorization: Bearer dev-admin" http://localhost:3001/api/sectors -ErrorAction Stop
        if ($response) {
            Write-Host "[OK] Dev server is responsive" -ForegroundColor Green
            $devServerReady = $true
            break
        }
    }
    catch {
        # Server not ready yet
    }

    $attempt++
    if ($attempt -lt $maxAttempts) {
        Start-Sleep -Seconds 1
    }
}

if (-not $devServerReady) {
    Write-Host "[ERROR] Dev server did not respond after $maxAttempts seconds" -ForegroundColor Red
    exit 1
}

# Start dashboard
Write-Host ""
Write-Host "[INFO] Starting dashboard with --local flag..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor Cyan
Write-Host ""

python3 -m dashboard --local

# Note: Dev server cleanup is handled by OS when PowerShell exits
# since we didn't set $process.WaitForExit()

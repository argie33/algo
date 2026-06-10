# Start both API dev server and Vite dev server
Write-Host "[START] Launching development environment..."
Write-Host ""

# Start API server
Write-Host "[1/2] Starting API server on localhost:3001..."
$apiProc = Start-Process python -ArgumentList "lambda\api\dev_server.py" `
  -NoNewWindow -PassThru -WorkingDirectory "$PSScriptRoot"
Write-Host "  API Server PID: $($apiProc.Id)"

Start-Sleep -Seconds 3

# Start Vite dev server
Write-Host "[2/2] Starting Vite dev server on localhost:5173..."
Push-Location "$PSScriptRoot\webapp\frontend"
$viteProc = Start-Process npm -ArgumentList "run dev" `
  -NoNewWindow -PassThru -RedirectStandardOutput "$PSScriptRoot\vite-dev.log" `
  -RedirectStandardError "$PSScriptRoot\vite-dev-error.log"
Pop-Location
Write-Host "  Vite Server PID: $($viteProc.Id)"

Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[READY] Development environment started!"
Write-Host "  API:      http://localhost:3001"
Write-Host "  Frontend: http://localhost:5173"
Write-Host ""
Write-Host "Press Ctrl+C to stop..."
Write-Host ""

# Wait for servers
try {
    $apiProc.WaitForExit()
} catch {
    Write-Host "Stopping servers..."
    Get-Process python -ErrorAction SilentlyContinue | Where-Object {$_.Id -eq $apiProc.Id} | Stop-Process -Force
    Get-Process node -ErrorAction SilentlyContinue | Where-Object {$_.Id -eq $viteProc.Id} | Stop-Process -Force
}

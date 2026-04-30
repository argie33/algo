# PowerShell restart script for both servers

Write-Host "🔴 Stopping all Node processes..." -ForegroundColor Yellow
Get-Process node, npm -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "🟢 Starting API server on port 3001..." -ForegroundColor Cyan
Push-Location "C:\Users\arger\code\algo\webapp\lambda"
Start-Process -NoNewWindow -FilePath "node" -ArgumentList "index.js" -RedirectStandardOutput "C:\temp\api.log" -RedirectStandardError "C:\temp\api.log"
Start-Sleep -Seconds 3

Write-Host "🟢 Starting Frontend server on port 5173..." -ForegroundColor Cyan
Push-Location "C:\Users\arger\code\algo\webapp\frontend"
Remove-Item ".vite" -Recurse -Force -ErrorAction SilentlyContinue
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run dev" -RedirectStandardOutput "C:\temp\frontend.log" -RedirectStandardError "C:\temp\frontend.log"
Start-Sleep -Seconds 8

Write-Host ""
Write-Host "⏳ Checking servers..." -ForegroundColor Yellow
Write-Host ""

# Check API
try {
    $apiResponse = Invoke-WebRequest -Uri "http://localhost:3001/api/health" -ErrorAction Stop -UseBasicParsing
    if ($apiResponse.Content -match "healthy") {
        Write-Host "✅ API is running on http://localhost:3001" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ API failed to start - check C:\temp\api.log" -ForegroundColor Red
    Get-Content "C:\temp\api.log" | Select-Object -Last 20
    exit 1
}

# Check Frontend
try {
    $frontendResponse = Invoke-WebRequest -Uri "http://localhost:5173" -ErrorAction Stop -UseBasicParsing
    if ($frontendResponse.Content -match "root") {
        Write-Host "✅ Frontend is running on http://localhost:5173" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ Frontend failed to start - check C:\temp\frontend.log" -ForegroundColor Red
    Get-Content "C:\temp\frontend.log" | Select-Object -Last 20
    exit 1
}

Write-Host ""
Write-Host "🎉 Both servers are running!" -ForegroundColor Green
Write-Host ""
Write-Host "Access the app at: http://localhost:5173" -ForegroundColor Cyan

# Start the algo system in local or AWS mode
# Usage: .\start_system.ps1 -Mode local   # Development (localhost)
#        .\start_system.ps1 -Mode aws     # Production (AWS endpoints)

param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("local", "aws")]
    [string]$Mode = "local"
)

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Mode -eq "local") {
    Write-Host "Starting Algo System in LOCAL MODE" -ForegroundColor Green
    Write-Host "====================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Terminal 1 (API Server):" -ForegroundColor Cyan
    Write-Host "  cd `"$RepoRoot`""
    Write-Host "  python api-pkg/dev_server.py"
    Write-Host ""
    Write-Host "Terminal 2 (Dashboard):" -ForegroundColor Cyan
    Write-Host "  cd `"$RepoRoot`""
    Write-Host "  python -m dashboard --local"
    Write-Host ""
    Write-Host "Starting API server..." -ForegroundColor Yellow

    Set-Location "$RepoRoot/api-pkg"
    python dev_server.py
}
elseif ($Mode -eq "aws") {
    Write-Host "Starting Algo System in AWS MODE" -ForegroundColor Green
    Write-Host "==================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Requires AWS credentials and Cognito configuration." -ForegroundColor Yellow
    Write-Host "Environment variables needed:" -ForegroundColor Yellow
    Write-Host "  - DASHBOARD_API_URL: AWS Lambda API endpoint"
    Write-Host "  - COGNITO_USER_POOL_ID: Cognito User Pool ID"
    Write-Host "  - COGNITO_CLIENT_ID: Cognito Client ID"
    Write-Host ""
    Write-Host "Starting dashboard..." -ForegroundColor Yellow

    Set-Location $RepoRoot
    python -m dashboard
}
else {
    Write-Host "Usage: .\start_system.ps1 -Mode [local|aws]" -ForegroundColor Red
    Write-Host "  local - Development mode (recommended)" -ForegroundColor Yellow
    Write-Host "  aws   - Production mode (requires AWS credentials)" -ForegroundColor Yellow
    exit 1
}

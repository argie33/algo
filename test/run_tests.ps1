# PowerShell script to run Docker-based tests
param(
    [switch]$Clean = $false
)

Write-Host "🚀 Starting Docker-based test environment..." -ForegroundColor Green

# Change to the test directory
$testDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $testDir

try {
    if ($Clean) {
        Write-Host "🧹 Cleaning up any existing containers and volumes..." -ForegroundColor Yellow
        docker-compose down -v
    }

    Write-Host "📦 Building and running tests..." -ForegroundColor Cyan
    docker-compose up --build

    $exitCode = $LASTEXITCODE
    
    Write-Host "🧹 Cleaning up containers..." -ForegroundColor Yellow
    docker-compose down

    if ($exitCode -eq 0) {
        Write-Host "✅ Tests completed successfully!" -ForegroundColor Green
    } else {
        Write-Host "❌ Tests failed with exit code: $exitCode" -ForegroundColor Red
    }

    return $exitCode
}
catch {
    Write-Host "💥 Error running tests: $_" -ForegroundColor Red
    docker-compose down
    return 1
}
finally {
    Write-Host "📊 Check the logs/ directory for detailed output" -ForegroundColor Blue
}

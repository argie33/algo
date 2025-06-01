# Custom test script for running tests with modified port
Write-Host "🚀 Starting Docker-based test environment with modified port..."

# Change to the test directory
Set-Location -Path "c:\code\deploy\loadfundamentals\test"

try {
    # Clean up any existing containers
    Write-Host "🧹 Cleaning up existing containers..."
    docker-compose down -v

    # Build and run the Docker environment
    Write-Host "📦 Building and starting containers..."
    docker-compose up --build

    $success = $true
}
catch {
    Write-Host "❌ Test execution failed: $_"
    $success = $false
}
finally {
    # Clean up
    Write-Host "🧹 Cleaning up containers..."
    docker-compose down
}

if ($success) {
    Write-Host "✅ Tests completed successfully!"
    exit 0
} else {
    Write-Host "❌ Tests failed!"
    exit 1
}

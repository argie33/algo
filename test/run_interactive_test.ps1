# PowerShell script to run tests interactively
# Change to the test directory
Set-Location -Path $PSScriptRoot

# Build the containers
docker-compose build

# Run PostgreSQL in the background
docker-compose up -d postgres

# Wait a moment for PostgreSQL to start
Write-Host "Waiting for PostgreSQL to start..."
Start-Sleep -Seconds 5

# Run the test runner in interactive mode
docker-compose run --rm test-runner python -u /app/run_direct_test.py

# Clean up after
docker-compose down

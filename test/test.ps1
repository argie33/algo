# PowerShell script to run the ECS container test environment
# This provides easy commands for Windows users

param(
    [Parameter(Position=0)]
    [ValidateSet("start", "stop", "test", "full-test", "health", "logs", "db", "all", "help")]
    [string]$Action = "help"
)

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Yellow
    Write-Host "=" * 60 -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Blue
}

# Change to the test directory
$TestDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $TestDir
Write-Info "Working in directory: $TestDir"

switch ($Action) {
    "start" {
        Write-Header "Starting Docker Test Environment"
        docker-compose up -d --build
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Environment started successfully"
            Write-Info "Run './test.ps1 test' to run simple tests"
        } else {
            Write-Error "Failed to start environment"
            exit 1
        }
    }
    
    "stop" {
        Write-Header "Stopping Docker Test Environment"
        docker-compose down -v
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Environment stopped successfully"
        } else {
            Write-Error "Failed to stop environment"
            exit 1
        }
    }
    
    "test" {
        Write-Header "Running Simple Validation Test"
        docker-compose run --rm test-runner python simple_test.py
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Simple test completed successfully"
        } else {
            Write-Error "Simple test failed"
            exit 1
        }
    }
    
    "full-test" {
        Write-Header "Running Full Test Suite"
        docker-compose run --rm test-runner python run_direct_test.py
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Full test suite completed successfully"
        } else {
            Write-Error "Full test suite failed"
            exit 1
        }
    }
    
    "health" {
        Write-Header "Running Health Check"
        docker-compose run --rm test-runner python test_config.py
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Health check passed"
        } else {
            Write-Error "Health check failed"
            exit 1
        }
    }
    
    "logs" {
        Write-Header "Showing Container Logs"
        Write-Info "Press Ctrl+C to exit log viewing"
        docker-compose logs -f
    }
    
    "db" {
        Write-Header "Connecting to Test Database"
        Write-Info "Use \q to exit the database connection"
        docker-compose exec postgres psql -U testuser -d testdb
    }
    
    "all" {
        Write-Header "Running Complete Test Cycle"
        
        # Start environment
        Write-Info "Step 1: Starting environment..."
        docker-compose up -d --build
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to start environment"
            exit 1
        }
        
        # Wait for services
        Write-Info "Step 2: Waiting for services to be ready..."
        Start-Sleep -Seconds 10
        
        # Health check
        Write-Info "Step 3: Running health check..."
        docker-compose run --rm test-runner python test_config.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Health check failed"
            exit 1
        }
        
        # Simple test
        Write-Info "Step 4: Running simple test..."
        docker-compose run --rm test-runner python simple_test.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Simple test failed"
            exit 1
        }
        
        # Full tests
        Write-Info "Step 5: Running full test suite..."
        docker-compose run --rm test-runner python run_direct_test.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Full test suite failed"
            exit 1
        }
        
        Write-Success "🎉 All tests completed successfully!"
        Write-Info "Environment is still running. Use './test.ps1 stop' to shut it down."
    }
    
    "help" {
        Write-Header "ECS Container Test Environment"
        Write-Host ""
        Write-Host "Available commands:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  start      - Start the Docker test environment" -ForegroundColor White
        Write-Host "  stop       - Stop the Docker test environment" -ForegroundColor White
        Write-Host "  test       - Run simple validation test" -ForegroundColor White
        Write-Host "  full-test  - Run full test suite" -ForegroundColor White
        Write-Host "  health     - Run health check" -ForegroundColor White
        Write-Host "  logs       - Show container logs" -ForegroundColor White
        Write-Host "  db         - Connect to test database" -ForegroundColor White
        Write-Host "  all        - Run complete test cycle" -ForegroundColor White
        Write-Host "  help       - Show this help message" -ForegroundColor White
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\test.ps1 start" -ForegroundColor Gray
        Write-Host "  .\test.ps1 test" -ForegroundColor Gray
        Write-Host "  .\test.ps1 all" -ForegroundColor Gray
        Write-Host "  .\test.ps1 stop" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Quick start:" -ForegroundColor Yellow
        Write-Host "  .\test.ps1 all    # Runs everything" -ForegroundColor Gray
        Write-Host ""
    }
    
    default {
        Write-Error "Unknown action: $Action"
        Write-Info "Run './test.ps1 help' for available commands"
        exit 1
    }
}

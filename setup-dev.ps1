# Financial Data Web Application - Development Setup (PowerShell)
# This script helps set up and run the application locally on Windows

param(
    [Parameter(Position=0)]
    [ValidateSet("setup", "install", "env", "test", "build", "dev", "docker", "check", "help")]
    [string]$Action = "setup"
)

# Colors for output
$ErrorColor = "Red"
$SuccessColor = "Green"
$WarningColor = "Yellow"
$InfoColor = "Cyan"

function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor $InfoColor
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor $SuccessColor
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor $WarningColor
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor $ErrorColor
}

function Test-NodeJS {
    Write-Status "Checking Node.js installation..."
    
    try {
        $nodeVersion = node --version
        $versionNumber = [Version]($nodeVersion -replace 'v', '')
        
        if ($versionNumber.Major -lt 18) {
            Write-Error "Node.js version 18 or higher is required. Current version: $nodeVersion"
            exit 1
        }
        
        Write-Success "Node.js $nodeVersion is installed"
    }
    catch {
        Write-Error "Node.js is not installed. Please install Node.js 18 or higher."
        Write-Status "Download from: https://nodejs.org/"
        exit 1
    }
}

function Test-NPM {
    Write-Status "Checking npm installation..."
    
    try {
        $npmVersion = npm --version
        Write-Success "npm $npmVersion is installed"
    }
    catch {
        Write-Error "npm is not installed. Please install npm."
        exit 1
    }
}

function Install-Dependencies {
    Write-Status "Installing dependencies..."
    
    # Install backend dependencies
    Write-Status "Installing backend dependencies..."
    Set-Location "webapp\backend"
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install backend dependencies"
        exit 1
    }
    Set-Location "..\..\"
    
    # Install frontend dependencies
    Write-Status "Installing frontend dependencies..."
    Set-Location "webapp\frontend"
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install frontend dependencies"
        exit 1
    }
    Set-Location "..\..\"
    
    Write-Success "All dependencies installed successfully"
}

function Setup-Environment {
    Write-Status "Setting up environment files..."
    
    # Backend environment
    $backendEnvPath = "webapp\backend\.env"
    if (-not (Test-Path $backendEnvPath)) {
        Write-Status "Creating backend .env file..."
        
        $backendEnvContent = @"
NODE_ENV=development
PORT=3001
LOG_LEVEL=debug

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fundamentals
DB_USER=postgres
DB_PASSWORD=password

# AWS Configuration (for production)
AWS_REGION=us-east-1
AWS_SECRETS_MANAGER_SECRET_NAME=rds-db-credentials/cluster-fundamentals

# CORS Configuration
CORS_ORIGIN=http://localhost:5173
"@
        
        $backendEnvContent | Out-File -FilePath $backendEnvPath -Encoding UTF8
        Write-Success "Backend .env file created"
    }
    else {
        Write-Warning "Backend .env file already exists"
    }
    
    # Frontend environment
    $frontendEnvPath = "webapp\frontend\.env"
    if (-not (Test-Path $frontendEnvPath)) {
        Write-Status "Creating frontend .env file..."
        
        $frontendEnvContent = @"
VITE_API_URL=http://localhost:3001/api
VITE_APP_TITLE=Financial Data Platform
VITE_APP_DESCRIPTION=Professional financial data analysis platform
"@
        
        $frontendEnvContent | Out-File -FilePath $frontendEnvPath -Encoding UTF8
        Write-Success "Frontend .env file created"
    }
    else {
        Write-Warning "Frontend .env file already exists"
    }
}

function Test-Database {
    Write-Status "Checking database connection..."
    
    # Try to connect to PostgreSQL
    try {
        $pgReady = Get-Command pg_isready -ErrorAction SilentlyContinue
        if ($pgReady) {
            $result = pg_isready -h localhost -p 5432 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "PostgreSQL is running"
            }
            else {
                Write-Warning "PostgreSQL may not be running on localhost:5432"
                Write-Warning "Make sure your database is accessible and credentials are correct"
            }
        }
        else {
            Write-Warning "pg_isready not found. Cannot check PostgreSQL status"
            Write-Warning "Make sure PostgreSQL is installed and running"
        }
    }
    catch {
        Write-Warning "Unable to check PostgreSQL status"
        Write-Warning "Make sure PostgreSQL is installed and running"
    }
}

function Invoke-Tests {
    Write-Status "Running tests..."
    
    # Backend tests
    Write-Status "Running backend tests..."
    Set-Location "webapp\backend"
    npm test
    $backendTestResult = $LASTEXITCODE
    Set-Location "..\..\"
    
    if ($backendTestResult -eq 0) {
        Write-Success "Backend tests passed"
    }
    else {
        Write-Warning "Backend tests failed or not configured"
    }
    
    # Frontend tests
    Write-Status "Running frontend tests..."
    Set-Location "webapp\frontend"
    npm run test:run
    $frontendTestResult = $LASTEXITCODE
    Set-Location "..\..\"
    
    if ($frontendTestResult -eq 0) {
        Write-Success "Frontend tests passed"
    }
    else {
        Write-Warning "Frontend tests failed or not configured"
    }
}

function Build-Application {
    Write-Status "Building application..."
    
    # Build frontend
    Write-Status "Building frontend..."
    Set-Location "webapp\frontend"
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build failed"
        exit 1
    }
    Set-Location "..\..\"
    
    Write-Success "Application built successfully"
}

function Start-DevServers {
    Write-Status "Creating development startup script..."
    
    # Create PowerShell script to run both servers
    $startDevContent = @'
# Start development servers
Write-Host "Starting backend server..." -ForegroundColor Cyan
$backendJob = Start-Job -ScriptBlock {
    Set-Location "webapp\backend"
    npm run dev
}

Write-Host "Starting frontend server..." -ForegroundColor Cyan
$frontendJob = Start-Job -ScriptBlock {
    Set-Location "webapp\frontend"
    npm run dev
}

Write-Host ""
Write-Host "🚀 Development servers started!" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Yellow
Write-Host "Backend:  http://localhost:3001" -ForegroundColor Yellow
Write-Host "API Health: http://localhost:3001/api/health" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop all servers" -ForegroundColor White

# Function to cleanup
function Stop-Servers {
    Write-Host "Shutting down servers..." -ForegroundColor Yellow
    Stop-Job $backendJob, $frontendJob -Force
    Remove-Job $backendJob, $frontendJob -Force
}

# Set up trap for cleanup
$null = Register-EngineEvent PowerShell.Exiting -Action { Stop-Servers }

try {
    # Wait for jobs
    Wait-Job $backendJob, $frontendJob
}
finally {
    Stop-Servers
}
'@
    
    $startDevContent | Out-File -FilePath "start-dev.ps1" -Encoding UTF8
    
    Write-Success "Development startup script created: .\start-dev.ps1"
    Write-Status "Run '.\start-dev.ps1' to start both servers"
}

function Setup-Docker {
    Write-Status "Setting up Docker development environment..."
    
    # Create docker-compose for development
    $dockerComposeContent = @'
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: fundamentals
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./webapp/backend
      dockerfile: Dockerfile
    ports:
      - "3001:3001"
    environment:
      NODE_ENV: development
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: fundamentals
      DB_USER: postgres
      DB_PASSWORD: password
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./webapp/backend:/app
      - /app/node_modules

  frontend:
    build:
      context: ./webapp/frontend
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:3001/api
    volumes:
      - ./webapp/frontend:/app
      - /app/node_modules

volumes:
  postgres_data:
'@
    
    $dockerComposeContent | Out-File -FilePath "docker-compose.dev.yml" -Encoding UTF8
    
    # Create development Dockerfile for frontend
    $frontendDockerfile = @'
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
'@
    
    $frontendDockerfile | Out-File -FilePath "webapp\frontend\Dockerfile.dev" -Encoding UTF8
    
    Write-Success "Docker development setup created"
    Write-Status "Run 'docker-compose -f docker-compose.dev.yml up' to start with Docker"
}

function Show-Help {
    Write-Host "Usage: .\setup-dev.ps1 [OPTION]" -ForegroundColor White
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  setup     - Full setup (install dependencies, environment, etc.)"
    Write-Host "  install   - Install dependencies only"
    Write-Host "  env       - Set up environment files only"
    Write-Host "  test      - Run tests"
    Write-Host "  build     - Build the application"
    Write-Host "  dev       - Create development server startup script"
    Write-Host "  docker    - Set up Docker development environment"
    Write-Host "  check     - Check system requirements"
    Write-Host "  help      - Show this help message"
    Write-Host ""
}

# Main execution
function Main {
    Write-Host "🚀 Financial Data Web Application - Development Setup" -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host ""

    switch ($Action) {
        "setup" {
            Test-NodeJS
            Test-NPM
            Install-Dependencies
            Setup-Environment
            Test-Database
            Start-DevServers
            Setup-Docker
            Write-Success "Development setup complete!"
            Write-Status "Next steps:"
            Write-Status "1. Make sure your database is running and accessible"
            Write-Status "2. Run '.\start-dev.ps1' to start development servers"
            Write-Status "3. Visit http://localhost:5173 to view the application"
        }
        "install" {
            Test-NodeJS
            Test-NPM
            Install-Dependencies
        }
        "env" {
            Setup-Environment
        }
        "test" {
            Invoke-Tests
        }
        "build" {
            Build-Application
        }
        "dev" {
            Start-DevServers
        }
        "docker" {
            Setup-Docker
        }
        "check" {
            Test-NodeJS
            Test-NPM
            Test-Database
        }
        "help" {
            Show-Help
        }
        default {
            Write-Error "Unknown option: $Action"
            Show-Help
            exit 1
        }
    }
}

# Run main function
Main

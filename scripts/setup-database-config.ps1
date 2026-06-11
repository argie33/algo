#!/usr/bin/env pwsh
<#
.SYNOPSIS
Setup database configuration for local or AWS RDS connection.

.DESCRIPTION
Easily switch between local development database and AWS RDS production database.
This script updates your PowerShell profile with the appropriate database credentials.

.EXAMPLE
# Switch to AWS RDS (requires valid AWS credentials)
.\scripts\setup-database-config.ps1 -UseAWS

# Switch back to local database
.\scripts\setup-database-config.ps1 -UseLocal

# Show current configuration
.\scripts\setup-database-config.ps1 -Show
#>

param(
    [switch]$UseAWS,
    [switch]$UseLocal,
    [switch]$Show
)

# Get the repo root
$RepoRoot = git rev-parse --show-toplevel 2>$null
if (-not $RepoRoot) {
    Write-Host "[ERROR] Not in a git repository" -ForegroundColor Red
    exit 1
}

function Get-CurrentDatabase {
    $host_val = $env:DB_HOST
    if ($host_val -eq "localhost" -or $host_val -eq "127.0.0.1" -or -not $host_val) {
        return "LOCAL"
    } elseif ($host_val -match "rds.amazonaws.com") {
        return "AWS-RDS"
    } else {
        return "UNKNOWN"
    }
}

function Show-Configuration {
    Write-Host "`n=== Current Database Configuration ===" -ForegroundColor Cyan
    Write-Host "Target:       $(Get-CurrentDatabase)" -ForegroundColor $(if((Get-CurrentDatabase) -eq 'AWS-RDS') {'Green'} else {'Yellow'})
    Write-Host "DB_HOST:      $env:DB_HOST"
    Write-Host "DB_PORT:      $env:DB_PORT"
    Write-Host "DB_NAME:      $env:DB_NAME"
    Write-Host "DB_USER:      $env:DB_USER"
    Write-Host "DB_PASSWORD:  $(if($env:DB_PASSWORD) {'[SET]'} else {'[NOT SET]'})"
    Write-Host ""
}

function Get-AWSCredentials {
    Write-Host "Fetching AWS credentials from Secrets Manager..." -ForegroundColor Cyan

    # Check if gh CLI is available
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        Write-Host "[ERROR] GitHub CLI (gh) not found. Install from https://cli.github.com" -ForegroundColor Red
        return $null
    }

    # Get AWS credentials via refresh script
    $script_path = Join-Path $RepoRoot "scripts\refresh-aws-credentials.ps1"
    if (-not (Test-Path $script_path)) {
        Write-Host "[ERROR] refresh-aws-credentials.ps1 not found" -ForegroundColor Red
        return $null
    }

    Write-Host "Running refresh-aws-credentials.ps1..." -ForegroundColor Gray
    & $script_path

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to refresh AWS credentials" -ForegroundColor Red
        return $null
    }

    # Try to get RDS endpoint from AWS Secrets Manager
    Write-Host "Fetching RDS credentials from AWS Secrets Manager..." -ForegroundColor Gray
    try {
        $secret = aws secretsmanager get-secret-value `
            --secret-id algo/database `
            --region us-east-1 `
            --query SecretString `
            --output text 2>$null | ConvertFrom-Json

        if ($secret) {
            return @{
                host = $secret.host
                port = $secret.port -as [string]
                user = $secret.username
                password = $secret.password
                dbname = $secret.dbname
            }
        }
    } catch {
        Write-Host "[WARNING] Could not fetch from Secrets Manager, using default RDS endpoint" -ForegroundColor Yellow
    }

    # Fallback to standard RDS endpoint
    return @{
        host = "algo-db.cvjv6oql86ak.us-east-1.rds.amazonaws.com"
        port = "5432"
        user = "postgres"
        password = ""  # User should set this after getting credentials
        dbname = "algo_trades"
    }
}

function Set-LocalDatabaseEnv {
    Write-Host "`nConfiguring local database..." -ForegroundColor Cyan

    $env:DB_HOST = "localhost"
    $env:DB_PORT = "5432"
    $env:DB_NAME = "stocks"
    $env:DB_USER = "stocks"
    # Keep existing password if set, or prompt
    if (-not $env:DB_PASSWORD) {
        $env:DB_PASSWORD = Read-Host "Enter local database password"
    }

    # Also update PowerShell profile for persistence
    Update-PowerShellProfile @{
        DB_HOST = "localhost"
        DB_PORT = "5432"
        DB_NAME = "stocks"
        DB_USER = "stocks"
    }

    Write-Host "[OK] Local database configured" -ForegroundColor Green
    Show-Configuration
}

function Set-AWSDatabaseEnv {
    Write-Host "`nConfiguring AWS RDS database..." -ForegroundColor Cyan

    $aws_creds = Get-AWSCredentials
    if (-not $aws_creds) {
        Write-Host "[ERROR] Could not retrieve AWS credentials" -ForegroundColor Red
        return
    }

    $env:DB_HOST = $aws_creds.host
    $env:DB_PORT = $aws_creds.port
    $env:DB_NAME = $aws_creds.dbname
    $env:DB_USER = $aws_creds.user
    if ($aws_creds.password) {
        $env:DB_PASSWORD = $aws_creds.password
    } else {
        Write-Host "[WARNING] Password not set. Enter it manually or check AWS Secrets Manager" -ForegroundColor Yellow
        $env:DB_PASSWORD = Read-Host "Enter AWS RDS password"
    }

    # Update PowerShell profile for persistence
    Update-PowerShellProfile @{
        DB_HOST = $aws_creds.host
        DB_PORT = $aws_creds.port
        DB_NAME = $aws_creds.dbname
        DB_USER = $aws_creds.user
    }

    Write-Host "[OK] AWS RDS database configured" -ForegroundColor Green
    Show-Configuration

    # Verify connection
    Write-Host "Testing connection to AWS RDS..." -ForegroundColor Gray
    Test-DatabaseConnection
}

function Test-DatabaseConnection {
    Write-Host "`nTesting connection to database..." -ForegroundColor Gray

    # Try using psql if available
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if ($psql) {
        $env:PGPASSWORD = $env:DB_PASSWORD
        $output = psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME -c "SELECT 'Connection successful' AS status;" 2>&1
        Remove-Item env:PGPASSWORD -ErrorAction SilentlyContinue

        if ($output -match "Connection successful") {
            Write-Host "[OK] Database connection successful" -ForegroundColor Green
            return
        }
    }

    # Fallback: show what to check
    Write-Host "[INFO] Could not verify connection (install PostgreSQL client tools for testing)" -ForegroundColor Yellow
    Write-Host "`nConfiguration details to verify:"
    Write-Host "  - DB_HOST:     $env:DB_HOST"
    Write-Host "  - DB_PORT:     $env:DB_PORT"
    Write-Host "  - DB_NAME:     $env:DB_NAME"
    Write-Host "  - DB_USER:     $env:DB_USER"
    Write-Host "  - DB_PASSWORD: $(if($env:DB_PASSWORD) {'SET'} else {'NOT SET'})"
    Write-Host "`nFor AWS RDS, also check:"
    Write-Host "  - AWS RDS instance is in 'available' state"
    Write-Host "  - Security group allows inbound on port 5432 from your IP"
    Write-Host "  - AWS credentials are current (run refresh-aws-credentials.ps1 if expired)"
}

function Update-PowerShellProfile {
    param([hashtable]$Config)

    $profile_path = $PROFILE.CurrentUserCurrentHost
    if (-not (Test-Path $profile_path)) {
        New-Item -Path $profile_path -ItemType File -Force | Out-Null
    }

    # Read existing profile
    $profile_content = Get-Content $profile_path -Raw -ErrorAction SilentlyContinue
    if (-not $profile_content) {
        $profile_content = ""
    }

    # Remove old database env vars if they exist
    $profile_content = $profile_content -replace '\$env:DB_HOST.*\n', ''
    $profile_content = $profile_content -replace '\$env:DB_PORT.*\n', ''
    $profile_content = $profile_content -replace '\$env:DB_NAME.*\n', ''
    $profile_content = $profile_content -replace '\$env:DB_USER.*\n', ''

    # Add new database env vars
    $new_vars = "`n`n# Algo Database Configuration`n"
    $new_vars += "`$env:DB_HOST = '$($Config.DB_HOST)'`n"
    $new_vars += "`$env:DB_PORT = '$($Config.DB_PORT)'`n"
    $new_vars += "`$env:DB_NAME = '$($Config.DB_NAME)'`n"
    $new_vars += "`$env:DB_USER = '$($Config.DB_USER)'`n"

    $profile_content += $new_vars

    Set-Content -Path $profile_path -Value $profile_content -Encoding UTF8
    Write-Host "[OK] Updated PowerShell profile: $profile_path" -ForegroundColor Gray
}

# Main
Write-Host "Algo Database Configuration Tool" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan

if ($Show) {
    Show-Configuration
} elseif ($UseLocal) {
    Set-LocalDatabaseEnv
} elseif ($UseAWS) {
    Set-AWSDatabaseEnv
} else {
    Write-Host "`nUsage:"
    Write-Host "  -Show    : Show current database configuration"
    Write-Host "  -UseLocal: Switch to local database (localhost)"
    Write-Host "  -UseAWS  : Switch to AWS RDS database"
    Write-Host ""
    Write-Host "Current: $(Get-CurrentDatabase)" -ForegroundColor $(if((Get-CurrentDatabase) -eq 'AWS-RDS') {'Green'} else {'Yellow'})
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\scripts\setup-database-config.ps1 -UseLocal"
    Write-Host "  .\scripts\setup-database-config.ps1 -UseAWS"
    Write-Host "  .\scripts\setup-database-config.ps1 -Show"
}

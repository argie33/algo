# Stock Analytics Platform - PowerShell Environment Setup
# This script sets up environment variables for local development

param(
    [string]$DBHost = "localhost",
    [string]$DBPort = "5432",
    [string]$DBUser = "stocks",
    [string]$DBName = "stocks",
    [string]$DBPassword = "",
    [switch]$Persistent = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Stock Analytics Platform - Setup"
Write-Host "========================================" -ForegroundColor Cyan

# Database Credentials (REQUIRED)
if (-not $DBPassword) {
    Write-Host "`nDatabase Credentials Required:" -ForegroundColor Yellow
    Write-Host "Please provide your PostgreSQL password" -ForegroundColor Gray
    $DBPassword = Read-Host "DB_PASSWORD"
}

if (-not $DBPassword) {
    Write-Host "[ERROR] DB_PASSWORD is required" -ForegroundColor Red
    exit 1
}

Write-Host "`n[Setting environment variables...]" -ForegroundColor Cyan

# Set environment variables for this session
$env:DB_HOST = $DBHost
$env:DB_PORT = $DBPort
$env:DB_USER = $DBUser
$env:DB_NAME = $DBName
$env:DB_PASSWORD = $DBPassword

Write-Host "[OK] Environment variables set for this session:" -ForegroundColor Green
Write-Host "  DB_HOST = $env:DB_HOST"
Write-Host "  DB_PORT = $env:DB_PORT"
Write-Host "  DB_USER = $env:DB_USER"
Write-Host "  DB_NAME = $env:DB_NAME"
Write-Host "  DB_PASSWORD = [SET]"

# Optionally save to PowerShell profile for persistence
if ($Persistent) {
    Write-Host "`n[Setting up persistent profile...]" -ForegroundColor Cyan

    # Find or create profile
    if (-not (Test-Path $PROFILE)) {
        New-Item -ItemType File -Path $PROFILE -Force | Out-Null
        Write-Host "[OK] Created PowerShell profile: $PROFILE"
    }

    # Add credentials to profile
    $profileContent = @"
# Stock Analytics Platform - Development Credentials
# Added on $(Get-Date)

`$env:DB_HOST = "$DBHost"
`$env:DB_PORT = "$DBPort"
`$env:DB_USER = "$DBUser"
`$env:DB_NAME = "$DBName"
`$env:DB_PASSWORD = "$DBPassword"

Write-Host "[OK] Stock Analytics Platform credentials loaded" -ForegroundColor Green
"@

    Add-Content -Path $PROFILE -Value $profileContent
    Write-Host "[OK] Credentials added to profile: $PROFILE"

    # Restrict permissions to owner only
    try {
        $acl = Get-Acl $PROFILE
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            "$env:username", "FullControl", "Allow"
        )
        $acl.SetAccessRule($rule)
        Set-Acl $PROFILE $acl
        Write-Host "[OK] Restricted profile permissions to owner only"
    } catch {
        Write-Host "[WARN] Could not restrict profile permissions: $_" -ForegroundColor Yellow
    }
}

# Test connection to database
Write-Host "`n[Testing database connection...]" -ForegroundColor Cyan

try {
    python3 -c "
from config.credential_manager import get_db_credentials
creds = get_db_credentials()
print(f'[OK] Database credentials loaded: {creds[\"user\"]}@{creds[\"host\"]}:{creds[\"port\"]}/{creds[\"database\"]}')
"
    Write-Host "[OK] Credentials are valid!" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Could not test credentials - ensure Python is in PATH"
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

if ($Persistent) {
    Write-Host "`nNext steps:"
    Write-Host "1. Restart PowerShell for permanent credentials to take effect"
    Write-Host "2. Run: python3 init_database.py"
    Write-Host "3. Run: python3 run-all-loaders.py"
} else {
    Write-Host "`nNext steps:"
    Write-Host "1. Run: python3 init_database.py"
    Write-Host "2. Run: python3 run-all-loaders.py"
    Write-Host "`nTip: Use -Persistent flag to save credentials to PowerShell profile"
    Write-Host "     ./scripts/setup-powershell-env.ps1 -DBPassword 'your-password' -Persistent"
}

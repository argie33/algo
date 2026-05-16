# Stock Analytics Platform - New PC Setup Script
# Run this in PowerShell as Administrator
# Right-click PowerShell -> "Run as Administrator" -> paste this script

param(
    [switch]$SkipChocolatey,
    [switch]$SkipDocker
)

Write-Host "=== Stock Analytics Platform - New PC Setup ===" -ForegroundColor Cyan

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
if (-not $isAdmin) {
    Write-Host "ERROR: This script must run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell -> 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Running as Administrator" -ForegroundColor Green

# Install Chocolatey if not present
if (-not (Test-Path "C:\ProgramData\chocolatey")) {
    Write-Host "Installing Chocolatey..." -ForegroundColor Cyan
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    Write-Host "✓ Chocolatey installed" -ForegroundColor Green
} else {
    Write-Host "✓ Chocolatey already installed" -ForegroundColor Green
}

# Install tools via Chocolatey
Write-Host "Installing development tools..." -ForegroundColor Cyan
choco install -y awscli github-cli git
Write-Host "✓ Tools installed" -ForegroundColor Green

# Install WSL 2 and Docker if not skipped
if (-not $SkipDocker) {
    Write-Host "Installing WSL 2..." -ForegroundColor Cyan
    wsl --install -d Ubuntu-24.04
    Write-Host "✓ WSL 2 installed (requires restart)" -ForegroundColor Yellow
}

Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Restart PowerShell (tools will be in PATH)"
Write-Host "2. Set GitHub Secrets: gh secret set ALPACA_API_KEY_ID --body 'PK7ZEKP3CSYZ3EUBHPXBRHJGT6'"
Write-Host "3. Configure AWS: aws configure"
Write-Host "4. If installed WSL: Restart computer, then docker-compose up -d in WSL"

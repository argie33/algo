#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Start the API dev server for local dashboard development

.DESCRIPTION
  Starts dev_server.py on localhost:3001 with:
  - Dev mode enabled (no Cognito JWT validation required)
  - LOCAL_MODE enabled (connects to localhost postgres instead of AWS RDS)
  - Dev authentication enabled (accepts dev-user, dev-admin tokens)

  This allows full dashboard testing without AWS credentials or Cognito setup.

.EXAMPLE
  .\start-local-dev-server.ps1

.NOTES
  - Requires localhost postgres running on port 5432 with stocks database
  - Dev tokens: "dev-user" or "dev-admin" (pass as Authorization: Bearer dev-user)
  - Stop with Ctrl+C in the terminal running the server
#>

Write-Host "Starting API dev server for local development..."
Write-Host ""

# Clear Cognito environment variables (enables dev mode)
# Use Remove-Item to properly unset the variables (setting to $null doesn't work in PowerShell)
Remove-Item Env:\COGNITO_USER_POOL_ID -ErrorAction SilentlyContinue
Remove-Item Env:\COGNITO_CLIENT_ID -ErrorAction SilentlyContinue
Remove-Item Env:\COGNITO_REGION -ErrorAction SilentlyContinue

# Enable local mode (use localhost postgres instead of AWS RDS)
$env:LOCAL_MODE = "true"

# Set API port
$env:API_PORT = "3001"

# Start dev server
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repoRoot

Write-Host "Configuration:"
Write-Host "  LOCAL_MODE: true (using localhost postgres)"
Write-Host "  COGNITO: disabled (dev mode enabled)"
Write-Host "  API_PORT: 3001"
Write-Host "  Database: localhost:5432/stocks"
Write-Host ""
Write-Host "Dev tokens accepted:"
Write-Host "  - dev-user (basic user)"
Write-Host "  - dev-admin (admin access)"
Write-Host ""
Write-Host "Usage:"
Write-Host "  curl -H 'Authorization: Bearer dev-admin' http://localhost:3001/api/algo/portfolio"
Write-Host ""
Write-Host "Starting server..."
Write-Host ""

python -m lambda.api.dev_server

Pop-Location

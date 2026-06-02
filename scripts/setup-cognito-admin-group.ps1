#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Sets up Cognito admin group and adds user (T1-A audit completion)

.DESCRIPTION
  This script automates the manual T1-A action: creating the admin group
  in Cognito and adding argeropolos@gmail.com to it.

  Prerequisites:
  - AWS CLI configured with credentials
  - User must already exist in Cognito user pool
#>

param(
    [string]$UserPoolId = "",
    [string]$Email = "argeropolos@gmail.com",
    [string]$Region = "us-east-1"
)

Write-Host "=== Cognito Admin Group Setup (T1-A) ===" -ForegroundColor Cyan

# If no pool ID provided, try to find it
if (-not $UserPoolId) {
    Write-Host "No user pool ID provided, discovering from AWS..." -ForegroundColor Yellow
    try {
        $pools = aws cognito-idp list-user-pools --max-results 1 --region $Region --query 'UserPools[0]' --output json | ConvertFrom-Json
        $UserPoolId = $pools.Id
        Write-Host "Found user pool: $($pools.Name) ($UserPoolId)" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to discover user pool. Please specify with -UserPoolId"
        exit 1
    }
}

if (-not $UserPoolId) {
    Write-Error "No user pool found"
    exit 1
}

Write-Host ""
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  User Pool ID: $UserPoolId"
Write-Host "  Email: $Email"
Write-Host "  Region: $Region"
Write-Host ""

# Step 1: Create admin group (idempotent)
Write-Host "Step 1: Creating admin group..." -ForegroundColor Yellow
try {
    aws cognito-idp create-group `
        --user-pool-id $UserPoolId `
        --group-name admin `
        --description "Full access to admin-gated algo dashboard and trading endpoints" `
        --region $Region | Out-Null
    Write-Host "✓ Admin group created" -ForegroundColor Green
}
catch {
    if ($_.Exception.Message -match "GroupExistsException|already exists") {
        Write-Host "✓ Admin group already exists" -ForegroundColor Green
    } else {
        Write-Error "Failed to create admin group: $_"
        exit 1
    }
}

# Step 2: Add user to admin group (idempotent)
Write-Host "Step 2: Adding user to admin group..." -ForegroundColor Yellow
try {
    aws cognito-idp admin-add-user-to-group `
        --user-pool-id $UserPoolId `
        --username $Email `
        --group-name admin `
        --region $Region | Out-Null
    Write-Host "✓ User $Email added to admin group" -ForegroundColor Green
}
catch {
    if ($_.Exception.Message -match "UserNotFoundException") {
        Write-Error "User $Email not found in pool. Create user first and try again."
        exit 1
    } else {
        Write-Error "Failed to add user to group: $_"
        exit 1
    }
}

Write-Host ""
Write-Host "=== T1-A COMPLETE ===" -ForegroundColor Green
Write-Host "Admin group is now configured. Users can:" -ForegroundColor Cyan
Write-Host "  - Access /api/admin/* endpoints"
Write-Host "  - View audit logs and system health"
Write-Host "  - Access admin dashboard features"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. User will get 'admin' in cognito:groups claim on next login"
Write-Host "  2. User must log out and log back in for groups to refresh"
Write-Host "  3. Complete T1-D: Run seasonality loader (GitHub Actions)"

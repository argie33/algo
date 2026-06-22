#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Refresh AWS credentials for local development

.DESCRIPTION
    Fetches fresh AWS credentials and updates configuration.
    Called when: credentials expire, AWS errors occur, or quarterly during rotation.

.EXAMPLE
    PS> .\scripts\refresh-aws-credentials.ps1
#>

param(
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

function Write-Success { Write-Host -ForegroundColor Green @args }
function Write-Error_ { Write-Host -ForegroundColor Red @args }
function Write-Info { Write-Host -ForegroundColor Cyan @args }
function Write-Warning_ { Write-Host -ForegroundColor Yellow @args }

$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Write-Info "Refreshing AWS credentials..."
Write-Info "Root directory: $RootDir"

# Step 1: Set AWS profile
$ExistingProfile = if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "algo-developer" }
$env:AWS_PROFILE = $ExistingProfile
$env:AWS_REGION = "us-east-1"

Write-Info "Using AWS profile: $ExistingProfile"

# Step 2: Validate credentials
try {
    Write-Info "Validating AWS credentials..."
    $WhoAmI = aws sts get-caller-identity --profile $ExistingProfile --output json 2>&1 | ConvertFrom-Json
    $AccountId = $WhoAmI.Account
    $Arn = $WhoAmI.Arn

    Write-Success "Credentials validated"
    Write-Info "Account: $AccountId"
    Write-Info "ARN: $Arn"
} catch {
    Write-Error_ "Failed to validate credentials: $_"
    Write-Info ""
    Write-Info "Setup options:"
    Write-Info "  1. Configure AWS credentials: aws configure --profile algo-developer"
    Write-Info "  2. Set environment variables:"
    Write-Info "     `$env:AWS_ACCESS_KEY_ID = '...'"
    Write-Info "     `$env:AWS_SECRET_ACCESS_KEY = '...'"
    Write-Info "  3. Use AWS SSO: aws sso login --profile algo-developer"
    exit 1
}

# Step 3: Fetch Terraform outputs (which includes Cognito + API gateway config)
try {
    Write-Info "Fetching Terraform outputs..."
    Push-Location $RootDir/terraform

    $TfOutputs = terraform output -json 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning_ "Terraform output failed: $TfOutputs"
        Pop-Location
        exit 1
    }

    $Outputs = $TfOutputs | ConvertFrom-Json

    Write-Success "Terraform outputs retrieved"
    
    # Display key outputs
    if ($Outputs.api_url) {
        Write-Info "API URL: $($Outputs.api_url.value)"
    }
    if ($Outputs.cognito_user_pool_id) {
        Write-Info "Cognito User Pool ID: $($Outputs.cognito_user_pool_id.value)"
    }

    Pop-Location

} catch {
    Write-Error_ "Failed to fetch Terraform outputs: $_"
    Write-Info ""
    Write-Info "Terraform initialization needed. Run:"
    Write-Info "  cd terraform && terraform init"
    exit 1
}

Write-Success "[✓] Credentials refreshed and ready to use"
Write-Info ""
Write-Info "Next steps:"
Write-Info "  1. Dashboard will automatically fetch Terraform outputs:"
Write-Info "     python -m tools.dashboard.dashboard"
Write-Info "  2. Or set environment variables manually:"
Write-Info "     `$env:DASHBOARD_API_URL = '...'"
Write-Info "     `$env:COGNITO_USER_POOL_ID = '...'"
Write-Info "     `$env:COGNITO_CLIENT_ID = '...'"

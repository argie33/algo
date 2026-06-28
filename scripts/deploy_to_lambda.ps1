#!/usr/bin/env pwsh
<#
.SYNOPSIS
Deploy algo-api to AWS Lambda with verification

.DESCRIPTION
Builds the Lambda package, deploys it, and tests the live endpoints

.EXAMPLE
./scripts/deploy_to_lambda.ps1
#>

param(
    [string]$FunctionName = "algo-api",
    [string]$Region = "us-east-1",
    [switch]$SkipBuild = $false,
    [switch]$SkipDeploy = $false,
    [switch]$SkipTest = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "AWS Lambda Deployment for algo-api" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Verify AWS credentials
Write-Host "[1/5] Verifying AWS credentials..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity --region $Region --output json | ConvertFrom-Json
    Write-Host "✓ AWS Account: $($identity.Account)" -ForegroundColor Green
    Write-Host "✓ User: $($identity.Arn)" -ForegroundColor Green
} catch {
    Write-Host "✗ AWS credentials not configured or invalid" -ForegroundColor Red
    Write-Host "  Run: ./scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
    exit 1
}

# Step 2: Build Lambda package
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[2/5] Building Lambda package..." -ForegroundColor Yellow

    $LambdaDir = Join-Path $PSScriptRoot ".." "lambda" "api"
    $PackageDir = Join-Path $LambdaDir "package"
    $ZipFile = Join-Path $LambdaDir "algo-api.zip"

    # Clean previous build
    if (Test-Path $PackageDir) {
        Write-Host "  Cleaning previous build..."
        Remove-Item $PackageDir -Recurse -Force
    }
    if (Test-Path $ZipFile) {
        Remove-Item $ZipFile -Force
    }

    # Create package directory
    New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null
    Write-Host "  Creating package directory..." -ForegroundColor Gray

    # Install dependencies
    Write-Host "  Installing dependencies..." -ForegroundColor Gray
    $RequirementsFile = Join-Path $LambdaDir "requirements.txt"
    pip install -q -r $RequirementsFile -t $PackageDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
        exit 1
    }

    # Copy Python files
    Write-Host "  Copying Lambda function files..." -ForegroundColor Gray
    Get-ChildItem $LambdaDir -Filter "*.py" | ForEach-Object {
        Copy-Item $_.FullName -Destination $PackageDir
    }

    # Create ZIP file
    Write-Host "  Creating ZIP package..." -ForegroundColor Gray
    Push-Location $PackageDir
    # Use PowerShell's native Compress-Archive for better cross-platform support
    Get-ChildItem -Recurse | Compress-Archive -DestinationPath $ZipFile -Update -Force -ErrorAction Stop
    Pop-Location

    $ZipSize = (Get-Item $ZipFile).Length / 1MB
    Write-Host "✓ Lambda package created: $ZipFile ($([math]::Round($ZipSize, 2)) MB)" -ForegroundColor Green
} else {
    Write-Host "[2/5] Skipping build (--SkipBuild)" -ForegroundColor Gray
}

# Step 3: Deploy to Lambda
if (-not $SkipDeploy) {
    Write-Host ""
    Write-Host "[3/5] Deploying to AWS Lambda..." -ForegroundColor Yellow

    $LambdaDir = Join-Path $PSScriptRoot ".." "lambda" "api"
    $ZipFile = Join-Path $LambdaDir "algo-api.zip"

    Write-Host "  Function: $FunctionName" -ForegroundColor Gray
    Write-Host "  Region: $Region" -ForegroundColor Gray

    try {
        $DeployOutput = aws lambda update-function-code `
            --function-name $FunctionName `
            --zip-file fileb://$ZipFile `
            --region $Region `
            --output json | ConvertFrom-Json

        Write-Host "✓ Deployment successful" -ForegroundColor Green
        Write-Host "  CodeSha256: $($DeployOutput.CodeSha256)" -ForegroundColor Gray
        Write-Host "  LastModified: $($DeployOutput.LastModified)" -ForegroundColor Gray
    } catch {
        Write-Host "✗ Deployment failed: $_" -ForegroundColor Red
        exit 1
    }

    # Wait for deployment to complete
    Write-Host "  Waiting for deployment to stabilize (10s)..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
} else {
    Write-Host "[3/5] Skipping deployment (--SkipDeploy)" -ForegroundColor Gray
}

# Step 4: Get API Gateway endpoint
Write-Host ""
Write-Host "[4/5] Finding API Gateway endpoint..." -ForegroundColor Yellow

try {
    # Get the API Gateway ID from Lambda function configuration
    $LambdaConfig = aws lambda get-function-url-config `
        --function-name $FunctionName `
        --region $Region `
        --output json 2>$null | ConvertFrom-Json

    if ($LambdaConfig.FunctionUrl) {
        $ApiEndpoint = $LambdaConfig.FunctionUrl
        Write-Host "✓ Found Function URL: $ApiEndpoint" -ForegroundColor Green
    } else {
        Write-Host "⚠ Could not find Lambda Function URL" -ForegroundColor Yellow
        Write-Host "  Please configure API Gateway manually and set endpoint for testing" -ForegroundColor Yellow
        $ApiEndpoint = $null
    }
} catch {
    Write-Host "⚠ Could not retrieve Function URL: $_" -ForegroundColor Yellow
    $ApiEndpoint = $null
}

# Step 5: Test endpoints
if (-not $SkipTest -and $ApiEndpoint) {
    Write-Host ""
    Write-Host "[5/5] Testing live endpoints..." -ForegroundColor Yellow

    $Endpoints = @(
        @{path = "/api/algo/positions"; name = "Positions"}
        @{path = "/api/algo/performance"; name = "Performance"}
        @{path = "/api/algo/swing-scores"; name = "Swing Scores"}
    )

    $FailedTests = @()

    foreach ($endpoint in $Endpoints) {
        Write-Host "  Testing $($endpoint.name)..." -ForegroundColor Gray
        try {
            $Response = Invoke-WebRequest -Uri "$ApiEndpoint$($endpoint.path)" `
                -Method GET `
                -TimeoutSec 10 `
                -SkipHttpErrorCheck `
                -Headers @{"Accept" = "application/json"}

            if ($Response.StatusCode -eq 200) {
                Write-Host "    ✓ $($endpoint.name) returned 200 OK" -ForegroundColor Green
            } else {
                Write-Host "    ✗ $($endpoint.name) returned $($Response.StatusCode)" -ForegroundColor Red
                $FailedTests += $endpoint.name
            }
        } catch {
            Write-Host "    ✗ $($endpoint.name) failed: $_" -ForegroundColor Red
            $FailedTests += $endpoint.name
        }
        Start-Sleep -Milliseconds 500
    }

    if ($FailedTests.Count -eq 0) {
        Write-Host "✓ All endpoints responding correctly!" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed endpoints: $($FailedTests -join ', ')" -ForegroundColor Red
    }
} else {
    Write-Host "[5/5] Skipping endpoint tests (--SkipTest or no endpoint URL)" -ForegroundColor Gray
}

# Summary
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Deployment Complete" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Open dashboard in browser" -ForegroundColor Yellow
Write-Host "2. Verify all panels load" -ForegroundColor Yellow
Write-Host "3. Check CloudWatch logs:" -ForegroundColor Yellow
Write-Host "   aws logs tail /aws/lambda/$FunctionName --follow" -ForegroundColor Yellow
Write-Host ""

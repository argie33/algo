# Financial Dashboard - Serverless Deployment Script (PowerShell) 
# This script deploys the webapp to AWS Lambda + API Gateway + CloudFront

param(
    [string]$Environment = "prod",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

# Configuration - Use existing stack name
$StackName = if ($Environment -eq "prod") { "stocks-webapp-stack" } else { "stocks-webapp-$Environment" }

# Logging functions
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Check prerequisites
function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check AWS CLI
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        Write-Error "AWS CLI is not installed. Please install it first."
        exit 1
    }
    
    # Check SAM CLI
    if (-not (Get-Command sam -ErrorAction SilentlyContinue)) {
        Write-Error "SAM CLI is not installed. Please install it first."
        exit 1
    }
    
    # Check Node.js
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Error "Node.js is not installed. Please install Node.js 18 or later."
        exit 1
    }
    
    # Check npm
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Error "npm is not installed. Please install npm."
        exit 1
    }
    
    # Check AWS credentials
    try {
        aws sts get-caller-identity --output text | Out-Null
    }
    catch {
        Write-Error "AWS credentials are not configured. Please run 'aws configure'."
        exit 1
    }
    
    Write-Success "Prerequisites check passed"
}

# Build Lambda function
function Build-Lambda {
    Write-Info "Building Lambda function..."
    
    Push-Location webapp\lambda
    
    try {
        # Install dependencies
        Write-Info "Installing Lambda dependencies..."
        npm ci --only=production
        
        # Verify required files exist
        if (-not (Test-Path "index.js")) {
            Write-Error "Lambda function index.js not found"
            exit 1
        }
        
        if (-not (Test-Path "package.json")) {
            Write-Error "Lambda package.json not found"
            exit 1
        }
        
        Write-Success "Lambda function built successfully"
    }
    finally {
        Pop-Location
    }
}

# Build frontend
function Build-Frontend {
    Write-Info "Building frontend..."
    
    Push-Location webapp\frontend
    
    try {
        # Install dependencies
        Write-Info "Installing frontend dependencies..."
        npm ci
        
        # Build with serverless configuration
        Write-Info "Building frontend for serverless deployment..."
        $env:VITE_SERVERLESS = "true"
        $env:VITE_API_URL = "/api"
        npm run build
        
        # Verify build output
        if (-not (Test-Path "dist")) {
            Write-Error "Frontend build failed - dist directory not found"
            exit 1
        }
        
        Write-Success "Frontend built successfully"
    }
    finally {
        Pop-Location
        Remove-Item env:VITE_SERVERLESS -ErrorAction SilentlyContinue
        Remove-Item env:VITE_API_URL -ErrorAction SilentlyContinue
    }
}

# Deploy infrastructure
function Deploy-Infrastructure {
    Write-Info "Deploying infrastructure..."
    
    # Get database secret ARN
    Write-Info "Looking up database secret..."
    $DbSecretArn = aws secretsmanager list-secrets `
        --query "SecretList[?contains(Name, 'rds-db-credentials')].ARN | [0]" `
        --output text `
        --region $Region
    
    if ($DbSecretArn -eq "None" -or [string]::IsNullOrEmpty($DbSecretArn)) {
        Write-Error "Database secret not found. Please ensure RDS is deployed first."
        exit 1
    }
    
    Write-Info "Using database secret: $DbSecretArn"
    
    # Get database endpoint
    Write-Info "Looking up database endpoint..."
    $DbEndpoint = aws rds describe-db-instances `
        --query "DBInstances[0].Endpoint.Address" `
        --output text `
        --region $Region
    
    if ($DbEndpoint -eq "None" -or [string]::IsNullOrEmpty($DbEndpoint)) {
        Write-Error "Database endpoint not found. Please ensure RDS is deployed first."
        exit 1
    }
    
    Write-Info "Using database endpoint: $DbEndpoint"
    
    # Deploy with SAM
    Write-Info "Deploying CloudFormation stack..."
    sam deploy `
        --template-file ..\template-webapp-lambda.yml `
        --stack-name $StackName `
        --capabilities CAPABILITY_IAM `
        --parameter-overrides `
            EnvironmentName=$Environment `
            DatabaseSecretArn=$DbSecretArn `
            DatabaseEndpoint=$DbEndpoint `
        --no-fail-on-empty-changeset `
        --region $Region
    
    Write-Success "Infrastructure deployed successfully"
}

# Get stack outputs
function Get-StackOutputs {
    Write-Info "Getting stack outputs..."
    
    $script:ApiUrl = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" `
        --output text `
        --region $Region
    
    $script:BucketName = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" `
        --output text `
        --region $Region
    
    $script:CloudFrontId = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" `
        --output text `
        --region $Region
    
    $script:WebsiteUrl = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --query "Stacks[0].Outputs[?OutputKey=='WebsiteURL'].OutputValue" `
        --output text `
        --region $Region
    
    Write-Success "Stack outputs retrieved"
}

# Deploy frontend to S3
function Deploy-Frontend {
    Write-Info "Deploying frontend to S3..."
    
    if ([string]::IsNullOrEmpty($script:BucketName)) {
        Write-Error "S3 bucket name not found"
        exit 1
    }
    
    # Sync frontend files
    Write-Info "Syncing files to S3 bucket: $($script:BucketName)"
    
    # Upload assets with long cache
    aws s3 sync webapp\frontend\dist s3://$($script:BucketName) `
        --delete `
        --cache-control "public, max-age=31536000" `
        --exclude "*.html" `
        --exclude "service-worker.js" `
        --region $Region
    
    # Upload HTML files with short cache
    aws s3 sync webapp\frontend\dist s3://$($script:BucketName) `
        --cache-control "public, max-age=300" `
        --include "*.html" `
        --include "service-worker.js" `
        --region $Region
    
    Write-Success "Frontend deployed to S3"
}

# Invalidate CloudFront cache
function Invoke-CloudFrontInvalidation {
    Write-Info "Invalidating CloudFront cache..."
    
    if ([string]::IsNullOrEmpty($script:CloudFrontId)) {
        Write-Error "CloudFront distribution ID not found"
        exit 1
    }
    
    aws cloudfront create-invalidation `
        --distribution-id $script:CloudFrontId `
        --paths "/*" `
        --region $Region
    
    Write-Success "CloudFront cache invalidated"
}

# Test deployment
function Test-Deployment {
    Write-Info "Testing deployment..."
    
    # Test API health
    Write-Info "Testing API health..."
    $maxAttempts = 10
    $attemptCount = 0
    
    do {
        $attemptCount++
        try {
            $response = Invoke-WebRequest -Uri "$($script:ApiUrl)/health" -Method Get -TimeoutSec 30
            if ($response.StatusCode -eq 200) {
                Write-Success "API health check passed"
                break
            }
        }
        catch {
            Write-Warning "API not ready, attempt $attemptCount/$maxAttempts"
            Start-Sleep -Seconds 30
        }
        
        if ($attemptCount -eq $maxAttempts) {
            Write-Error "API health check failed after $maxAttempts attempts"
            exit 1
        }
    } while ($attemptCount -lt $maxAttempts)
    
    # Test frontend
    Write-Info "Testing frontend..."
    try {
        $response = Invoke-WebRequest -Uri $script:WebsiteUrl -Method Get -TimeoutSec 30
        if ($response.StatusCode -eq 200) {
            Write-Success "Frontend accessibility test passed"
        }
    }
    catch {
        Write-Error "Frontend accessibility test failed"
        exit 1
    }
    
    Write-Success "All tests passed"
}

# Main deployment function
function Main {
    Write-Info "Starting Financial Dashboard serverless deployment..."
    Write-Info "Environment: $Environment"
    Write-Info "Region: $Region"
    Write-Info "Stack: $StackName"
    Write-Host ""
    
    Test-Prerequisites
    Build-Lambda
    Build-Frontend
    Deploy-Infrastructure
    Get-StackOutputs
    Deploy-Frontend
    Invoke-CloudFrontInvalidation
    Test-Deployment
    
    # Print summary
    Write-Host ""
    Write-Success "🎉 Deployment completed successfully!"
    Write-Host ""
    Write-Host "📋 Deployment Summary:" -ForegroundColor Blue
    Write-Host "Environment: $Environment"
    Write-Host "Region: $Region"
    Write-Host "Stack: $StackName"
    Write-Host ""
    Write-Host "🌐 URLs:" -ForegroundColor Blue
    Write-Host "Website: $($script:WebsiteUrl)"
    Write-Host "API: $($script:ApiUrl)"
    Write-Host ""
    Write-Host "AWS Resources:" -ForegroundColor Blue
    Write-Host "S3 Bucket: $($script:BucketName)"
    Write-Host "CloudFront: $($script:CloudFrontId)"
    Write-Host ""
    Write-Host "Cost Savings: 85-95% reduction vs ECS (estimated $1-5/month)" -ForegroundColor Green
    Write-Host ""
    Write-Success "Financial Dashboard is now live on serverless architecture!"
}

# Handle script parameters
if ($args -contains "-h" -or $args -contains "--help") {
    Write-Host "Usage: .\deploy-serverless.ps1 [-Environment env] [-Region region]"
    Write-Host "Environments: dev, staging, prod (default: prod)"
    Write-Host "Region: AWS region (default: us-east-1)"
    exit 0
}

# Validate environment
if ($Environment -notin @("dev", "staging", "prod")) {
    Write-Error "Invalid environment: $Environment"
    Write-Host "Valid environments: dev staging prod"
    exit 1
}

# Run main deployment
Main
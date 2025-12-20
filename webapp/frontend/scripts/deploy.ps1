#!/usr/bin/env powershell

param(
    [string]$StackName = "financial-dashboard-dev",
    [string]$Environment = "dev",
    [switch]$SkipBuild = $false,
    [switch]$Verbose = $false
)

Write-Host "🚀 Deploying Financial Dashboard Frontend" -ForegroundColor Green
Write-Host "Stack: $StackName" -ForegroundColor Yellow
Write-Host "Environment: $Environment" -ForegroundColor Yellow

# Function to get CloudFormation outputs
function Get-StackOutputs {
    param([string]$StackName)
    
    try {
        Write-Host "📋 Getting CloudFormation stack outputs..." -ForegroundColor Blue
        
        $outputs = aws cloudformation describe-stacks --stack-name $StackName --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
        
        $outputMap = @{}
        foreach ($output in $outputs) {
            $outputMap[$output.OutputKey] = $output.OutputValue
        }
        
        return $outputMap
    }
    catch {
        Write-Error "Failed to get CloudFormation outputs: $_"
        return $null
    }
}

# Get stack outputs
$stackOutputs = Get-StackOutputs -StackName $StackName

if (-not $stackOutputs) {
    Write-Error "Could not retrieve stack outputs. Make sure the stack exists and you have proper AWS credentials."
    exit 1
}

$apiUrl = $stackOutputs.ApiGatewayUrl
$bucketName = $stackOutputs.FrontendBucketName
$cloudFrontId = $stackOutputs.CloudFrontDistributionId
$websiteUrl = $stackOutputs.WebsiteURL

Write-Host "🔗 API Gateway URL: $apiUrl" -ForegroundColor Green
Write-Host "🪣 S3 Bucket: $bucketName" -ForegroundColor Green
Write-Host "☁️ CloudFront Distribution: $cloudFrontId" -ForegroundColor Green
Write-Host "🌐 Website URL: $websiteUrl" -ForegroundColor Green

# Build the frontend if not skipped
if (-not $SkipBuild) {
    Write-Host "📦 Building frontend with configuration..." -ForegroundColor Blue
    
    # Create runtime configuration
    $config = @{
        API_URL = $apiUrl
        BUILD_TIME = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
        VERSION = "1.0.0"
        ENVIRONMENT = $Environment
        STACK_NAME = $StackName
    }
    
    $configJs = "window.__APP_CONFIG__ = $($config | ConvertTo-Json -Depth 10);"
    $configPath = Join-Path "public" "config.js"
    
    $configJs | Out-File -FilePath $configPath -Encoding UTF8
    Write-Host "✅ Created runtime config: $configPath" -ForegroundColor Green
    
    # Build the project
    npm run build
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build failed"
        exit 1
    }
    
    Write-Host "✅ Frontend build completed" -ForegroundColor Green
}

# Deploy to S3
Write-Host "📤 Uploading to S3..." -ForegroundColor Blue

aws s3 sync dist/ s3://$bucketName --delete --cache-control "public, max-age=31536000" --exclude "*.html" --exclude "config.js"
aws s3 sync dist/ s3://$bucketName --delete --cache-control "public, max-age=300" --include "*.html" --include "config.js"

if ($LASTEXITCODE -ne 0) {
    Write-Error "S3 upload failed"
    exit 1
}

Write-Host "✅ S3 upload completed" -ForegroundColor Green

# Invalidate CloudFront cache
Write-Host "🔄 Invalidating CloudFront cache..." -ForegroundColor Blue

aws cloudfront create-invalidation --distribution-id $cloudFrontId --paths "/*"

if ($LASTEXITCODE -ne 0) {
    Write-Error "CloudFront invalidation failed"
    exit 1
}

Write-Host "✅ CloudFront invalidation initiated" -ForegroundColor Green

Write-Host ""
Write-Host "🎉 Deployment completed successfully!" -ForegroundColor Green
Write-Host "🌐 Website URL: $websiteUrl" -ForegroundColor Yellow
Write-Host "🔗 API URL: $apiUrl" -ForegroundColor Yellow

# Test the deployment
Write-Host ""
Write-Host "🧪 Testing deployment..." -ForegroundColor Blue

try {
    $response = Invoke-WebRequest -Uri $websiteUrl -Method GET -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Website is responding" -ForegroundColor Green
    }
}
catch {
    Write-Warning "⚠️ Website test failed: $_"
}

try {
    $healthUrl = "$apiUrl/health"
    $response = Invoke-WebRequest -Uri $healthUrl -Method GET -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ API is responding" -ForegroundColor Green
    }
}
catch {
    Write-Warning "⚠️ API test failed: $_"
}

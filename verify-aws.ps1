# Verify AWS deployment is working
# Run with: ! powershell -ExecutionPolicy Bypass -File verify-aws.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AWS DEPLOYMENT VERIFICATION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# Check 1: AWS CLI configured
Write-Host "[Check 1] AWS CLI credentials..." -ForegroundColor Yellow
try {
    $profile = aws sts get-caller-identity --output json 2>&1 | ConvertFrom-Json
    if ($profile.UserId) {
        Write-Host "✅ AWS CLI configured (Account: $($profile.Account))" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ AWS credentials not configured" -ForegroundColor Red
    Write-Host "   Run: aws configure" -ForegroundColor Yellow
    $allPassed = $false
}

Write-Host ""

# Check 2: RDS Database
Write-Host "[Check 2] RDS Database..." -ForegroundColor Yellow
try {
    $rds = aws rds describe-db-instances --region us-east-1 --query 'DBInstances[0].{ID:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine}' --output json 2>&1 | ConvertFrom-Json
    if ($rds.ID) {
        Write-Host "✅ RDS instance found" -ForegroundColor Green
        Write-Host "   ID: $($rds.ID)" -ForegroundColor Green
        Write-Host "   Status: $($rds.Status)" -ForegroundColor Green
        Write-Host "   Engine: $($rds.Engine)" -ForegroundColor Green
    }
} catch {
    Write-Host "❌ RDS check failed" -ForegroundColor Red
    Write-Host "   Error: $_" -ForegroundColor Yellow
    $allPassed = $false
}

Write-Host ""

# Check 3: API Gateway
Write-Host "[Check 3] API Gateway..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/prod/health" -UseBasicParsing 2>&1
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ API Gateway responding (200 OK)" -ForegroundColor Green
        Write-Host "   Response: $($response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 1)" -ForegroundColor Green
    } else {
        Write-Host "⚠️  API returned $($response.StatusCode)" -ForegroundColor Yellow
        $allPassed = $false
    }
} catch {
    Write-Host "❌ API Gateway check failed" -ForegroundColor Red
    Write-Host "   Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
    Write-Host "   Reason: $($_.Exception.Message)" -ForegroundColor Yellow
    $allPassed = $false
}

Write-Host ""

# Check 4: CloudFront Frontend
Write-Host "[Check 4] CloudFront Frontend..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://d5j1h4wzrkvw7.cloudfront.net/" -UseBasicParsing -MaximumRedirection 0 2>&1
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ CloudFront frontend responding (200 OK)" -ForegroundColor Green
        Write-Host "   Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor Green
        Write-Host "   Content-Length: $($response.Content.Length) bytes" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Frontend returned $($response.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Frontend check failed" -ForegroundColor Red
    Write-Host "   Status: $($_.Exception.Response.StatusCode)" -ForegroundColor Yellow
    $allPassed = $false
}

Write-Host ""

# Check 5: GitHub Actions Deployment
Write-Host "[Check 5] GitHub Actions Deployment..." -ForegroundColor Yellow
try {
    # Try to get recent deployment status from GitHub
    Write-Host "⚠️  GitHub Actions check requires 'gh' CLI (optional)" -ForegroundColor Yellow
    Write-Host "   To enable: Install GitHub CLI (https://cli.github.com)" -ForegroundColor Yellow
} catch {
    Write-Host "   Skipped" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

if ($allPassed) {
    Write-Host "✅ AWS DEPLOYMENT VERIFIED" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  SOME CHECKS FAILED" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  - API returning 404? Check Lambda deployment in AWS console" -ForegroundColor Yellow
    Write-Host "  - CloudFront down? Check S3 bucket and CloudFront distribution" -ForegroundColor Yellow
    Write-Host "  - AWS credentials error? Run: aws configure" -ForegroundColor Yellow
}

Write-Host ""

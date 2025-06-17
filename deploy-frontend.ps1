# Simple Frontend Deployment Script
param(
    [string]$BucketName = "financial-dashboard-frontend-prod-293337163605",
    [string]$DistributionId = "E3UPBXLAY5SZZ4"
)

Write-Host "🚀 Deploying Frontend to Production..." -ForegroundColor Blue

# Build frontend
Write-Host "📦 Building frontend..." -ForegroundColor Yellow
cd webapp/frontend
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}

# Sync to S3
Write-Host "☁️ Uploading to S3..." -ForegroundColor Yellow
try {
    aws s3 sync dist/ s3://$BucketName/ --delete --quiet
    Write-Host "✅ Upload successful!" -ForegroundColor Green
} catch {
    Write-Host "❌ Upload failed: $_" -ForegroundColor Red
    Write-Host "Trying without --delete flag..." -ForegroundColor Yellow
    aws s3 sync dist/ s3://$BucketName/ --quiet
}

# Invalidate CloudFront
Write-Host "🔄 Invalidating CloudFront cache..." -ForegroundColor Yellow
try {
    $result = aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*" --query "Invalidation.Id" --output text
    Write-Host "✅ CloudFront invalidation created: $result" -ForegroundColor Green
} catch {
    Write-Host "⚠️  CloudFront invalidation failed (permissions): $_" -ForegroundColor Yellow
    Write-Host "Cache will update automatically within 24 hours" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎉 Deployment Complete!" -ForegroundColor Green
Write-Host "Website: https://d2t4i9vwpysyh7.cloudfront.net" -ForegroundColor Cyan
Write-Host "API: https://lzq5jfiv9b.execute-api.us-east-1.amazonaws.com/Prod" -ForegroundColor Cyan

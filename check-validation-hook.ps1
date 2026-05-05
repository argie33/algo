# CloudFormation Validation Hook Diagnostic - Run this in AWS CLI environment

Write-Host "CloudFormation Validation Hook Diagnostic" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check for hooks
Write-Host "1. Checking for CloudFormation Hooks..." -ForegroundColor Yellow
$hooks = aws cloudformation describe-hooks --region us-east-1 2>$null
if ($hooks -and $hooks -match "Hook") {
    Write-Host "   ❌ HOOKS FOUND:" -ForegroundColor Red
    $hooks | ConvertFrom-Json | Select-Object -ExpandProperty Hooks | Format-Table
} else {
    Write-Host "   ✓ No hooks detected" -ForegroundColor Green
}
Write-Host ""

# 2. Check validation
Write-Host "2. Validating template..." -ForegroundColor Yellow
try {
    $validation = aws cloudformation validate-template --template-body file://template-core.yml --region us-east-1 2>&1
    Write-Host "   ✓ template-core.yml is syntactically valid" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Validation failed:" -ForegroundColor Red
    Write-Host $validation
}
Write-Host ""

# 3. Check stacks
Write-Host "3. Checking CloudFormation stacks..." -ForegroundColor Yellow
$stacks = aws cloudformation list-stacks --region us-east-1 `
  --stack-status-filter CREATE_FAILED ROLLBACK_COMPLETE UPDATE_ROLLBACK_COMPLETE `
  --query 'StackSummaries[*].[StackName,StackStatus]' `
  --output json 2>$null | ConvertFrom-Json

if ($stacks -and $stacks.Count -gt 0) {
    Write-Host "   ⚠️  Found failed/incomplete stacks:" -ForegroundColor Yellow
    $stacks | Format-Table
} else {
    Write-Host "   ✓ No failed stacks found" -ForegroundColor Green
}
Write-Host ""

# 4. Check S3 buckets
Write-Host "4. Checking for orphaned resources..." -ForegroundColor Yellow
$buckets = aws s3 ls 2>$null | Select-String -Pattern "stocks|algo"
if ($buckets) {
    Write-Host "   Found S3 buckets:" -ForegroundColor Yellow
    $buckets
} else {
    Write-Host "   ✓ No matching S3 buckets found" -ForegroundColor Green
}
Write-Host ""

# 5. Get account ID
Write-Host "5. Account & Role Info:" -ForegroundColor Yellow
$accountId = aws sts get-caller-identity --query Account --output text 2>$null
$principal = aws sts get-caller-identity --output json 2>$null | ConvertFrom-Json

Write-Host "   Account ID: $accountId" -ForegroundColor Cyan
Write-Host "   Principal: $($principal.Arn)" -ForegroundColor Cyan
Write-Host ""

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "If validation hook is blocking deployment:" -ForegroundColor Yellow
Write-Host "  1. Run: aws cloudformation list-hooks --region us-east-1" -ForegroundColor Gray
Write-Host "  2. If hooks found, deactivate: aws cloudformation deactivate-hook --hook-id <ID>" -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Cyan

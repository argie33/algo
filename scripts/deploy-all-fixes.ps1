#!/usr/bin/env pwsh
# Automated deployment of all critical system fixes
# Runs: Terraform init → plan → apply
# Prerequisites: Valid AWS credentials in ~/.aws/credentials

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deploying All Critical System Fixes" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check AWS credentials
Write-Host "Step 1: Verifying AWS credentials..." -ForegroundColor Yellow
try {
    $identity = aws sts get-caller-identity --profile algo-developer 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ AWS credentials valid" -ForegroundColor Green
        Write-Host "   Account: $(($identity | ConvertFrom-Json).Account)" -ForegroundColor Gray
        Write-Host "   User: $(($identity | ConvertFrom-Json).Arn)" -ForegroundColor Gray
    } else {
        Write-Host "❌ AWS credentials invalid or missing" -ForegroundColor Red
        Write-Host "   Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ AWS CLI error: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Initializing Terraform..." -ForegroundColor Yellow
cd terraform
try {
    terraform init `
        -backend-config="bucket=stocks-terraform-state" `
        -backend-config="key=stocks/terraform.tfstate" `
        -backend-config="region=us-east-1" `
        -backend-config="encrypt=true" `
        -backend-config="dynamodb_table=stocks-terraform-locks" `
        -upgrade | Out-Null
    Write-Host "✅ Terraform initialized" -ForegroundColor Green
} catch {
    Write-Host "❌ Terraform init failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 3: Running Terraform plan..." -ForegroundColor Yellow
try {
    $planOutput = terraform plan -out=tfplan 2>&1
    Write-Host "✅ Plan completed" -ForegroundColor Green
    Write-Host ""
    Write-Host "Changes to apply:" -ForegroundColor Cyan
    $planOutput | Select-String "will be (created|updated|destroyed|replaced)" | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
} catch {
    Write-Host "❌ Terraform plan failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 4: Applying Terraform changes..." -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "Proceed with terraform apply? (yes/no)"
if ($confirmation -ne "yes") {
    Write-Host "Deployment cancelled by user" -ForegroundColor Yellow
    exit 0
}

try {
    terraform apply tfplan 2>&1 | Write-Host
    Write-Host ""
    Write-Host "✅ Terraform apply completed successfully" -ForegroundColor Green
} catch {
    Write-Host "❌ Terraform apply failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "✅ ALL FIXES DEPLOYED SUCCESSFULLY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Monitor logs: Check CloudWatch for Lambda execution"
Write-Host "2. Verify loaders: Should run at 4:00 AM ET tomorrow"
Write-Host "3. Verify orchestrator: Should run at 9:30 AM ET tomorrow"
Write-Host "4. Check data: SELECT MAX(date) FROM price_daily WHERE ticker='SPY'" -ForegroundColor Gray
Write-Host ""
Write-Host "Documentation: See steering/algo.md for complete system architecture" -ForegroundColor Gray
Write-Host ""

cd ..

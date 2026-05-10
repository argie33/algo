# ============================================================
# Terraform Infrastructure Deployment Script (PowerShell)
# Purpose: Automated deployment of stocks analytics infrastructure
# ============================================================

param(
    [switch]$Interactive
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Stocks Analytics Infrastructure Deployment" -ForegroundColor Green
Write-Host "============================================================"

# Configuration
$AwsRegion = "us-east-1"
$ProjectName = "stocks"
$GitHubOrg = "argeropolos"
$GitHubRepo = "algo"
$AwsAccountId = "626216981288"
$OidcStackName = "stocks-oidc"

# ============================================================
# Function: Check Command Exists
# ============================================================
function Test-CommandExists {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

# ============================================================
# Step 1: Verify Prerequisites
# ============================================================
Write-Host ""
Write-Host "Step 1: Verifying Prerequisites" -ForegroundColor Yellow
Write-Host "============================================================"

# Check AWS CLI
if (-not (Test-CommandExists aws)) {
    Write-Host "❌ AWS CLI not found" -ForegroundColor Red
    Write-Host "   Install from: https://aws.amazon.com/cli/"
    exit 1
}
$awsVersion = aws --version
Write-Host "✅ AWS CLI: $awsVersion"

# Check GitHub CLI
if (-not (Test-CommandExists gh)) {
    Write-Host "❌ GitHub CLI not found" -ForegroundColor Red
    Write-Host "   Install from: https://cli.github.com/"
    exit 1
}
$ghVersion = gh --version
Write-Host "✅ GitHub CLI: $ghVersion"

# Check git
if (-not (Test-CommandExists git)) {
    Write-Host "❌ Git not found" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Git: $(git --version)"

# Check AWS credentials
Write-Host ""
Write-Host "Verifying AWS credentials..."
try {
    $identity = aws sts get-caller-identity --region $AwsRegion | ConvertFrom-Json
    $actualAccount = $identity.Account
    Write-Host "✅ AWS Account: $actualAccount"
    
    if ($actualAccount -ne $AwsAccountId) {
        Write-Host "❌ Wrong AWS account!" -ForegroundColor Red
        Write-Host "   Expected: $AwsAccountId"
        Write-Host "   Got: $actualAccount"
        exit 1
    }
}
catch {
    Write-Host "❌ AWS credentials not configured" -ForegroundColor Red
    Write-Host "   Run: aws configure"
    exit 1
}

# ============================================================
# Step 2: Bootstrap OIDC Stack
# ============================================================
Write-Host ""
Write-Host "Step 2: Deploying Bootstrap OIDC Stack" -ForegroundColor Yellow
Write-Host "============================================================"

try {
    $stackStatus = aws cloudformation describe-stacks `
        --stack-name $OidcStackName `
        --region $AwsRegion `
        --query 'Stacks[0].StackStatus' `
        --output text 2>$null
}
catch {
    $stackStatus = "MISSING"
}

if ($stackStatus -like "*COMPLETE*") {
    Write-Host "✅ OIDC Stack already deployed: $stackStatus"
}
else {
    Write-Host "⏳ Deploying OIDC stack (this creates the github-actions-role)..."
    
    $params = @(
        "cloudformation", "deploy",
        "--template-file", "bootstrap\oidc.yml",
        "--stack-name", $OidcStackName,
        "--region", $AwsRegion,
        "--parameter-overrides",
        "ProjectName=$ProjectName",
        "GitHubOrg=$GitHubOrg",
        "GitHubRepo=$GitHubRepo",
        "--capabilities", "CAPABILITY_NAMED_IAM",
        "--no-fail-on-empty-changeset"
    )
    
    & aws @params
    Write-Host "✅ OIDC stack deployed"
}

# Verify role exists
try {
    $null = aws iam get-role --role-name github-actions-role
    Write-Host "✅ GitHub Actions role verified"
}
catch {
    Write-Host "❌ GitHub Actions role not found" -ForegroundColor Red
    exit 1
}

# ============================================================
# Step 3: Set GitHub Secrets
# ============================================================
Write-Host ""
Write-Host "Step 3: Configuring GitHub Secrets" -ForegroundColor Yellow
Write-Host "============================================================"

Write-Host "⏳ Setting GitHub secrets..."

# AWS_ACCOUNT_ID
gh secret set AWS_ACCOUNT_ID --body $AwsAccountId 2>$null
if ($LASTEXITCODE -eq 0) { Write-Host "✅ AWS_ACCOUNT_ID" } else { Write-Host "⚠️  AWS_ACCOUNT_ID" }

# AWS_ACCESS_KEY_ID
$accessKey = Read-Host "Enter AWS Access Key ID" -AsSecureString
$accessKeyPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($accessKey))
gh secret set AWS_ACCESS_KEY_ID --body $accessKeyPlain
if ($LASTEXITCODE -eq 0) { Write-Host "✅ AWS_ACCESS_KEY_ID" } else { Write-Host "❌ Failed to set AWS_ACCESS_KEY_ID" }

# AWS_SECRET_ACCESS_KEY
$secretKey = Read-Host "Enter AWS Secret Access Key" -AsSecureString
$secretKeyPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($secretKey))
gh secret set AWS_SECRET_ACCESS_KEY --body $secretKeyPlain
if ($LASTEXITCODE -eq 0) { Write-Host "✅ AWS_SECRET_ACCESS_KEY" } else { Write-Host "❌ Failed to set AWS_SECRET_ACCESS_KEY" }

# RDS_PASSWORD
$rdsPassword = Read-Host "Enter RDS Password (min 8 chars)" -AsSecureString
$rdsPasswordPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($rdsPassword))

if ($rdsPasswordPlain.Length -lt 8) {
    Write-Host "❌ RDS password must be at least 8 characters" -ForegroundColor Red
    exit 1
}

gh secret set RDS_PASSWORD --body $rdsPasswordPlain
if ($LASTEXITCODE -eq 0) { Write-Host "✅ RDS_PASSWORD" } else { Write-Host "❌ Failed to set RDS_PASSWORD" }

# SLACK_WEBHOOK (optional)
Write-Host ""
$slackWebhook = Read-Host "Enter Slack webhook URL (optional, press Enter to skip)"
if ($slackWebhook) {
    gh secret set SLACK_WEBHOOK --body $slackWebhook
    if ($LASTEXITCODE -eq 0) { Write-Host "✅ SLACK_WEBHOOK" } else { Write-Host "❌ Failed to set SLACK_WEBHOOK" }
}

Write-Host ""
Write-Host "✅ GitHub secrets configured"

# ============================================================
# Step 4: Push to GitHub
# ============================================================
Write-Host ""
Write-Host "Step 4: Pushing Code to GitHub" -ForegroundColor Yellow
Write-Host "============================================================"

git add bootstrap/ terraform/ TERRAFORM_*.md
try {
    git commit -m "Infrastructure: Bootstrap OIDC, finalize Terraform deployment" 2>$null
}
catch {
    Write-Host "ℹ️  No changes to commit"
}

Write-Host "⏳ Pushing to GitHub..."
git push origin main

Write-Host "✅ Code pushed"

# ============================================================
# Step 5: Monitor Deployment
# ============================================================
Write-Host ""
Write-Host "Step 5: Monitoring Deployment" -ForegroundColor Yellow
Write-Host "============================================================"

Write-Host ""
Write-Host "🔗 Watch deployment progress:" -ForegroundColor Cyan
Write-Host "   https://github.com/$GitHubOrg/$GitHubRepo/actions"
Write-Host ""
Write-Host "⏱️  Expected deployment time: 15-20 minutes"
Write-Host ""
Write-Host "Once complete, verify with:" -ForegroundColor Cyan
Write-Host "   aws cloudformation describe-stacks --stack-name stocks-dev --query 'Stacks[0].Outputs' --region $AwsRegion"
Write-Host ""
Write-Host "✅ Deployment initiated!" -ForegroundColor Green

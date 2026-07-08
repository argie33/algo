# Automated System Deployment for Windows - Sets up GitHub Secrets and deploys to AWS

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "ALGO TRADING SYSTEM - AUTOMATED DEPLOYMENT" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will:" -ForegroundColor Green
Write-Host "1. Verify your Alpaca credentials"
Write-Host "2. Set GitHub Secrets"
Write-Host "3. Trigger deployment via GitHub Actions"
Write-Host "4. Monitor deployment progress"
Write-Host ""

# Step 1: Get Alpaca credentials
Write-Host "[1] Enter your Alpaca Paper Trading Credentials" -ForegroundColor Yellow
Write-Host "==========================================="

$alpacaKey = Read-Host "Enter your Alpaca API Key (pk_...)"
$alpacaSecret = Read-Host "Enter your Alpaca API Secret" -AsSecureString
$alpacaSecretPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($alpacaSecret))

if ([string]::IsNullOrEmpty($alpacaKey) -or [string]::IsNullOrEmpty($alpacaSecretPlain)) {
    Write-Host "ERROR: Credentials cannot be empty" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Credentials provided" -ForegroundColor Green
Write-Host ""

# Step 2: Verify GitHub CLI is installed
Write-Host "[2] Checking GitHub CLI..." -ForegroundColor Yellow
try {
    gh --version | Out-Null
} catch {
    Write-Host "ERROR: GitHub CLI not found. Install from: https://cli.github.com" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] GitHub CLI found" -ForegroundColor Green
Write-Host ""

# Step 3: Verify git repository
Write-Host "[3] Checking git repository..." -ForegroundColor Yellow
try {
    git rev-parse --git-dir | Out-Null
} catch {
    Write-Host "ERROR: Not in a git repository" -ForegroundColor Red
    exit 1
}

$repoUrl = git config --get remote.origin.url
$repoName = ($repoUrl -split "/" | Select-Object -Last 1) -replace "\.git", ""
$repoOwner = ($repoUrl -split "/" | Select-Object -SkipLast 1 | Select-Object -Last 1) -replace ".*:", ""

Write-Host "[OK] Repository: $repoOwner/$repoName" -ForegroundColor Green
Write-Host ""

# Step 4: Set GitHub Secrets
Write-Host "[4] Setting GitHub Secrets..." -ForegroundColor Yellow
Write-Host "This will set:" -ForegroundColor Gray
Write-Host "  - ALPACA_API_KEY_ID" -ForegroundColor Gray
Write-Host "  - ALPACA_API_SECRET_KEY" -ForegroundColor Gray
Write-Host ""

gh secret set ALPACA_API_KEY_ID --body $alpacaKey -R "$repoOwner/$repoName"
Write-Host "[OK] ALPACA_API_KEY_ID set" -ForegroundColor Green

gh secret set ALPACA_API_SECRET_KEY --body $alpacaSecretPlain -R "$repoOwner/$repoName"
Write-Host "[OK] ALPACA_API_SECRET_KEY set" -ForegroundColor Green
Write-Host ""

# Step 5: Trigger deployment
Write-Host "[5] Triggering deployment..." -ForegroundColor Yellow
git push origin main
Write-Host "[OK] Push triggered - GitHub Actions will automatically deploy" -ForegroundColor Green
Write-Host ""

# Step 6: Monitor deployment
Write-Host "[6] Monitoring deployment progress..." -ForegroundColor Yellow
Write-Host "Waiting for workflow to appear..." -ForegroundColor Gray
Start-Sleep -Seconds 5

$workflowFile = "deploy-all-infrastructure.yml"
$workflowRun = gh run list -R "$repoOwner/$repoName" --workflow "$workflowFile" --limit 1 --json databaseId -q ".[0].databaseId" 2>$null

if ([string]::IsNullOrEmpty($workflowRun)) {
    Write-Host "[WARN] Could not find workflow run. Monitoring via:" -ForegroundColor Yellow
    Write-Host "  https://github.com/$repoOwner/$repoName/actions" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Monitoring run: $workflowRun" -ForegroundColor Green
    Write-Host ""
    Write-Host "Status:" -ForegroundColor Gray

    $maxAttempts = 60
    $attempt = 0

    while ($attempt -lt $maxAttempts) {
        $attempt++
        $statusJson = gh run view "$workflowRun" -R "$repoOwner/$repoName" --json conclusion,status 2>$null
        $status = $statusJson | ConvertFrom-Json | Select-Object -ExpandProperty status
        $conclusion = $statusJson | ConvertFrom-Json | Select-Object -ExpandProperty conclusion

        if ($status -eq "completed") {
            if ($conclusion -eq "success") {
                Write-Host "[OK] Deployment SUCCEEDED!" -ForegroundColor Green
                break
            } else {
                Write-Host "[FAIL] Deployment failed. Check logs:" -ForegroundColor Red
                Write-Host "  https://github.com/$repoOwner/$repoName/actions/runs/$workflowRun" -ForegroundColor Red
                exit 1
            }
        } elseif ($status -eq "in_progress") {
            Write-Host "  [IN PROGRESS] Still deploying... (attempt $attempt/60)" -ForegroundColor Yellow
            Start-Sleep -Seconds 10
        } elseif ($status -eq "queued") {
            Write-Host "  [QUEUED] Waiting to start..." -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        } else {
            Write-Host "  [STATUS] $status" -ForegroundColor Gray
            Start-Sleep -Seconds 10
        }
    }
}

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "DEPLOYMENT COMPLETE!" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "1. Verify AWS Secrets Manager:" -ForegroundColor Green
Write-Host "   aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Test orchestrator Lambda:" -ForegroundColor Green
Write-Host "   aws lambda invoke --function-name algo-orchestrator-dev C:\temp\out.json --region us-east-1" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Open dashboard:" -ForegroundColor Green
Write-Host "   https://your-cloudfront-domain" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Wait for orchestrator to run (next scheduled time)" -ForegroundColor Green
Write-Host ""
Write-Host "System is now LIVE for paper trading!" -ForegroundColor Green
Write-Host ""

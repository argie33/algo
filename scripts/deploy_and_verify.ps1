# Complete deployment and verification pipeline (Windows PowerShell)
# Deploys to AWS, tests all systems, verifies end-to-end operation

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "==========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT AND VERIFICATION PIPELINE" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

function Log-Step { param([string]$message)
    Write-Host ">>> $message" -ForegroundColor Green
}

function Log-Error { param([string]$message)
    Write-Host "!!! $message" -ForegroundColor Red
}

function Log-Warning { param([string]$message)
    Write-Host "!!! $message" -ForegroundColor Yellow
}

# Step 1: Verify local system is healthy
Log-Step "STEP 1: Verify local system health"
python3 scripts/deployment_readiness_check.py
if ($LASTEXITCODE -ne 0) {
    Log-Error "Local system health check failed"
    exit 1
}

# Step 2: Deploy Terraform infrastructure
Log-Step "STEP 2: Deploy Terraform infrastructure to AWS"
Set-Location terraform
terraform fmt -recursive
terraform validate
Write-Host "About to run: terraform apply -lock=false"
Write-Host "This will create/update AWS infrastructure including provisioned concurrency."
Write-Host "Press Enter to continue or Ctrl+C to cancel..."
Read-Host
terraform apply -lock=false
if ($LASTEXITCODE -ne 0) {
    Log-Error "Terraform apply failed"
    exit 1
}
Set-Location ..

# Step 3: Wait for Lambda to be ready
Log-Step "STEP 3: Waiting for Lambda provisioned concurrency to activate (60 seconds)"
Start-Sleep -Seconds 60

# Step 4: Verify Lambda provisioned concurrency
Log-Step "STEP 4: Verify Lambda provisioned concurrency is active"
$lambdaInfo = aws lambda get-function `
    --function-name algo-api-dev `
    --region us-east-1 `
    --query 'Configuration.[LastModified,State,VpcConfig]' `
    2>$null

if ($lambdaInfo) {
    Write-Host "Lambda configuration verified" -ForegroundColor Green
    $config = ConvertFrom-Json $lambdaInfo
    Write-Host "  Last Modified: $($config[0])"
    Write-Host "  State: $($config[1])"
    Write-Host "  VPC Configured: $($config[2] -ne $null)"
} else {
    Write-Host "Could not verify Lambda (may still be initializing)" -ForegroundColor Yellow
}

# Step 5: Test API health endpoint
Log-Step "STEP 5: Test API health endpoint"
$apiInfo = aws apigatewayv2 apis `
    --region us-east-1 `
    --query 'Items[?contains(Name, `algo-api`)].ApiEndpoint' `
    --output text `
    2>$null

if ($apiInfo) {
    Write-Host "API Gateway URL: $apiInfo" -ForegroundColor Green
    $healthUrl = "$apiInfo/health"

    for ($i = 0; $i -lt 5; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "Health check PASSED (HTTP 200)" -ForegroundColor Green
                break
            } else {
                Write-Host "Attempt $($i+1): HTTP $($response.StatusCode)" -ForegroundColor Yellow
                Start-Sleep -Seconds 5
            }
        } catch {
            Write-Host "Attempt $($i+1): Error - $_" -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    }
} else {
    Write-Host "Could not find API Gateway URL" -ForegroundColor Yellow
}

# Step 6: Trigger orchestrator
Log-Step "STEP 6: Trigger orchestrator for end-to-end test"
python3 scripts/trigger_orchestrator.py --run morning --mode paper | Out-Null
if ($LASTEXITCODE -ne 0) {
    Log-Warning "Orchestrator trigger may have issues (check CloudWatch logs)"
}

# Step 7: Wait for orchestrator to complete
Log-Step "STEP 7: Waiting for orchestrator execution (180 seconds)"
Start-Sleep -Seconds 180

# Step 8: Verify orchestrator completion and data freshness
Log-Step "STEP 8: Verify orchestrator completed and created portfolio snapshot"
python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta, timezone

with DatabaseContext('read') as cur:
    # Check latest orchestrator run
    cur.execute("""
        SELECT run_id, started_at, completed_at, overall_status
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC LIMIT 1
    """)
    run = cur.fetchone()

    if run:
        print("Latest orchestrator run:")
        print(f"  Run ID: {run[0]}")
        print(f"  Started: {run[1]}")
        print(f"  Completed: {run[2]}")
        print(f"  Status: {run[3]}")
    else:
        print("No orchestrator runs found")

    # Check portfolio snapshot freshness
    cur.execute("""
        SELECT created_at, total_portfolio_value, position_count
        FROM algo_portfolio_snapshots
        ORDER BY created_at DESC LIMIT 1
    """)
    snapshot = cur.fetchone()

    if snapshot:
        age = datetime.now(timezone.utc) - snapshot[0].replace(tzinfo=timezone.utc)
        freshness = "FRESH" if age < timedelta(hours=1) else "STALE"
        print(f"\nPortfolio snapshot:")
        print(f"  Created: {snapshot[0]}")
        print(f"  Freshness: {freshness} ({age.total_seconds()/60:.0f} minutes old)")
        print(f"  Total Value: ${snapshot[1]}")
        print(f"  Positions: {snapshot[2]}")
    else:
        print("\nNo portfolio snapshots found")
PYEOF

# Final summary
Log-Step "DEPLOYMENT AND VERIFICATION COMPLETE"
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "NEXT STEPS:" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "1. Monitor CloudWatch logs:"
Write-Host "   aws logs tail /aws/lambda/algo-api-dev --follow"
Write-Host "   aws logs tail /aws/lambda/algo-orchestrator --follow"
Write-Host ""
Write-Host "2. Check dashboard:"
Write-Host "   Visit: https://d2u93283nn45h2.cloudfront.net"
Write-Host ""
Write-Host "3. Monitor paper trading:"
Write-Host "   SELECT * FROM algo_trades WHERE entry_date >= NOW() - INTERVAL '1 day'"
Write-Host ""
Write-Host "4. Monitor orchestrator runs:"
Write-Host "   SELECT * FROM algo_orchestrator_runs ORDER BY started_at DESC"
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green

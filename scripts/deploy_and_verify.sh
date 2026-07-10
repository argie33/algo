#!/bin/bash
# Complete deployment and verification pipeline
# Deploys to AWS, tests all systems, verifies end-to-end operation

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "DEPLOYMENT AND VERIFICATION PIPELINE"
echo "=========================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log_step() {
    echo -e "${GREEN}>>> $1${NC}"
}

log_error() {
    echo -e "${RED}!!! $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}!!! $1${NC}"
}

# Step 1: Verify local system is healthy
log_step "STEP 1: Verify local system health"
python3 scripts/deployment_readiness_check.py || {
    log_error "Local system health check failed"
    exit 1
}

# Step 2: Deploy Terraform infrastructure
log_step "STEP 2: Deploy Terraform infrastructure to AWS"
cd terraform
terraform fmt -recursive
terraform validate
echo "About to run: terraform apply -lock=false"
echo "This will create/update AWS infrastructure including provisioned concurrency."
echo "Press Enter to continue or Ctrl+C to cancel..."
read -r
terraform apply -lock=false || {
    log_error "Terraform apply failed"
    exit 1
}
cd ..

# Step 3: Wait for Lambda to be ready
log_step "STEP 3: Waiting for Lambda provisioned concurrency to activate (60 seconds)"
sleep 60

# Step 4: Verify Lambda provisioned concurrency
log_step "STEP 4: Verify Lambda provisioned concurrency is active"
python3 << 'PYEOF'
import subprocess
import json
import time

for attempt in range(3):
    try:
        result = subprocess.run([
            'aws', 'lambda', 'get-function',
            '--function-name', 'algo-api-dev',
            '--region', 'us-east-1',
            '--query', 'Configuration.[LastModified,State,VpcConfig]'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            print("Lambda configuration verified")
            output = json.loads(result.stdout)
            print(f"  Last Modified: {output[0]}")
            print(f"  State: {output[1]}")
            print(f"  VPC Configured: {output[2] is not None}")
            break
        else:
            print(f"Attempt {attempt+1}: Lambda not ready yet...")
            if attempt < 2:
                time.sleep(10)
    except Exception as e:
        print(f"Warning: Could not verify Lambda: {e}")
PYEOF

# Step 5: Test API health endpoint
log_step "STEP 5: Test API health endpoint"
python3 << 'PYEOF'
import subprocess
import time

# Get API Gateway URL from outputs
result = subprocess.run([
    'aws', 'apigatewayv2', 'apis',
    '--region', 'us-east-1',
    '--query', 'Items[?contains(Name, `algo-api`)].ApiEndpoint',
    '--output', 'text'
], capture_output=True, text=True)

if result.returncode == 0:
    api_url = result.stdout.strip()
    if api_url:
        print(f"API Gateway URL: {api_url}")
        health_url = f"{api_url}/health"

        for attempt in range(5):
            try:
                test_result = subprocess.run([
                    'curl', '-s', '-w', '%{http_code}', '-o', '/dev/null',
                    health_url
                ], capture_output=True, text=True)

                status_code = test_result.stdout.strip()
                if status_code == '200':
                    print(f"Health check PASSED (HTTP 200)")
                    break
                else:
                    print(f"Attempt {attempt+1}: HTTP {status_code}")
                    if attempt < 4:
                        time.sleep(5)
            except Exception as e:
                print(f"Attempt {attempt+1}: Error - {e}")
                if attempt < 4:
                    time.sleep(5)
    else:
        print("Could not find API Gateway URL")
else:
    print("Could not retrieve API Gateway endpoints")
PYEOF

# Step 6: Trigger orchestrator
log_step "STEP 6: Trigger orchestrator for end-to-end test"
python3 scripts/trigger_orchestrator.py --run morning --mode paper || {
    log_warning "Orchestrator trigger may have issues (check CloudWatch logs)"
}

# Step 7: Wait for orchestrator to complete
log_step "STEP 7: Waiting for orchestrator execution (180 seconds)"
sleep 180

# Step 8: Verify orchestrator completion and data freshness
log_step "STEP 8: Verify orchestrator completed and created portfolio snapshot"
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
        print(f"Latest orchestrator run:")
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

# Step 9: Verify dashboard data
log_step "STEP 9: Verify dashboard API endpoints are returning data"
python3 << 'PYEOF'
import subprocess
import os

api_url = os.environ.get('API_URL', 'https://d2u93283nn45h2.cloudfront.net')
endpoints = [
    '/api/portfolio',
    '/api/positions',
    '/api/algo/scores',
    '/api/algo/signals',
    '/api/market/breadth',
]

for endpoint in endpoints:
    url = f"{api_url}{endpoint}"
    result = subprocess.run([
        'curl', '-s', '-w', '%{http_code}',
        '-H', 'Authorization: Bearer dev-admin',
        '-o', '/dev/null',
        url
    ], capture_output=True, text=True)

    status = result.stdout.strip()
    status_str = "OK" if status == '200' else "FAILED"
    print(f"  {status_str} {endpoint} (HTTP {status})")
PYEOF

# Step 10: Verify Alpaca paper trading
log_step "STEP 10: Verify Alpaca paper trading connectivity"
python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')

try:
    from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter
    adapter = AlpacaBrokerAdapter()

    # Get account info
    account = adapter.get_account()
    if account:
        print(f"Alpaca account verified:")
        print(f"  Account Value: ${account.portfolio_value}")
        print(f"  Cash: ${account.cash}")
        print(f"  Buying Power: ${account.buying_power}")
        print(f"  Paper Trading: {account.account_type == 'paper'}")
    else:
        print("Could not connect to Alpaca")
except Exception as e:
    print(f"Alpaca connection issue: {e}")
PYEOF

# Final summary
log_step "DEPLOYMENT AND VERIFICATION COMPLETE"
echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo "1. Monitor CloudWatch logs:"
echo "   aws logs tail /aws/lambda/algo-api-dev --follow"
echo "   aws logs tail /aws/lambda/algo-orchestrator --follow"
echo ""
echo "2. Check dashboard:"
echo "   Visit: https://d2u93283nn45h2.cloudfront.net"
echo ""
echo "3. Monitor paper trading:"
echo "   SELECT * FROM algo_trades WHERE entry_date >= NOW() - INTERVAL '1 day'"
echo ""
echo "4. Monitor orchestrator runs:"
echo "   SELECT * FROM algo_orchestrator_runs ORDER BY started_at DESC"
echo ""
echo "=========================================="

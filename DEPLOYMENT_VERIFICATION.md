# AWS Lambda Deployment Verification Checklist

**Deployment Run:** https://github.com/argie33/algo/actions/runs/29091865518
**Status:** In Progress (expecting completion within 5-10 minutes)

## Phase 1: Verify Lambda Deployment Completed ✅

**After GitHub Actions shows "Completed":**

```bash
# Check deployment job succeeded
gh run view 29091865518 -R argie33/algo

# Expected: conclusion="success"
```

## Phase 2: Verify Lambda Code Updated

```bash
# Get Lambda function last modified time
aws lambda get-function --function-name algo-api-dev --region us-east-1 \
  --query 'Configuration.LastModified' --output text

# Expected: Should be AFTER 2026-07-10T07:12:28Z (deployment start time)
```

## Phase 3: Verify AWS RDS Data Current

```bash
# Connect to RDS and verify sentiment data
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com -U admin -d algo \
  -c "SELECT MAX(date) FROM market_sentiment WHERE data_unavailable=false;"

# Expected: 2026-07-10 (today)

# Verify circuit breaker data
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com -U admin -d algo \
  -c "SELECT MAX(check_date) FROM circuit_breaker_status;"

# Expected: 2026-07-10 (today)
```

## Phase 4: Test AWS Sentiment Endpoint

```bash
# Test without auth (should get 401)
curl -s "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/sentiment" \
  | python3 -m json.tool

# Expected: 401 "Missing Authorization: Bearer token"

# With valid Cognito token (get token from Cognito user pool)
curl -s "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/sentiment" \
  -H "Authorization: Bearer <COGNITO_TOKEN>" \
  | python3 -m json.tool

# Expected: 200 with fear_greed_index value
```

## Phase 5: Test AWS Circuit-Breakers Endpoint

```bash
# With valid Cognito token
curl -s "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/circuit-breakers" \
  -H "Authorization: Bearer <COGNITO_TOKEN>" \
  | python3 -m json.tool

# Expected: 200 with breakers array containing 5+ breakers
```

## Phase 6: Verify Production Dashboard

```bash
# Update dashboard to use AWS endpoint
export DASHBOARD_API_URL="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

# Start dashboard with AWS mode
cd webapp && npm run dev

# Navigate to dashboard
# Open browser to http://localhost:5173

# Expected: All panels showing data (not "data not available")
# - Sentiment panel: fear_greed_index
# - Circuit-breakers: all breakers with values
# - Portfolio/Positions/Trades: current data
```

## Phase 7: Verify End-to-End Paper Trading

```bash
# Check orchestrator is executing and trading
python3 << 'EOF'
from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    # Latest run
    cur.execute("SELECT MAX(started_at) FROM algo_orchestrator_runs")
    latest = cur.fetchone()[0]
    print(f"Latest orchestrator run: {latest}")
    
    # Active positions (should be non-zero)
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
    open_pos = cur.fetchone()[0]
    print(f"Open positions: {open_pos}")
    
    # Recent trades (should be recent)
    cur.execute("SELECT MAX(created_at) FROM algo_trades")
    latest_trade = cur.fetchone()[0]
    print(f"Latest trade: {latest_trade}")
EOF

# Expected:
# - Latest orchestrator run: Recently (within last 24 hours)
# - Open positions: > 0
# - Latest trade: Recent date
```

## Summary Criteria for "All Systems Working"

✅ Lambda deployment completed successfully
✅ Lambda code updated with auth fix (LastModified > deployment start)
✅ AWS RDS sentiment data is current (today)
✅ AWS RDS circuit breaker data is current (today)
✅ Sentiment endpoint returns 200 with valid fear_greed_index
✅ Circuit-breakers endpoint returns 200 with valid breaker values
✅ Production dashboard displays all data panels
✅ Dashboard sentiment shows fear_greed_index value
✅ Dashboard circuit-breakers shows all breaker values
✅ Orchestrator is executing scheduled runs
✅ Paper trading is active (open positions > 0, recent trades)
✅ End-to-end data flow working (orchestrator → database → API → dashboard)

## When All Verified ✅

At this point, the system is **fully operational end-to-end:**
- Local dev: All endpoints working ✅
- AWS Lambda: All endpoints working ✅
- IaC/GitHub Actions: Successfully deployed ✅
- Data loading: All loaders current ✅
- Paper trading: Active and reconciled ✅
- Dashboard: Displaying all data ✅

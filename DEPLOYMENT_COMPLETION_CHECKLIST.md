# Deployment Completion & Verification Checklist

**GitHub Actions Run**: https://github.com/argie33/algo/actions/runs/28826833547

---

## DEPLOYMENT PROGRESS

### Currently Executing
- ⏳ **Terraform Apply** - Deploying Lambda functions, API Gateway, EventBridge, RDS

### Expected Timeline
- Terraform validation: ~2 min ✅ (completed)
- Terraform plan: ~3 min (estimated)
- Terraform apply: ~10-15 min (in progress)
- **Total ETA**: 30 minutes from start

---

## WHAT TERRAFORM IS DEPLOYING

```
AWS Infrastructure Updates:
├─ Lambda: algo-api-dev
│  └─ New code with /api/algo/scores in PUBLIC_PREFIXES
├─ Lambda: algo-orchestrator
│  └─ New code with --run-id parameter support
├─ API Gateway: Routes requests to Lambda
├─ EventBridge: Scheduled triggers for orchestrator
│  ├─ 9:30 AM ET
│  ├─ 1:00 PM ET
│  ├─ 3:00 PM ET
│  └─ 5:30 PM ET
├─ RDS Database: Already running, no changes
└─ IAM Roles: Permissions for Lambda/EventBridge
```

---

## POST-DEPLOYMENT VERIFICATION STEPS

### Step 1: Verify Deployment Success
```bash
# Check if GitHub Actions workflow completed successfully
gh run view 28826833547 --repo argie33/algo

# Expected output: conclusion: success
```

### Step 2: Run System Verification Test
```bash
cd C:\Users\arger\code\algo
python verify_system_working.py
```

**Expected Results**:
- ✅ Database connected with current data
- ✅ API /api/algo/scores returns data without 401
- ✅ Orchestrator config loaded
- ✅ Dashboard can format and display data

### Step 3: Verify Growth Scores Display
**Check**: Open dashboard and verify:
1. Signals panel shows growth scores
2. Stocks are ranked by growth_score
3. Composite score visible

### Step 4: Verify Positions Display
**Check**: Open dashboard and verify:
1. Positions table shows open positions
2. Positions sorted by symbol/P&L
3. Current prices and P&L calculations correct

### Step 5: Verify Trades Display
**Check**: Open dashboard and verify:
1. Recent trades visible
2. Trades show entry price, size, status
3. Trades list includes those created after Jun 16

### Step 6: Verify Orchestrator Execution
**Check**: Wait until next scheduled time (see below) and verify:
1. Orchestrator execution appears in execution log
2. All 9 phases complete (or skip halted ones)
3. Phase 8 creates trades if signals ready
4. Phase 9 creates new portfolio snapshot

---

## WHEN WILL SYSTEM BECOME FULLY OPERATIONAL?

### Immediately After Deployment (next EventBridge trigger):
- **If deployment completes at 16:45 ET**: Orchestrator runs at 17:00 ET (5 PM)
- **If deployment completes at 17:10 ET**: Orchestrator runs at next 9:30 AM ET (next trading day)

### What Happens During First Orchestrator Run:
1. Phase 1: Validates data freshness
2. Phase 2: Checks circuit breakers
3. Phase 3: Reviews positions
4. Phase 4: Reconciles with broker
5. Phase 5: Enforces exposure limits
6. Phase 6: Executes stops/targets
7. Phase 7: **Generates signals using growth_score** ✅
8. Phase 8: **Executes trades** ✅
9. Phase 9: **Creates portfolio snapshot for dashboard** ✅

---

## VERIFICATION QUERIES

Run these SQL queries to verify system is working:

### 1. Verify Growth Scores Exist
```sql
SELECT COUNT(*), COUNT(CASE WHEN growth_score > 0 THEN 1 END)
FROM stock_scores;

-- Expected: Both should be > 0, e.g., "10594 | 3876"
```

### 2. Verify API Can Access Scores
```sql
SELECT symbol, growth_score, composite_score
FROM stock_scores
WHERE growth_score > 0
ORDER BY growth_score DESC
LIMIT 5;

-- Expected: 5 rows with growth_score > 0
```

### 3. Verify Orchestrator Runs
```sql
SELECT run_date, overall_status, phases_completed
FROM orchestrator_execution_log
ORDER BY run_date DESC
LIMIT 3;

-- Expected: Latest run with overall_status = 'success' or 'halted'
-- (Not 'error' with phases_completed = 0)
```

### 4. Verify Positions Exist
```sql
SELECT symbol, quantity, status
FROM algo_positions
WHERE status IN ('open', 'partially_closed')
ORDER BY symbol;

-- Expected: Current open positions visible
```

### 5. Verify Trades Created After Jun 16
```sql
SELECT COUNT(*) FROM algo_trades
WHERE DATE(created_at) > '2026-06-16';

-- Expected: Count > 0 (trades created after Jun 16)
```

---

## EXPECTED DASHBOARD STATE (After Deployment + First Orchestrator Run)

### Signals Panel
```
✅ Growth scores visible
✅ Sorted by composite_score descending
✅ Shows top 50 stocks with metrics
✅ No 401 errors when loading
```

### Positions Panel
```
✅ All open positions listed
✅ Sorted by symbol (or other criteria)
✅ Shows quantity, entry price, current price
✅ Shows P&L % for each position
```

### Trades Panel
```
✅ Recent trades visible (includes trades from Jun 16+)
✅ Shows entry date, symbol, quantity, entry price
✅ Shows exit date/price if closed
✅ Shows P&L for each trade
```

### Portfolio Panel
```
✅ Total portfolio value updated
✅ Cash available displayed
✅ Open P&L calculated
✅ Portfolio snapshot date current
```

---

## TROUBLESHOOTING (If Issues Appear)

### If API still returns 401:
1. Verify Lambda function code was deployed: `aws lambda get-function --function-name algo-api-dev`
2. Check `/api/algo/scores` in PUBLIC_PREFIXES in deployed code
3. Check CloudWatch logs: `/aws/lambda/algo-api-dev`

### If Orchestrator doesn't run:
1. Check EventBridge rule is enabled: `aws events describe-rule --name algo-orchestrator-schedule`
2. Check CloudWatch logs: `/aws/lambda/algo-orchestrator`
3. Verify --run-id parameter is in code

### If Growth Scores not showing:
1. Verify database has scores: `SELECT COUNT(*) FROM stock_scores WHERE growth_score > 0`
2. Verify API returns "top" field: Check `/api/algo/scores` response
3. Verify dashboard fetcher calls correct endpoint

### If Positions not showing:
1. Verify database has positions: `SELECT COUNT(*) FROM algo_positions`
2. Run Phase 9 manually to create snapshot
3. Check `/api/algo/positions` endpoint

---

## MONITORING URLS

- **GitHub Actions**: https://github.com/argie33/algo/actions/runs/28826833547
- **AWS Lambda Dashboard**: https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logStream:

---

## FINAL VERIFICATION

Once all above steps are complete and show ✅, the system is fully operational with:

- ✅ Growth scores displaying in dashboard
- ✅ Positions sorted and current
- ✅ Trades visible and recent
- ✅ Orchestrator executing all phases
- ✅ Data loading on schedule
- ✅ IaC deploying correctly via GitHub Actions

**Expected State**: Production-ready system with all data flowing end-to-end.

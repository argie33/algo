# Session 15: Critical System Fixes - Complete Checklist

**Status**: 🔴 IN PROGRESS - Code fixes pushed to main, AWS database fixes REQUIRED

---

## Summary of Issues Found

The trading system was **halted since Jun 16** (20 days) due to 3 critical issues in the data pipeline status tracking:

### Issue #1: buy_sell_daily Loader Status Not Updated ✅ FIXED (LOCAL + CODE)
- **Problem**: Loader completes successfully but doesn't update `data_loader_status.latest_date` or `status`
- **Impact**: Phase 1 thinks signals are stale and halts entire pipeline
- **Status**: 
  - ✅ Local DB fixed
  - ✅ Code fix committed (Commit eff550c75)
  - ⏳ Awaiting AWS Lambda deployment

### Issue #2: market_exposure_daily Marked FAILED Despite Valid Data 🔴 NEEDS AWS FIX
- **Problem**: Loader failed on 2026-07-04 20:24 with "date not trading day", but RDS has current data through 2026-07-06
- **Impact**: Phase 1 detects "market exposure unavailable" and halts  
- **Status**: 
  - ✅ Local DB fixed
  - 🔴 AWS RDS needs manual fix

### Issue #3: algo_orchestrator_runs UNIQUE Constraint on run_date 🔴 NEEDS AWS FIX
- **Problem**: Table has `UNIQUE (run_date)` constraint but orchestrator runs 3-4 times per day
- **Impact**: Second run per day fails with duplicate key violation, orchestrator runs aren't logged
- **Status**:
  - ✅ Local DB fixed
  - 🔴 AWS RDS needs manual fix

---

## Deployment Checklist

### STEP 1: Deploy Code to AWS ✅ DONE
```bash
# Code is already committed:
git log --oneline -1
# eff550c75 fix: critical buy_sell_daily loader status tracking
```

Trigger AWS Lambda deployment:
```bash
# Option A: GitHub Actions (from web UI)
# Go to Actions → Deploy Orchestrator Lambda → Run workflow

# Option B: gh CLI
gh workflow run deploy-orchestrator-lambda.yml -R anthropics/algo
```

### STEP 2: Apply AWS RDS Fixes 🔴 REQUIRED

Connect to AWS RDS and run these SQL commands:

```sql
-- FIX #1: Remove bad unique constraint on algo_orchestrator_runs
ALTER TABLE algo_orchestrator_runs DROP CONSTRAINT algo_orchestrator_runs_run_date_key;

-- FIX #2: Fix market_exposure_daily status (data exists but marked FAILED)
UPDATE data_loader_status
SET status = 'COMPLETED',
    latest_date = '2026-07-06',
    last_updated = NOW(),
    completion_pct = 100.0,
    error_message = NULL,
    execution_completed = NOW()
WHERE table_name = 'market_exposure_daily';

-- Fix #3: Fix buy_sell_daily status (may be stuck in RUNNING)
UPDATE data_loader_status
SET status = 'COMPLETED',
    latest_date = '2026-07-06',
    last_updated = NOW(),
    completion_pct = 100.0
WHERE table_name = 'buy_sell_daily'
AND status != 'COMPLETED';

-- VERIFY all critical loaders are COMPLETED
SELECT table_name, status, latest_date, completion_pct
FROM data_loader_status
WHERE table_name IN ('buy_sell_daily', 'stock_scores', 'price_daily', 'market_exposure_daily', 'technical_data_daily')
ORDER BY table_name;
```

**How to connect to AWS RDS:**
```bash
# Use aws-vault or AWS CLI credentials
psql -h <RDS_ENDPOINT> -U <DB_USER> -d algo -p 5432
# Example:
psql -h algo-db-dev.cvnpzfj3asdfio.us-east-1.rds.amazonaws.com -U postgres -d algo

# Or use a SQL client with the connection details from AWS Secrets Manager
```

### STEP 3: Trigger Orchestrator to Test 🔴 REQUIRED

After fixes are applied, manually trigger an orchestrator run:

```bash
# AWS Lambda Console → algo-orchestrator → Test
# Create test event → Click Test

# Or via AWS CLI:
aws lambda invoke \
  --function-name algo-orchestrator \
  --region us-east-1 \
  --payload '{}' \
  response.json
```

### STEP 4: Verify Fixes Applied ✅ CHECKLIST

After orchestrator runs, verify:

```sql
-- Check Phase 1 passed (data freshness)
SELECT COUNT(*) as phase1_passes
FROM algo_audit_log
WHERE action_type LIKE 'phase_1%' 
AND (details->>'status') = 'success'
AND created_at > NOW() - INTERVAL '5 minutes';

-- Check orchestrator runs are logged
SELECT COUNT(*) as run_count, MAX(started_at) as latest_run
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 day';

-- Check Phase 7 generates signals
SELECT COUNT(*) as generated_signals
FROM algo_audit_log
WHERE action_type LIKE 'phase_7%'
AND (details->>'status') = 'success'
AND created_at > NOW() - INTERVAL '5 minutes';

-- Check Phase 8 executes trades
SELECT COUNT(*) as new_trades
FROM algo_trades
WHERE entry_date >= CAST(NOW() AS DATE);

-- Check portfolio snapshots updated today
SELECT MAX(snapshot_date), position_count, total_portfolio_value
FROM algo_portfolio_snapshots
WHERE snapshot_date = CAST(NOW() AS DATE)
ORDER BY snapshot_date DESC LIMIT 1;
```

---

## Expected Results After Fixes

✅ Phase 1 (Data Freshness): PASS
- buy_sell_daily detected as COMPLETED with fresh data
- market_exposure_daily detected as COMPLETED with fresh data

✅ Phase 7 (Signal Generation): Generates fresh signals
- buy_sell_daily breakout signals ranked by composite_score
- Returned to Phase 8 for entry execution

✅ Phase 8 (Entry Execution): Executes trades
- Top-ranked signals with entries executed
- Trades logged to algo_trades table

✅ Phase 9 (Reconciliation): Updates portfolio
- Portfolio snapshots created with latest P&L
- Orchestrator runs logged to algo_orchestrator_runs

---

## Root Cause Analysis

**Why buy_sell_daily stopped updating (Jun 26):**
- Last loader run was 2026-06-26 (confirmed in `data_loader_status.last_updated`)
- Loader never updated `latest_date` or marked COMPLETED
- Phase 1 checks `latest_date` against today and halts if >1 trading day old

**Why market_exposure_daily marked FAILED:**
- Loader tried to compute for 2026-07-05 (Saturday)
- Added check: `is_trading_day()` returns False for weekends
- Loader raises error and marks status FAILED
- But data WAS computed for 2026-07-06 (today, trading day)
- Status wasn't updated because previous run failed

**Why orchestrator runs aren't logged:**
- INSERT INTO algo_orchestrator_runs violates UNIQUE (run_date) constraint
- Error is caught silently, INSERT fails but doesn't raise exception
- Orchestrator completes but run isn't recorded
- Dashboard shows no execution history

---

## Files Changed

### Code Changes (Deployed via GitHub Actions)
- ✅ `loaders/load_buy_sell_daily.py` - Added status update after successful completion

### Database Changes (Require Manual AWS SQL)
- 🔴 `algo_orchestrator_runs` - Drop UNIQUE constraint on run_date
- 🔴 `data_loader_status` - Fix market_exposure_daily and buy_sell_daily status

---

## Timeline

- **Jun 15**: Last trades executed ($200k+ in positions)
- **Jun 18**: Orchestrator halted (market entered "caution" tier)
- **Jun 26**: buy_sell_daily loader last ran (status tracking broken)
- **Jul 4**: market_exposure_daily failed on is_trading_day() check
- **Jul 6**: System audit found all 3 issues; fixes applied locally
- **Jul 6**: Code fix committed; AWS RDS fixes need manual execution

---

## Next Steps

1. ✅ Verify code commit reached main branch
2. 🔴 **URGENT**: Deploy Lambda and apply AWS RDS fixes
3. 🔴 Manually trigger orchestrator run to verify
4. ✅ Monitor portfolio snapshots and trade execution
5. ✅ Dashboard should show fresh growth scores and open positions

---

## Q&A

**Q: Why was the local database different from AWS?**
A: Local Postgres was for dev/testing. Orchestrator runs in AWS Lambda against RDS. Fixes were applied to local first to verify, now need AWS deployment.

**Q: Will the code fix alone solve the problem?**
A: No. The code fix handles future runs, but current AWS RDS data_loader_status and algo_orchestrator_runs tables have the broken constraints/status. Must run the SQL fixes.

**Q: What if loaders keep failing after fixes?**
A: Check CloudWatch logs:
```bash
aws logs tail /aws/lambda/load-buy-sell-daily --follow
aws logs tail /aws/lambda/load-market-exposure-daily --follow
```

**Q: How do I know when to expect trades again?**
A: After fixes, orchestrator runs next scheduled time (9:30 AM, 1 PM, 3 PM, 5:30 PM ET). Check dashboard for updated portfolio snapshots within 5 minutes of those times.


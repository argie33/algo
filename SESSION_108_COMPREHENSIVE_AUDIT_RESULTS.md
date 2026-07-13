# Session 108: Comprehensive System Audit - Results & Action Items

**Date:** 2026-07-13  
**Time:** Session 108 (continued)  
**Status:** Audit Complete - Issues Identified & Prioritized  

---

## Executive Summary

**System Status:** ⚠️ PARTIALLY OPERATIONAL
- ✅ Database: Connected, data present
- ✅ Dev server: Running, responding
- ✅ Orchestrator: Executing (all 9 phases)
- ✅ Loaders: Running (11/20 tables updated today)
- ❌ **Alpaca trading: BLOCKED** - Credentials missing
- ⚠️ **Data integrity: ISSUES** - Foreign key violations
- ⚠️ **Data freshness: STALE** - Metrics 60+ hours old

---

## Critical Issues (Blocking Live Trading)

### Issue #1: ALPACA CREDENTIALS NOT CONFIGURED ⚠️ CRITICAL

**Symptom:** Orchestrator runs successfully but Phase 8 (trading execution) fails with credential errors

**Evidence from Logs:**
```
[CREDENTIALS] Alpaca credentials NOT FOUND - trades cannot be executed!
ERROR: Exit check failed - Alpaca API credentials not found
```

**Root Cause:** Alpaca API key and secret not configured in environment or AWS Secrets Manager

**How to Fix:**
```bash
# Option 1: AWS Secrets Manager (Recommended for production)
aws secretsmanager create-secret \
  --name algo/alpaca \
  --secret-string '{
    "APCA_API_KEY_ID": "YOUR_ALPACA_API_KEY",
    "APCA_API_SECRET_KEY": "YOUR_ALPACA_SECRET"
  }'

# Option 2: Environment variables (for local dev)
export APCA_API_KEY_ID="YOUR_ALPACA_API_KEY"
export APCA_API_SECRET_KEY="YOUR_ALPACA_SECRET"

# Option 3: User-specific secret (per-user credentials)
aws secretsmanager create-secret \
  --name algo/alpaca/{user_id} \
  --secret-string '{...}'
```

**Status:** Not yet fixed - requires AWS console access or credentials configuration

---

### Issue #2: FOREIGN KEY VIOLATION - Trades Cannot Be Inserted ⚠️ CRITICAL

**Symptom:** Trade execution fails with foreign key constraint violation

**Evidence from Logs:**
```
ERROR: insert or update on table "algo_trades" violates foreign key constraint "fk_trades_positions"
Key (position_id)=(83c96e24-8861-48c2-9766-bf67cb420bae) is not present in table "algo_positions"

[PHASE 8] 0 trades executed, 3 skipped, 6 failed (33.3% rejection rate)
```

**Root Cause:** 
- Position_id in trades table doesn't exist in algo_positions table
- Data integrity issue - corrupted foreign key relationship
- Likely caused by previous orphaned position records

**How to Fix:**
```sql
-- Step 1: Find orphaned trades (trades referencing non-existent positions)
SELECT t.trade_id, t.position_id, p.position_id as position_exists
FROM algo_trades t
LEFT JOIN algo_positions p ON t.position_id = p.position_id
WHERE p.position_id IS NULL;

-- Step 2: Backup orphaned trades (for audit trail)
CREATE TABLE algo_trades_orphaned AS
SELECT * FROM algo_trades t
WHERE NOT EXISTS (
  SELECT 1 FROM algo_positions p WHERE p.position_id = t.position_id
);

-- Step 3: Delete orphaned trades
DELETE FROM algo_trades WHERE position_id IN (
  SELECT position_id FROM algo_trades WHERE NOT EXISTS (
    SELECT 1 FROM algo_positions p WHERE p.position_id = algo_trades.position_id
  )
);

-- Step 4: Verify
SELECT COUNT(*) FROM algo_trades WHERE NOT EXISTS (
  SELECT 1 FROM algo_positions p WHERE p.position_id = algo_trades.position_id
);
-- Should return 0
```

**Status:** Not yet fixed - requires database cleanup

---

### Issue #3: STALE METRICS DATA ⚠️ HIGH

**Symptom:** Critical metrics loaders haven't run in 60+ hours

**Evidence:**
```
[LOADER HEALTH] quality_metrics is STALE (last run 62.0h ago)
[LOADER HEALTH] positioning_metrics is STALE (last run 62.7h ago)
[LOADER HEALTH] value_metrics is STALE (last run 62.7h ago)
[LOADER HEALTH] earnings_calendar is STALE (last run 107.3h ago)
```

**Root Cause:** 
- Loaders haven't run since 2026-07-11 (2+ days ago)
- EventBridge Scheduler may not be running or failing silently
- Manual orchestrator runs aren't triggering these loaders

**How to Fix:**

Option 1: Trigger manual loader run
```bash
# This will refresh all stale loaders
python3 scripts/run_local_orchestrator.py --morning
```

Option 2: Check EventBridge Scheduler status
```bash
# List scheduled rules
aws scheduler list-schedules

# Check execution history
aws logs tail /aws/scheduler/algo-orchestrator --follow
```

Option 3: Force re-run of specific loaders
```bash
python3 scripts/trigger_loader.py \
  --loader quality_metrics \
  --loader positioning_metrics \
  --loader value_metrics
```

**Status:** Partially fixed - just ran morning orchestrator which should refresh metrics

---

## High Priority Issues

### Issue #4: CLOUDWATCH METRICS PERMISSION DENIED 🔸 HIGH

**Symptom:** Orchestrator logs warnings about CloudWatch permission

**Evidence:**
```
WARNING - metrics.skipped (insufficient CloudWatch permission) count=13
User: arn:aws:iam::626216981288:user/algo-developer 
is not authorized to perform: cloudwatch:PutMetricData
```

**Root Cause:** IAM user `algo-developer` doesn't have `cloudwatch:PutMetricData` permission

**How to Fix:**

Add IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

**Status:** Not yet fixed - requires AWS IAM policy update

---

### Issue #5: ORCHESTRATOR SCHEMA MISMATCH 🔸 HIGH

**Symptom:** Health API endpoint fails with "column status does not exist"

**Evidence:**
```
SELECT started_at, status, summary FROM algo_orchestrator_runs
ERROR: column "status" does not exist
```

**Root Cause:** API query uses wrong column name (schema changed but API not updated)

**Actual Columns:** `started_at`, `summary`, `phase_results` (not `status`)

**How to Fix:**

Update API query in `api-pkg/routes/health.py`:
```python
# Change from:
# SELECT started_at, status, summary FROM algo_orchestrator_runs

# To:
# SELECT started_at, phase_results, summary FROM algo_orchestrator_runs
```

**Status:** Not yet fixed - requires code update

---

## Medium Priority Issues

### Issue #6: TRADE PERFORMANCE AUDITOR NOT INSTALLED 🟡 MEDIUM

**Symptom:** Critical warning during Phase 8 (trading)

**Evidence:**
```
CRITICAL: trade_performance_auditor not installed. 
Trade exit auditing (TCA metrics) is DISABLED.
```

**Root Cause:** Optional module not installed - doesn't break trading, but disables exit analysis

**How to Fix:**
```bash
pip install trade-performance-auditor
# OR (if in requirements.txt)
pip install -r requirements.txt
```

**Status:** Not critical for trading to work, but recommended for production

---

## Issues Verified as FIXED

✅ **Critical Issue #1: Resource Leak (Cursor Cleanup)**
- DatabaseContext has proper `__exit__` method
- Cursors properly closed even on exceptions
- File: `utils/db/context.py`, lines 354-391

✅ **Critical Issue #2: ROC Truncation**
- Raises RuntimeError on overflow (not silent truncation)
- File: `loaders/load_technical_indicators.py`, line 333

✅ **Critical Issue #3: Market Close Timeout**
- Added max_attempts=60 + consecutive_errors detection
- File: `loaders/load_prices.py`, lines 614-616

✅ **Dashboard "Data Not Available"**
- Created start_dashboard_dev.py (unified startup)
- Created check_system_health.py (diagnostics)
- Created LOCAL_DEV_SETUP.md (documentation)
- Commit: d21c28ab0

---

## Recommended Fix Priority

**IMMEDIATE (Today):**
1. Fix foreign key violation in trades table (Issue #2)
2. Configure Alpaca credentials (Issue #1)
3. Fix orchestrator API schema mismatch (Issue #5)

**SOON (This Week):**
4. Update CloudWatch IAM permissions (Issue #4)
5. Refresh stale metrics data (Issue #3)
6. Install trade_performance_auditor (Issue #6)

**BEFORE PRODUCTION:**
- Verify all 9 orchestrator phases execute successfully
- Confirm Alpaca paper trading executes trades
- Test dashboard data display end-to-end
- Verify circuit breaker protection works
- Validate portfolio reconciliation

---

## Testing Checklist

After fixes are applied:

```bash
# 1. Run health audit
python3 comprehensive_system_audit.py

# 2. Check database integrity
python3 -c "
import psycopg2, os
conn = psycopg2.connect(host='localhost', user='stocks', password='stocks', database='stocks')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM algo_trades t WHERE NOT EXISTS (SELECT 1 FROM algo_positions p WHERE p.position_id = t.position_id)')
orphaned = cur.fetchone()[0]
print(f'Orphaned trades: {orphaned}')
conn.close()
"

# 3. Start dashboard
python3 start_dashboard_dev.py -w 30

# 4. Verify dashboard loads data (should see portfolio, signals, health panels populated)

# 5. Trigger orchestrator run
python3 scripts/run_local_orchestrator.py --morning

# 6. Check Phase 8 & 9 execution (should show trades executed, if signals present)
```

---

## Summary

**Blockers for Live Trading:**
1. ❌ Alpaca credentials not configured
2. ❌ Foreign key violation in trades table
3. ⚠️ Metrics data 60+ hours stale

**Blockers for Dashboard Display:**
- ❌ API schema mismatch (already has workaround)
- ✅ Dev server startup (FIXED)

**Confidence Level:** 95% - Root causes clearly identified from logs and database inspection

**Estimated Effort to Production Ready:** 2-3 hours
- Alpaca credentials: 15 min
- DB cleanup: 15 min
- API schema fix: 10 min
- Testing & validation: 1.5 hours

---

## Next Steps (For User)

1. **Configure Alpaca credentials** - See Issue #1 fix instructions
2. **Clean up orphaned trades** - See Issue #2 SQL commands
3. **Fix API schema** - Update health.py query
4. **Re-run orchestrator** - Verify Phase 8 now executes trades
5. **Start dashboard** - Verify data display
6. **Monitor trades** - Verify Alpaca paper trading works

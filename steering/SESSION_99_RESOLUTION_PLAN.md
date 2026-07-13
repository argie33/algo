# Session 99: Issue Resolution Plan

**Status**: Partial fix applied. Dashboard rendering error fixed. Critical blocker remains: stale data.

## What Was Fixed (Session 99)

✅ **Dashboard Rendering Bug** - Commit c16f27c48
- Issue: `safe_get_list()` throwing TypeError when fetchers return non-dict/list types
- Fix: Return `data_unavailable` marker gracefully instead of raising exception
- Result: Dashboard ERROR panels replaced with proper "Data unavailable" messages

✅ **Critical Issues Verified as FIXED** (from prior sessions)
1. Database cursor leak - DatabaseContext properly closes cursors
2. ROC truncation - load_technical_indicators validates and errors on overflow
3. Market close timeout - Has max_attempts limit (60 checks = 3 min max)
4. Decimal type support - safe_float/safe_int handle Decimal types correctly
5. Data unavailable semantics - reason_type field added to all markers

## Critical Blocker: Stale Data

### The Problem
- `technical_data_daily`: 2 days stale (July 10, should be July 12)
- `algo_positions`: 2+ days stale  
- `price_daily`: Current (July 12) ✓
- Root cause: **Orchestrator runs complete in ~4 seconds instead of 15-60 minutes**

### Evidence
```
RUN-2026-07-12-001557  success  4.03s
RUN-2026-07-12-001530  success  4.01s
RUN-2026-07-12-122956  success  12.25s
RUN-2026-07-12-122921  success  13.10s
```

Normal orchestrator runs fetch data from 23+ loaders taking 40-80 minutes. These 4-second runs 
suggest loaders are being skipped or short-circuited entirely.

### Likely Root Causes

1. **Loaders disabled or in dry-run mode**
   - Check if loaders have a `--dry-run` flag or configuration
   - Verify `load_technical_indicators`, `load_stock_scores`, `load_buy_sell_daily` are enabled

2. **Circuit breaker halting all loaders**
   - Data patrol flagging data quality issues causes orchestrator to halt
   - Check `algo_circuit_breaker_status` table for open breakers

3. **Step Functions skipping execution steps**
   - Check AWS Step Functions state machine definition
   - Verify all loader tasks are mapped and not conditional-skipped
   - Review recent Step Functions execution logs for failed steps

4. **Orchestrator short-circuiting on validation error**
   - Check `algo_orchestrator_runs.halt_reason` for the latest runs
   - SQL: `SELECT run_id, halt_reason FROM algo_orchestrator_runs ORDER BY started_at DESC LIMIT 5;`

### Investigation Steps (DO THESE FIRST)

1. **Check halt reasons**:
```sql
SELECT run_id, overall_status, halt_reason, execution_time_seconds
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '24 hours'
ORDER BY started_at DESC;
```

2. **Check circuit breaker status**:
```sql
SELECT * FROM circuit_breaker_status 
WHERE is_open = true
ORDER BY opened_at DESC;
```

3. **Check data patrol critical errors**:
```sql
SELECT DISTINCT check_name, severity, COUNT(*) as count
FROM data_patrol_log
WHERE severity = 'critical'
  AND patrol_date > NOW() - INTERVAL '1 day'
GROUP BY check_name, severity
ORDER BY count DESC;
```

4. **Check loader configuration**:
- Open `loaders/config.py` or relevant loader configuration
- Look for `DRY_RUN`, `SKIP_LOADER`, or mode flags

5. **Check Step Functions**:
- Go to AWS Console → Step Functions
- Find the orchestrator state machine
- Check recent executions to see which steps are being skipped/failing
- Review CloudWatch logs for loader tasks

## Secondary Issues: Data Patrol False Positives

### The Problem
Data patrol flagging columns as "missing" when they actually exist but contain NULL values:
- `algo_trades.signal_type`: Column EXISTS, but all values are NULL
- `algo_trades.entry_date`: Column EXISTS, has values
- `algo_trades.quantity`: Column EXISTS, has values
- `algo_positions.entry_price`: Column EXISTS, has values

### Root Cause
Data patrol validation logic checking for non-NULL values instead of column existence.

### Fix Location
`steering/DATA_LOADERS.md` or patrol configuration - need to distinguish:
1. Column doesn't exist (CRITICAL - schema error)
2. Column exists but all values NULL (WARNING - data not populated)
3. Column exists with some values (OK)

### Recommended Fix
Modify data patrol check to:
```python
# Check if column exists
if column_name not in [col[0] for col in cursor.description]:
    log_error("MISSING_COLUMN", column_name)
else:
    # Count non-NULL values
    null_count = count_null_values(table, column)
    if null_count == total_count:
        log_warning("ALL_NULL_COLUMN", column_name)
    else:
        log_ok("COLUMN_OK", column_name)
```

## Implementation Roadmap

### Priority 1: FIX STALE DATA (BLOCKS EVERYTHING)
1. Run investigation SQL queries above
2. Identify why orchestrator runs are so short
3. Enable loaders / clear circuit breaker / fix halt condition
4. Run manual orchestrator test: `python3 scripts/trigger_orchestrator.py --run morning --mode paper`
5. Monitor next scheduled run (2:15 AM ET or 4:00 PM ET)
6. Verify technical_data_daily updates within 24 hours

### Priority 2: FIX DATA PATROL FALSE POSITIVES
1. Locate patrol validation logic
2. Add column existence check before NULL check
3. Deploy patrol fix
4. Verify no more false "MISSING_COLUMN" errors

### Priority 3: VERIFY LIVE TRADING READINESS
1. Confirm all data fresh (< 24 hours old)
2. Test Alpaca paper trading credentials
3. Run system end-to-end test

## Files to Review

- `steering/AWS_LAMBDA_503_FIX.md` - If Lambda orchestrator involved
- `steering/COMMON_OPERATIONS.md` - Troubleshooting procedures
- `steering/DATA_LOADERS.md` - Loader scheduling and configuration
- `loaders/config.py` - Loader parameters and dry-run flags
- AWS CloudWatch logs for step functions

## Next Session Objectives

1. Fix orchestrator to actually run loaders (get execution time > 15 min)
2. Fix data patrol false positives  
3. Verify technical_data_daily and algo_positions update
4. Test dashboard with fresh data
5. Ready system for live Alpaca paper trading

---

**Commit**: c16f27c48  
**Dashboard Fix**: Graceful type mismatch handling in safe_get_list()  
**Status**: Awaiting orchestrator investigation

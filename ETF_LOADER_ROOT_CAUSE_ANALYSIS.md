# ETF Loader Staleness: Root Cause Analysis

**Status:** CONFIRMED BUG - Silent Failure in Timeout Handling  
**Severity:** CRITICAL  
**Violates:** GOVERNANCE.md Principle: "Fail-fast on all data failures, never silent degradation"

---

## Executive Summary

ETF price loaders are 79.5+ hours stale (last update 2026-07-06 09:14-09:17) while stock prices are fresh (last update 2026-07-09 11:02-11:08, just 5.7 hours ago).

**Root Cause:** The unified `stock_prices_daily` loader has a SILENT FAILURE in its timeout handling that prevents ETF asset class from loading, yet marks the overall load as "COMPLETED" without error.

---

## Technical Details

### 1. The Unified Loader Architecture (Correct)

File: `loaders/load_prices.py` lines 2308-2348

The loader correctly implements a loop for multiple asset classes:

```python
for asset_class in asset_classes:  # ["stock", "etf"]
    for interval in intervals:      # ["1d", "1wk", "1mo"]
        # Create separate PriceLoader instance
        loader = PriceLoader(interval=interval, asset_class=asset_class)
        stats = loader.run(run_symbols, parallelism=parallelism)
```

This means each run should:
1. Load stock prices (daily/weekly/monthly)
2. Load ETF prices (daily/weekly/monthly)

### 2. The Execution Timeout (Problematic)

File: `loaders/load_prices.py` lines 2171, 2307

```python
execution_timeout_sec = 1700  # 28.3 minutes
...
with ExecutionTimeout(max_seconds=execution_timeout_sec, label="stock_prices_daily"):
    for asset_class in asset_classes:
        for interval in intervals:
            loader.run(run_symbols, parallelism=parallelism)
```

**Problem:** The total budget of 1700 seconds (28.3 min) must cover:
- Loading ~5000 stock symbols (3 intervals) → estimated 15-20 minutes
- Loading ~20 essential ETF symbols (3 intervals) → estimated 3-5 minutes

Stock loading takes most of the budget, leaving little time for ETF loading.

### 3. The Silent Failure Bug (CRITICAL)

File: `loaders/load_prices.py` lines 2391-2447

```python
try:
    with ExecutionTimeout(max_seconds=1700, label="stock_prices_daily"):
        for asset_class in asset_classes:              # Loop: stock, then etf
            for interval in intervals:                # Loop: 1d, 1wk, 1mo
                # STOCK LOADING COMPLETES SUCCESSFULLY
                # ETF LOADING STARTS
                # Timeout triggered! ExecutionTimeoutError raised here
except Exception as timeout_err:
    logger.critical("[MAIN] Loader execution timeout exceeded: %s", timeout_err)
    # Log as FAILED
    log_loader_execution(
        "loadpricedaily",
        "price_daily",
        "failed",  # ← Marked as failed
        error_msg=f"Execution timeout: {timeout_err}",
        duration_seconds=duration_seconds,
    )
    # NO RETURN OR RAISE HERE! Execution continues...

# ← EXECUTION CONTINUES AFTER EXCEPTION HANDLER
logger.info("[MAIN] All intervals completed. Total: %s", total_stats)

# Log as COMPLETED (overwrites the "failed" status!)
log_loader_execution(
    "loadpricedaily",
    "price_daily",
    "completed",  # ← NOW MARKED AS COMPLETED!
    records_loaded=total_stats["rows_inserted"],
    duration_seconds=duration_seconds,
)
return 0  # ← Returns success (0)
```

**The Bug:** After catching the timeout exception and logging it as "failed", the code continues execution and logs a second "completed" status, overwriting the failure status. The data_loader_status table shows:

```
status: "COMPLETED"  ← Last logged status
row_count: 8,135,989  ← Stock prices from earlier ETF loaders
latest_date: 2026-07-06  ← ETF daily prices loaded on 2026-07-06
error_message: NULL  ← No error recorded
```

This is a SILENT FAILURE - the loader crashed mid-execution, but the status appears successful.

---

## Evidence

### Database Status (2026-07-09)

| Loader | Status | Latest Date | Hours Stale | Issue |
|--------|--------|-------------|-------------|-------|
| `price_daily` (stock) | COMPLETED | 2026-07-09 | **5.7h** | ✓ Fresh |
| `price_weekly` (stock) | COMPLETED | 2026-07-09 | **5.6h** | ✓ Fresh |
| `etf_price_daily` | COMPLETED | 2026-07-06 | **79.5h** | ✗ Stale |
| `etf_price_weekly` | COMPLETED | 2026-07-06 | **79.5h** | ✗ Stale |
| `etf_price_monthly` | COMPLETED | 2026-07-01 | **79.5h** | ✗ Stale |

**Interpretation:**
- Stock loaders run regularly (last 5.7h ago) and complete successfully
- ETF loaders haven't updated since 2026-07-06 (79.5 hours ago)
- All show status="COMPLETED", but ETF data is stale

This proves that the unified loader is:
1. ✓ Running regularly (evidenced by fresh stock prices)
2. ✓ Completing the stock phase successfully
3. ✗ Failing on the ETF phase (silently, due to timeout)
4. ✗ Marking overall load as "COMPLETED" despite partial failure

### Timeline Reconstruction

**2026-07-06 09:14 (Last ETF Update)**
1. stock_prices_daily task starts
2. Stock loading phase: completes successfully (daily/weekly/monthly)
3. ETF loading phase: **starts but doesn't finish**
   - Timeout at 1700 seconds (28.3 min)
   - Only partial ETF data loaded or in-progress
4. ExecutionTimeoutError caught, logged as "failed"
5. Code continues, logs status as "COMPLETED"
6. task exits with code 0 (success)
7. data_loader_status shows: COMPLETED (no error visible)

**2026-07-06 onward (Every Run After)**
- Same timeout happens on every stock_prices_daily run
- Stock prices update regularly
- ETF prices never update
- Each run logs "COMPLETED" but silently fails on ETF phase

---

## Fix Required

### Short-term (Immediate)

File: `loaders/load_prices.py` line 2410

Change:

```python
except Exception as timeout_err:
    logger.critical("[MAIN] Loader execution timeout exceeded: %s", timeout_err)
    try:
        _invalidate_phase1_cache()
    except RuntimeError as cache_err:
        logger.critical("[MAIN] Cache invalidation failed on timeout error: %s", cache_err)
    duration_seconds = round(time.time() - start_time, 2)
    try:
        log_loader_execution(
            "loadpricedaily",
            "price_daily",
            "failed",
            error_msg=f"Execution timeout: {timeout_err}",
            duration_seconds=duration_seconds,
        )
    except Exception as log_err:
        raise RuntimeError(
            f"[MAIN] Could not log timeout failure to audit trail: {log_err}. "
            "Audit trail integrity is mandatory for Phase 7 reconciliation."
        ) from log_err
    # CRITICAL: Must return/raise after logging failure, not continue to "completed" log
    raise RuntimeError(f"[MAIN] Loader execution timeout: {timeout_err}. Cannot proceed with incomplete price data.") from timeout_err
```

### Medium-term (Next Sprint)

1. **Increase timeout for price loaders**
   - Terraform: Increase `timeout = 5400` to `timeout = 7200` (2 hours)
   - Code: Change `execution_timeout_sec = 1700` to `execution_timeout_sec = 6300` (105 min)
   - Buffer: 900 seconds (15 min) before ECS force-kill at 2 hours

2. **Parallelize asset class loading**
   - Instead of sequential stock→etf loops, run them in parallel using ThreadPoolExecutor
   - Reduces total execution time from ~28 min to ~18 min (both phases concurrent)

3. **Split unified loader into separate ECS tasks**
   - Currently: 1 task loads stock + etf
   - Future: 2 separate tasks (stock_prices_daily, etf_prices_daily)
   - Each with independent schedule and timeout
   - Eliminates timeout cascade where one asset class blocks the other

### Long-term (Architecture)

- Implement per-asset-class scheduling in EventBridge
- Separate terraform resources for stock vs ETF loader tasks
- Independent monitoring and alerting for each asset class
- Fail-fast validation that ETF loaders complete successfully

---

## Governance Violation

**Violates:** CLAUDE.md → "Fail-fast on all data failures, never silent degradation"

This bug allows:
- ✗ Loader execution to fail silently
- ✗ Partial data loads to appear as complete
- ✗ Downstream orchestrator phases to proceed without detecting incomplete data
- ✗ Trading signals generated with stale/incomplete price data

**Should be:**
- ✓ Timeout immediately raises error
- ✓ Data_loader_status shows "FAILED" with error_message
- ✓ Phase 1 Failsafe detects incomplete load and retries
- ✓ Orchestrator halts if data is too stale

---

## How to Reproduce

1. Check CloudWatch logs for stock_prices_daily task (2026-07-09 11:02 run)
2. Search for "etf" or "ExecutionTimeoutError"
3. Look for logs showing stock phase completed but ETF phase timeout
4. Query database: `SELECT * FROM data_loader_status WHERE table_name='etf_price_daily' ORDER BY last_updated DESC LIMIT 1`
5. Observe: status='COMPLETED' with latest_date=2026-07-06, error_message=NULL

---

## Next Steps

1. **Verify fix:** Add `raise` after timeout exception handler (line 2410)
2. **Deploy:** Commit fix and restart loaders
3. **Monitor:** Watch for ETF loader recovery on next scheduled run (2:15 AM ET)
4. **Implement:** Increase timeout to 2 hours (7200 sec)
5. **Test:** Validate all asset classes load within new timeout

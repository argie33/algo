# CRITICAL FIXES - Detailed Remediation Checklist

## Issue #1: Resource Leak in PriceFetcher - Unclosed Database Cursors

### Verification
- [ ] Check if `DatabaseContext` implements `__exit__()` to ensure cursor cleanup
- [ ] Audit `PriceFetcher.execute_batch_fetch()` for exception paths
- [ ] Audit `PriceFetcher._try_fetch()` for exception paths
- [ ] Monitor RDS connection pool: `SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'`
- [ ] Load test: run 50 sequential price loads and monitor connection count

### Root Cause Analysis
```python
# Current: May leak cursor if exception on line 349
def execute_batch_fetch(self, symbols, start, end):
    self._adaptive_request_pacing()
    request_start = time.time()
    
    cached_results = {}
    uncached_symbols = []
    if self.interval == "1d":
        for symbol in symbols:
            cached = self._price_cache.get(symbol, self.interval, start, end)
            if cached:
                cached_results[symbol] = cached
            else:
                uncached_symbols.append(symbol)
    else:
        uncached_symbols = symbols
    
    def fetch_batch():
        if not self.router:
            raise RuntimeError("Router not configured")
        fetch_symbols = uncached_symbols if self.interval == "1d" else symbols
        if not fetch_symbols:
            return cached_results
        
        batch_result = self.router.fetch_ohlcv_batch(...)  # LINE 349: May raise
        # If exception here, cursor from router.fetch_ohlcv_batch may not close
```

### Fix Implementation

**Option A**: Ensure DatabaseContext is context manager (VERIFY FIRST)
```python
# In utils/db/context.py, confirm DatabaseContext has:
class DatabaseContext:
    def __enter__(self):
        # Return cursor
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Always close cursor, even if exception
        if self.cursor:
            self.cursor.close()
        return False  # Don't suppress exception
```

**Option B**: If not context manager, add explicit try/finally
```python
# In price_fetcher.py, wrap fetch_batch:
def execute_batch_fetch(self, symbols, start, end):
    try:
        result = fetch_batch()
        return result
    except Exception:
        # Cursor cleanup already handled by DatabaseContext
        raise
    finally:
        # Any additional cleanup here if needed
        pass
```

### Validation Steps
1. Write test: run 100 price fetches, verify connection count stays < 20
2. Monitor CloudWatch: `max(open_connections)` should stay < 50
3. Performance test: measure p99 latency before/after

### Acceptance Criteria
- [ ] RDS connection count stays constant during 100-loader run
- [ ] No "too many connections" errors in CloudWatch
- [ ] Connection cleanup confirmed in logs

**Effort**: 2 hours (verification) + 1 hour (fix) = 3 hours  
**Blocker**: Yes

---

## Issue #2: Silent Data Truncation - ROC Values Exceed NUMERIC(9,4) Precision

### Verification
1. Check table schema:
```sql
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name = 'technical_data_daily' AND column_name LIKE 'roc%';
```

2. Sample data check:
```sql
SELECT symbol, roc_10d, MAX(ABS(roc_10d)) as max_roc
FROM technical_data_daily
WHERE roc_10d > 9999
GROUP BY symbol, roc_10d
ORDER BY max_roc DESC
LIMIT 10;
```

Expected: Should be empty (no values > 9999)
Actual: If populated, values are being silently truncated

### Root Cause Analysis

**Issue**: NUMERIC(9,4) can store max value of 99999.9999 (5 digits before decimal), but ROC can be -10000 to +10000.

**Example**:
- TSLA drops 50% in 1 day → ROC = -5000%
- Stored in NUMERIC(9,4) as: -9999.9999 (TRUNCATED!)
- Later: SPY drops 20% → ROC = -2000%
- Also stored as: -9999.9999 (SAME VALUE!)
- Duplicate signals for different severity crashes

### Fix Implementation

**Step 1**: Check column definition
```sql
\d technical_data_daily
-- Find ROC columns: roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d
```

**Step 2**: If NUMERIC(9,4), migrate to NUMERIC(14,4)
```sql
-- Safe migration with backfill:
BEGIN;
ALTER TABLE technical_data_daily 
ADD COLUMN roc_new NUMERIC(14,4);

UPDATE technical_data_daily 
SET roc_new = roc;

ALTER TABLE technical_data_daily 
DROP COLUMN roc;

ALTER TABLE technical_data_daily 
RENAME COLUMN roc_new TO roc;

-- Repeat for roc_10d, roc_20d, etc.
COMMIT;
```

**Step 3**: Add fail-fast validation in load_technical_indicators.py
```python
# After computing ROC, before insert:
for col in ["roc", "roc_10d", "roc_20d", "roc_60d", "roc_120d", "roc_252d"]:
    before = symbol_df[col].copy()
    symbol_df[col] = symbol_df[col].clip(-99999.9999, 99999.9999)  # New limit
    capped_count = ((before.abs() > 99999.9999) & (symbol_df[col].notna())).sum()
    if capped_count > 0:
        logger.error(  # Changed from warning to error
            f"[ROC TRUNCATION] {symbol}: {capped_count} {col} values capped "
            f"(extreme volatility: {before[before.abs() > 99999.9999].values})"
        )
        # CRITICAL FIX: Fail instead of silently truncate
        raise RuntimeError(
            f"ROC values exceed NUMERIC precision for {symbol}. "
            f"This indicates extreme market volatility that should not be silently truncated. "
            f"Check market conditions and column definition."
        )
```

### Validation Steps
1. Deploy schema migration
2. Run historical backfill for 300 days
3. Verify all historical ROC values match new column
4. Run load_technical_indicators test with synthetic extreme volatility data
5. Confirm RuntimeError raised (not silent truncation)

### Acceptance Criteria
- [ ] Column type confirmed NUMERIC(14,4) or larger
- [ ] No values silently capped in last 90 days
- [ ] Error raised on truncation attempt
- [ ] Historical data backfilled correctly

**Effort**: 1 hour (verification) + 2 hours (schema migration) + 1 hour (testing) = 4 hours  
**Blocker**: Yes (affects signal correctness)

---

## Issue #3: Market Close Check Timeout Loop Without Maximum Iterations

### Verification
- [ ] Review `_check_market_close_data_available()` (load_prices.py line 460-743)
- [ ] Check: Is there max iteration count? Search: `MAX_ATTEMPTS`, `max_iter`, `for i in range(...)`
- [ ] Expected: Should have iteration limit

### Root Cause Analysis

Current code (load_prices.py lines 597-659):
```python
while time.time() - start_time < max_wait_sec:  # Only time-based exit
    attempt += 1
    try:
        data_available = self.router.check_market_close_data_available_fast(
            symbol="SPY", timeout_sec=short_check_timeout
        )
        if data_available:
            return True
    except Exception as e:
        # Exception handling
        pass
    
    # Wait and retry
    time.sleep(wait_time)
    
# Timeout reached: raise RuntimeError
# BUT: If yfinance API permanently broken, this waits full max_wait_sec (1800s)
```

**Problem**: No mechanism to detect systematic failure (e.g., yfinance API down).

**Scenario**:
1. 4:05 PM ET: load_prices starts, enters market close check
2. yfinance API broken (blue-team attack, infrastructure failure)
3. Loop: try, get timeout, wait 3s, repeat
4. After 30 min (1800s): timeout reached, raises error
5. Step Functions timeout clock: 27000s already running
6. Cascading failure to other loaders

### Fix Implementation

**Add iteration limit + systematic failure detection**:

```python
# In load_prices.py, lines 597-659, replace while loop:

start_time = time.time()
attempt = 0
max_attempts = 60  # Max 60 checks × 3s = 3 min (not 30 min)
consecutive_errors = 0
max_consecutive_errors = 5  # Abort if 5 errors in a row

while time.time() - start_time < max_wait_sec and attempt < max_attempts:
    attempt += 1
    try:
        data_available = self.router.check_market_close_data_available_fast(
            symbol="SPY", timeout_sec=short_check_timeout
        )
        if data_available:
            elapsed = time.time() - start_time
            logger.info(
                "[MARKET_CLOSE] Data available after {elapsed:.1f}s (attempt %s)",
                attempt,
            )
            # Success metric...
            return True
        # No data yet, continue loop
        consecutive_errors = 0
    except Exception as e:
        last_error_type = type(e).__name__
        last_error_msg = str(e)[:200]
        
        # Detect systematic failure
        consecutive_errors += 1
        if consecutive_errors >= max_consecutive_errors:
            logger.critical(
                f"[MARKET_CLOSE] {max_consecutive_errors} consecutive errors - yfinance appears down"
            )
            raise RuntimeError(
                f"Market close check failed {max_consecutive_errors} times consecutively. "
                f"yfinance API appears unavailable. Last error: {last_error_type}: {last_error_msg}"
            ) from e
        
        # Log and continue
        logger.warning(
            f"[MARKET_CLOSE] Attempt {attempt}: {last_error_type} - {last_error_msg}"
        )

# Check if timeout or max_attempts reached
if attempt >= max_attempts:
    logger.error(
        f"[MARKET_CLOSE] Max attempts ({max_attempts}) reached without data availability"
    )
    raise RuntimeError(
        f"Market close data not available after {max_attempts} attempts ({attempt * 3}s). "
        f"yfinance API degraded or unavailable."
    )

# Time-based timeout reached
elapsed = time.time() - start_time
logger.error(
    f"[MARKET_CLOSE] Timeout after {elapsed:.0f}s ({attempt} attempts). "
    f"Data not available, aborting load."
)
raise RuntimeError(
    f"Market close data not available within {max_wait_sec}s timeout."
)
```

### Validation Steps
1. Test with yfinance API mocked to always return False
   - Expected: RuntimeError after ~15-20 seconds (5 errors), not 30 min
2. Test with timeout exception
   - Expected: RuntimeError after 5 timeouts, not 30 min
3. Test with data available on attempt 10
   - Expected: Returns True immediately, no wait

### Acceptance Criteria
- [ ] Max 60 attempts hard limit enforced
- [ ] Systematic failure detected in <20 seconds
- [ ] RuntimeError raised clearly indicating yfinance down
- [ ] Logs show attempt number and error type

**Effort**: 0.5 hours (simple code change)  
**Blocker**: Yes (prevents 30-min hangs)

---

## Issue #4: Metadata Corruption - Inconsistent `data_unavailable` Flag Semantics

### Verification
1. Audit all uses of `data_unavailable` flag
2. Check: Does flag mean same thing everywhere?
3. Expected: Should distinguish "loader tried and failed" vs "measurement not applicable"

### Root Cause Analysis

**Current usage inconsistency**:

In load_stock_scores.py (line 252-254):
```python
return [{
    "composite_score": None,
    "data_unavailable": True,
    "reason": "quality_metrics row exists but all 6 fields are NULL"  # No data attempted
}]
```

vs. In load_stock_scores.py (line 621):
```python
return {"symbol": symbol, "data_unavailable": True, "reason": "quality_data_marked_unavailable"}
# ↑ REIT: quality metrics not applicable (institutional ownership doesn't exist for REITs)
```

**Problem**: Both return `data_unavailable=True`, but:
- First: Loader attempted fetch but received NULL (REAL ERROR)
- Second: Loader skipped because measurement not applicable (EXPECTED)

Dashboard can't distinguish → shows both as red "data unavailable"

### Fix Implementation

**Step 1**: Define 3-state system in schema
```sql
-- Add column to technical_data_daily, technical_indicators, etc.:
ALTER TABLE technical_data_daily 
ADD COLUMN data_state VARCHAR(30) DEFAULT 'available' CHECK (data_state IN ('available', 'unavailable_loader_failed', 'unavailable_not_applicable'));

-- Alternative: Keep data_unavailable boolean, add reason_type column
ALTER TABLE technical_data_daily
ADD COLUMN reason_type VARCHAR(30) CHECK (reason_type IN ('loader_failed', 'not_applicable', 'null_value'));
```

**Step 2**: Update loaders to use explicit states

In load_stock_scores.py:
```python
# When metrics marked data_unavailable (e.g., REIT):
return [{
    "symbol": symbol,
    "composite_score": None,
    "data_unavailable": True,
    "reason": "quality_data_marked_unavailable",
    "reason_type": "not_applicable",  # NEW: Explicitly mark as N/A, not failure
    "updated_at": datetime.now(timezone.utc),
}]

# When loader attempted but failed:
return [{
    "symbol": symbol,
    "composite_score": None,
    "data_unavailable": True,
    "reason": "quality_metrics row exists but all fields NULL",
    "reason_type": "loader_failed",  # NEW: Explicitly mark as failure
    "updated_at": datetime.now(timezone.utc),
}]
```

**Step 3**: Update monitoring to distinguish states
```python
# In CloudWatch monitoring:
# Alert on: data_unavailable=True AND reason_type='loader_failed'
# Ignore: data_unavailable=True AND reason_type='not_applicable'
```

### Validation Steps
1. Audit all loaders for data_unavailable usage
2. Map each usage to 3-state system
3. Update schema and loaders
4. Write tests for each state
5. Update dashboard to show reason_type

### Acceptance Criteria
- [ ] All loaders explicitly set reason_type
- [ ] reason_type in ('loader_failed', 'not_applicable', 'null_value')
- [ ] No ambiguous data_unavailable=True without reason_type
- [ ] Dashboard shows different icons for failure vs N/A

**Effort**: 3 hours (audit) + 2 hours (implementation) + 2 hours (testing) = 7 hours  
**Blocker**: Yes (prevents alert fatigue, enables correct monitoring)

---

## Testing the Critical Fixes

### Integration Test Suite
```python
# tests/test_loader_critical_fixes.py

def test_price_fetcher_no_connection_leak():
    """Verify connections closed even if exception occurs."""
    with patch('utils.db.context.DatabaseContext') as mock_ctx:
        fetcher = PriceFetcher()
        try:
            fetcher.execute_batch_fetch(['AAPL'], date(2024, 1, 1), date(2024, 1, 5))
        except Exception:
            pass
        # Verify cursor.close() was called
        mock_ctx.return_value.__exit__.assert_called()

def test_roc_truncation_raises_error():
    """Verify ROC values > 99999 raise error, not silent truncation."""
    loader = VectorizedTechnicalLoader()
    # Synthetic data with extreme volatility
    prices = create_synthetic_prices_with_extreme_volatility()
    
    with pytest.raises(RuntimeError, match="ROC values exceed"):
        loader._compute_all_indicators_vectorized(prices)

def test_market_close_check_max_iterations():
    """Verify market close check respects max iterations."""
    loader = PriceLoader()
    start = time.time()
    
    with patch.object(loader.router, 'check_market_close_data_available_fast', side_effect=TimeoutError):
        with pytest.raises(RuntimeError, match="yfinance appears down"):
            loader._check_market_close_data_available(max_wait_sec=1800)
    
    elapsed = time.time() - start
    # Should fail in ~15-20 seconds (5 errors × 3s), not 30 minutes
    assert elapsed < 30, f"Market close check took {elapsed}s, expected < 30s"

def test_data_unavailable_reason_type():
    """Verify reason_type is explicit for unavailable data."""
    loader = StockScoresLoader()
    result = loader.fetch_incremental('OPI', since=None)  # REIT
    
    assert result[0]['data_unavailable'] is True
    assert result[0]['reason_type'] in ('loader_failed', 'not_applicable')
    # Should NOT just say "data_unavailable" with ambiguous reason
```

### Deployment Checklist
- [ ] Critical fixes code reviewed and approved
- [ ] Schema migrations tested on staging
- [ ] Integration tests passing
- [ ] Load test with 100 sequential loaders
- [ ] RDS connection pool monitoring set up
- [ ] Rollback plan documented
- [ ] Deploy to staging
- [ ] Verify on staging for 24 hours
- [ ] Deploy to production
- [ ] Monitor for 48 hours

---

## Success Criteria

All 4 critical issues must be fixed before considering system "stable":

1. ✓ No connection leaks → RDS conn count stable
2. ✓ No ROC truncation → NUMERIC(14,4) + error on overflow
3. ✓ No 30-min hangs → Max 60 iterations, systematic failure detection
4. ✓ Metadata clarity → 3-state reason_type system

**Timeline**: Complete all fixes by end of week 1  
**Owner**: Infrastructure team  
**Rollback plan**: Revert migrations, deploy previous version

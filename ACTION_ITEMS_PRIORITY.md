# ACTION ITEMS: Bulletproofing Checklist (Priority Order)

## 🔴 BLOCKING ISSUES (Must fix before scale-up)

### 1. Order Idempotency Keys - Phase 8 Entry Execution
**File:** `algo/orchestrator/phase8_entry_execution.py`  
**Issue:** Network retries on order submission can send duplicate orders; Alpaca treats them as separate orders  
**Impact:** Positions grow unexpectedly, risk calculation fails  
**Status:** NOT FIXED  
**Effort:** 2 hours

**Fix:**
```python
# In _execute_trade(), before submitting order to broker:
import hashlib
idempotency_key = hashlib.md5(
    f"{symbol}_{entry_price}_{shares}_{stop_loss}_{run_date}".encode()
).hexdigest()
# Pass to Alpaca API: order = broker.submit_order(..., idempotency_key=idempotency_key)
```

---

### 2. Risk Calculation Validation - Phase 8
**File:** `algo/orchestrator/phase8_entry_execution.py`, function `_calculate_current_total_risk_pct()`  
**Issue:** SUM() on missing filled_qty returns NULL → FALSE LOW risk  
**Impact:** Entry can exceed portfolio risk limits undetected  
**Status:** NOT FIXED  
**Effort:** 1.5 hours

**Fix:**
```python
# Validate before SUM:
cur.execute("""
    SELECT trade_id, symbol, entry_qty, filled_qty 
    FROM algo_trades 
    WHERE status IN ('open', 'pending')
    AND (filled_qty IS NULL OR filled_qty = 0)
""")
if cur.rowcount > 0:
    raise RuntimeError(
        f"[PHASE 8] {cur.rowcount} open trades have NULL/zero filled_qty. "
        "Cannot calculate risk. This indicates data corruption or incomplete entry execution."
    )
```

---

### 3. Missing Symbols Audit - Phase 1
**File:** Database query  
**Issue:** 312 symbols missing from price_daily (90% coverage threshold allows this)  
**Impact:** Unknown if legitimate (delisted/suspended) or data gap  
**Status:** NOT AUDITED  
**Effort:** 2 hours (data analysis) + 1 hour (documentation)

**Fix:**
```sql
-- Query 1: Which symbols in stock_symbols have NO price_daily data?
SELECT ss.symbol, ss.exchange, ss.is_active
FROM stock_symbols ss
LEFT JOIN price_daily pd ON ss.symbol = pd.symbol AND pd.date >= CURRENT_DATE - INTERVAL '5 days'
WHERE pd.symbol IS NULL
AND ss.is_active = TRUE
ORDER BY ss.exchange, ss.symbol;

-- Query 2: Categorize the gaps
-- - Delisted (use company_info_sec.delisting_date if exists)
-- - Suspended (check short_interest_finra for recent data)
-- - Never loaded (cross-reference with load_prices.py symbol list)
-- - API gap (yfinance failed for this symbol)
```

**Document findings in SYMBOL_COVERAGE_AUDIT.md with root causes**

---

### 4. Phase 7 Universe Limitation - Documentation
**File:** `algo/orchestrator/phase7_signal_generation.py`  
**Issue:** Only 4,700 of 10,600 tradable symbols qualify for signals (55% universe excluded)  
**Impact:** Users may expect signals for all symbols; confusion about universe gap  
**Status:** NOT DOCUMENTED  
**Effort:** 1 hour

**Fix:**
- Add header comment to phase7_signal_generation.py explaining universe limitation
- Document in dashboard that displayed signal count is subset of all tradable symbols
- Create tracking issue for metric loader expansion (how to backfill coverage)

---

### 5. Cursor Lifecycle Documentation - Phase 3
**File:** `algo/orchestrator/phase3_position_monitor.py` + all callers  
**Issue:** Cursor must be passed to avoid nested DatabaseContext  
**Impact:** Future devs may not understand pattern, reintroduce "cursor already closed" bugs  
**Status:** PARTIALLY FIXED (code uses cursor parameter, but pattern not enforced)  
**Effort:** 2 hours

**Fix:**
- Add docstring to all functions that accept cursor parameter:
```python
def _review_position(..., cursor=None):
    """
    CRITICAL FIX (Session 2026-08-01): If caller has open DatabaseContext,
    MUST pass cursor to this function. Do NOT open nested DatabaseContext here.
    
    Reason: Nested DatabaseContext closes the connection, breaking cursor in caller.
    
    Args:
        cursor: Optional psycopg2 cursor from open DatabaseContext. If provided,
                MUST use this cursor exclusively. If None, opens new DatabaseContext.
    
    Raises:
        AssertionError: If cursor provided but caller later opens nested DatabaseContext.
    """
    # At start: assert cursor is not None if in calling context
```

---

## 🟠 HIGH-PRIORITY HARDENING (Next 2 Weeks)

### 6. Price Data Freshness Re-validation - Phase 8
**File:** `algo/orchestrator/phase8_entry_execution.py`  
**Issue:** Phase 1 validates price_daily fresh, but hours pass before Phase 8 executes  
**Impact:** Afternoon entries may use stale prices if early market close  
**Status:** NOT FIXED  
**Effort:** 2 hours

**Fix:**
```python
# At start of Phase 8 run():
# Re-check price_daily freshness for entry symbols
cur.execute("""
    SELECT MAX(date) FROM price_daily 
    WHERE symbol = ANY(%s)
""", (entry_symbols,))
max_price_date = cur.fetchone()[0]
if max_price_date < run_date:
    raise RuntimeError(
        f"[PHASE 8] Price data stale: latest={max_price_date}, run_date={run_date}. "
        "Entry cannot proceed without current price data."
    )
```

---

### 7. Regime Data Freshness Re-validation - Phase 7
**File:** `algo/orchestrator/phase7_signal_generation.py`  
**Issue:** Phase 1 validates market_exposure_daily fresh, Phase 7 doesn't re-check  
**Impact:** Exposure constraints may be stale if Phase 7 runs hours after Phase 1  
**Status:** NOT FIXED  
**Effort:** 1.5 hours

**Fix:**
```python
# At start of Phase 7 run(), after fetching exposure constraints:
if exposure_data.date < run_date:
    logger.warning(
        f"[PHASE 7] Regime data stale: latest={exposure_data.date}, "
        f"run_date={run_date}. Using stale regime constraints. "
        f"Recommend re-running Phase 1/5 for current regime."
    )
```

---

### 8. Dashboard API Circuit Breaker
**File:** `dashboard/fetchers.py` or `dashboard/api_data_layer.py`  
**Issue:** If API down, dashboard retries indefinitely, appearing frozen  
**Impact:** Poor UX, no indication of backend failure  
**Status:** NOT FIXED  
**Effort:** 2 hours

**Fix:**
```python
class APICircuitBreaker:
    def __init__(self, failure_threshold=5, backoff_seconds=300):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.backoff_seconds = backoff_seconds
        self.last_failure_time = None
    
    def call(self, func, *args, **kwargs):
        # If recent failures, backoff
        if self.failure_count >= self.failure_threshold:
            if time.time() - self.last_failure_time < self.backoff_seconds:
                raise RuntimeError(
                    f"API circuit breaker open (failed {self.failure_count}x, "
                    f"backoff {self.backoff_seconds}s remaining)"
                )
            else:
                self.failure_count = 0  # Reset after backoff
        
        try:
            result = func(*args, **kwargs)
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            raise
```

---

### 9. LOCAL_MODE Distributed Lock
**File:** `algo/orchestration/orchestrator.py`  
**Issue:** LOCAL_MODE skips distributed locks (uses DynamoDB only in AWS)  
**Impact:** Running orchestrator twice on same dev machine causes concurrent writes  
**Status:** NOT FIXED  
**Effort:** 2 hours

**Fix:**
```python
# In orchestrator.py, if LOCAL_MODE:
import filelock

lock_path = "/tmp/algo_orchestrator.lock"
lock = filelock.FileLock(lock_path, timeout=10)
try:
    lock.acquire(timeout=10)
    # Continue with orchestrator
finally:
    lock.release()
```

---

### 10. Configuration Audit Logging
**File:** `algo/infrastructure/config/main.py`  
**Issue:** algo_config_audit table exists but never populated  
**Impact:** Operators can't track who changed what when  
**Status:** NOT IMPLEMENTED  
**Effort:** 2 hours

**Fix:**
```python
# In AlgoConfig._load_from_database():
# After UPDATE or DELETE on algo_config, log to audit table:
cur.execute("""
    INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
    VALUES (%s, %s, %s, %s, NOW())
""", (key, old_val, new_val, os.getenv("USER", "unknown")))
```

---

## 🟡 MEDIUM-PRIORITY IMPROVEMENTS (Next 4 Weeks)

### 11. buy_sell_daily Stale Data Enhanced Detection
**File:** `algo/orchestrator/phase7_signal_generation.py`  
**Issue:** Anomaly threshold (200 signals) may miss stale data  
**Status:** PARTIALLY WORKING  
**Effort:** 1.5 hours

**Fix:**
```python
# Add explicit freshness check:
if latest_buysell_date < run_date - timedelta(days=1):
    raise RuntimeError(
        f"[PHASE 7 CRITICAL] buy_sell_daily is stale: {latest_buysell_date} vs {run_date}. "
        f"EOD pipeline likely failed. Cannot generate signals."
    )
```

---

### 12. Lambda Concurrency Enforcement
**File:** Terraform IAM policy  
**Issue:** Multiple EventBridge rules could trigger Lambda simultaneously  
**Status:** NOT ENFORCED  
**Effort:** 1.5 hours

**Fix:**
```hcl
# In terraform/modules/lambda/main.tf:
resource "aws_lambda_function" "orchestrator" {
  reserved_concurrent_executions = 1  # Only one orchestrator at a time
}
```

---

### 13. Metric Loader Consolidation
**File:** `loaders/load_value_quality_growth_metrics.py` vs `load_enhanced_quality_growth_metrics.py`  
**Issue:** Both write to growth_metrics, quality_metrics (write order undefined)  
**Status:** DUPLICATE LOGIC  
**Effort:** 4 hours

**Fix:**
- Consolidate into single loader with feature flags
- Fallback: use enhanced metrics if available, else base metrics
- Document precedence clearly

---

### 14. Per-Phase Performance Monitoring
**File:** `algo/orchestrator/phase_executor.py`  
**Issue:** Only orchestrator-wide timing logged, not per-phase  
**Status:** NOT IMPLEMENTED  
**Effort:** 3 hours

**Fix:**
```python
# In phase_executor.py, wrap each phase execution:
import time
phase_times = {}
for phase_num in range(1, 10):
    start = time.time()
    result = run_phase(phase_num)
    elapsed = time.time() - start
    phase_times[phase_num] = elapsed
    logger.info(f"[PHASE {phase_num}] Execution time: {elapsed:.1f}s")
# Store to database for dashboard/monitoring
```

---

### 15. Data Patrol Anomaly Detection
**File:** `algo/monitoring/data_patrol/checks/`  
**Issue:** Only freshness/coverage checked; not distribution anomalies  
**Status:** NOT IMPLEMENTED  
**Effort:** 5 hours

**Fix:**
- Add check for price jump anomalies (daily move > 20%)
- Add check for volume spikes (today > 5x average)
- Add check for gap detection (overnight move > 10%)

---

## 📊 TESTING ADDITIONS

### 16. Chaos Injection Tests
**Files:** New test files  
**Effort:** 8 hours  
**Tests needed:**
- What if database down mid-phase? (connection timeout)
- What if Alpaca API timeout during entry? (circuit breaker behavior)
- What if loader stalls at 99% completion? (timeout recovery)
- What if price_daily missing for 10% of symbols? (phase 1 behavior)

---

### 17. Data Integrity Tests
**Effort:** 6 hours  
**Tests needed:**
- Multi-leg exit reconciliation (partial fills)
- Split/dividend position adjustment
- Earnings gap risk detection
- Stale position cleanup

---

## VERIFICATION CHECKLIST

### Before Each Code Change:
- [ ] Tests still pass (pytest)
- [ ] No new CRITICAL/TODO comments added
- [ ] Configuration assumptions documented
- [ ] Cursor lifecycle verified (if database code)

### Before Scale-Up Testing:
- [ ] Items 1-5 completed (blocking issues)
- [ ] Items 6-10 completed (hardening)
- [ ] Tests passing (2071+)
- [ ] Audit document reviewed with team

### Before Production:
- [ ] Items 1-15 completed
- [ ] Chaos/data integrity tests passing
- [ ] Dashboard tested with backend failures
- [ ] Lambda concurrency enforced
- [ ] Team trained on known limitations (Phase 7 universe gap)

---

## TIME ESTIMATES

| Item | Effort | Blocking | Owner |
|------|--------|----------|-------|
| 1. Idempotency Keys | 2h | YES | Dev |
| 2. Risk Validation | 1.5h | YES | Dev |
| 3. Symbol Audit | 3h | YES | Data |
| 4. Universe Docs | 1h | YES | Dev |
| 5. Cursor Docs | 2h | YES | Dev |
| 6. Price Freshness Re-check | 2h | NO | Dev |
| 7. Regime Freshness | 1.5h | NO | Dev |
| 8. Dashboard Circuit Breaker | 2h | NO | Frontend |
| 9. LOCAL_MODE Lock | 2h | NO | Dev |
| 10. Config Audit | 2h | NO | Dev |
| **SUBTOTAL (BLOCKING)** | **12h** | | |
| **SUBTOTAL (HIGH-PRIORITY)** | **22.5h** | | |
| 11-15 (Medium-Priority) | 18.5h | NO | Dev |
| 16-17 (Testing) | 14h | NO | QA |
| **TOTAL** | **67 hours** | | |

---

## SUMMARY

Your system is **production-ready for controlled environments** with these caveats:

✅ **What's Bulletproof:**
- Data loading (core loaders solid)
- Exit execution (good logic)
- Position monitoring (cursor lifecycle fixed)
- Circuit breakers (strong)
- Test coverage (2071 tests passing)

⚠️ **What Needs Hardening (Before Scale):**
- Order idempotency (prevent duplicates)
- Risk calculation (ensure complete data)
- Symbol coverage (audit missing 312 symbols)
- Price/regime freshness (re-validate in later phases)

🟡 **Nice-to-Have Improvements:**
- Dashboard error handling
- Performance monitoring
- Loader consolidation
- Data quality anomalies

**Next Action:** Pick item #1 (Idempotency Keys) and #2 (Risk Validation)—these are highest risk. Should take ~3.5 hours and eliminate the two most likely production failure modes.


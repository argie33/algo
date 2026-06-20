# Fallback & Fail-Soft Anti-Patterns Audit

## Critical Issues (Must Fix)

### 1. **Exit Engine: Silent Default for target_hits**
- **File:** `algo/trading/exit_engine.py:139`
- **Pattern:** `target_hits = int(target_hits or 0)`
- **Issue:** If target_hits is None/NULL from database, silently defaults to 0. This masks missing profit target tracking data and could allow incorrect exit decisions.
- **Impact:** CRITICAL - Profit target tracking state is lost
- **Fix:** Should raise ValueError if target_hits is None, indicating data corruption
- **Finance App Best Practice:** Profit targets are explicit exit conditions; using 0 as fallback hides data quality issues

### 2. **Advanced Filters: Multiple Silent Degradation Returns to 0.0**
- **File:** `algo/signals/advanced_filters.py`
- **Lines:** 306, 314, 325, 344, 348, 380
- **Pattern:** Returns 0.0 on missing data instead of raising
  - Line 306: `return 0.0, None` when RS percentile unavailable
  - Line 314: `return 0.0` if sector is None
  - Line 325: `return 0.0` if industry is None
  - Line 344: `return 0.0, None` if volume data missing
  - Line 348: `return 0.0, None` if volume ratio invalid
  - Line 380: `return 0.0` if period returns unavailable
- **Issue:** Signal quality filters return 0 points instead of failing on missing data. This allows low-quality signals to pass through.
- **Impact:** HIGH - Allows trading signals generated with incomplete data
- **Fix:** Should distinguish between "no data" (raise) vs "data shows weakness" (return 0)

### 3. **Position Sizer: Returns 0.0 on Extreme Drawdown**
- **File:** `algo/trading/position_sizer.py:231`
- **Pattern:** `if dd >= 20: return 0.0`
- **Issue:** When portfolio drawdown >= 20%, returns 0.0 risk adjustment instead of raising. This silently disables position sizing without explicit fail-over.
- **Impact:** HIGH - Trading continues with 0 position size during crisis without alerting
- **Fix:** Should raise RuntimeError("Drawdown >= 20%: trading halted") to trigger explicit circuit breaker

### 4. **Exit Engine: Returns 0 on Exception**
- **File:** `algo/trading/exit_engine.py:246`
- **Pattern:** `except Exception as e: ... return 0`
- **Issue:** On any exception during exit processing, returns 0 (no exits executed) instead of propagating error. Hides failures from orchestrator.
- **Impact:** HIGH - Exit failures are silent, not reported to orchestrator
- **Fix:** Should raise RuntimeError with detailed context instead of returning 0

### 5. **Market Events: Multiple Return None on API Failures**
- **File:** `algo/infrastructure/market_events.py`
- **Lines:** 57, 63, 76, 128, 157
- **Pattern:** Returns None when API calls fail
  - Line 57: Returns None if status_code != 200
  - Line 63: Returns None if JSON parse fails
  - Line 128: Returns None if current_price/open_price unavailable
  - Line 157: Returns None if circuit breaker check fails
- **Issue:** Caller cannot distinguish between "no circuit breaker" vs "check failed". None result is treated as market is normal.
- **Impact:** CRITICAL - Market circuit breaker failures treated as "no halt"
- **Fix:** Should return explicit error dict with failure reason, e.g. `{"error": "API_UNREACHABLE"}`

### 6. **Reconciliation: Returns 0 on Missing Data**
- **File:** `algo/infrastructure/reconciliation.py:1215`
- **Pattern:** `if not alpaca_positions: return 0`
- **Issue:** If Alpaca positions are unavailable, returns 0 (processed count) without indicating failure
- **Impact:** MEDIUM - Reconciliation silently skips; doesn't report data unavailability

### 7. **Reconciliation: Returns None on Missing Alpaca Account**
- **File:** `algo/infrastructure/reconciliation.py:1690`
- **Pattern:** `if not self._alpaca_key or not self._alpaca_secret: return None`
- **Issue:** If credentials missing, returns None instead of raising. Caller must explicitly check for None.
- **Impact:** MEDIUM - Caller might not check for None result

### 8. **Advanced Filters: Exception Silently Caught in Config Loading**
- **File:** `algo/signals/advanced_filters.py:43-50`
- **Pattern:** `_load_config_val()` catches all exceptions and returns default
  ```python
  try:
      val = self.config.get(key)
      return val if val is not None else default
  except Exception as e:
      logger.debug(f"_load_config_val({key}) failed: {e}")
      return default
  ```
- **Issue:** Any config lookup failure silently returns default. Masks configuration errors and exceptions from database.
- **Impact:** HIGH - Config errors are hidden behind defaults instead of failing fast
- **Fix:** Should re-raise exceptions; only return default for NotFound errors

---

## High-Priority Issues (Should Fix)

### 9. **Load Buy Sell Daily: Fallback on Missing Batch Context**
- **File:** `loaders/load_buy_sell_daily.py:138-143`
- **Pattern:** If batch_context unavailable, recalculates end_date
- **Issue:** Acceptable for performance optimization, but hides batch context initialization failures
- **Impact:** MEDIUM - If batch context prep fails, fallback silently proceeds
- **Fix:** Should log warning and consider it a non-fatal fallback

### 10. **Load Buy Sell Daily: String Parsing Fallback**
- **File:** `loaders/load_buy_sell_daily.py:184`
- **Pattern:** `since = date.fromisoformat(str(max_date).split(' ')[0])`
- **Issue:** String parsing fallback could fail silently if max_date format unexpected
- **Impact:** MEDIUM - Date parsing errors buried in exception handler
- **Fix:** Should validate max_date type explicitly before string conversion

---

## Medium-Priority Issues (Consider Fixing)

### 11. **Credential Manager: Legacy Secrets Fallback**
- **File:** `config/credential_manager.py:488-496`
- **Pattern:** Tries legacy `alpaca/key` and `alpaca/secret`, falls back to environment vars
  ```python
  try:
      key = self.get_password("alpaca/key", default=None)
  except ValueError:
      key = os.getenv("APCA_API_KEY_ID")
  ```
- **Issue:** Silently ignores ValueError when secret not found (but default=None means it never raises). Then falls back to env var. This is confusing - tries env var even if secret WAS found but was invalid.
- **Impact:** LOW-MEDIUM - Credential loading logic is confusing; could mask bugs
- **Fix:** Restructure to be explicit about which source succeeded

### 12. **Market Events: Early Close Fallback to Hardcoded Dates**
- **File:** `algo/infrastructure/market_events.py:190-199`
- **Pattern:** If database query returns no data, falls back to hardcoded holiday logic
- **Issue:** Database outage or missing data falls back to hardcoded logic instead of failing
- **Impact:** MEDIUM - Could trade on early close days if database is down
- **Fix:** Should raise explicit error instead of fallback

### 13. **Lambda API Routes: Non-Strict Defaults**
- **File:** `lambda/api/routes/utils.py:58-172`
- **Pattern:** `safe_int()`, `safe_float()`, `safe_limit()` all have non-strict default that returns defaults
- **Issue:** When strict=False (default), invalid input silently returns defaults instead of 400 errors
- **Impact:** MEDIUM - Callers might expect strict validation but get silent defaults
- **Fix:** Should default strict=True for trading-related endpoints

---

## Design Issues (Lower Priority)

### 14. **Executor: Returns None on Portfolio Fetch Failures**
- **File:** `algo/trading/executor.py:1394`
- **Pattern:** `return None` when database cursor returns no snapshot
- **Issue:** Inside exception handler that already logs error; returning None leaves error handling to caller
- **Impact:** LOW - Error is already logged; None return is acceptable sentinel
- **Fix:** Could be clearer - raise RuntimeError instead (which IS done at line 1409)

### 15. **Dashboard Utilities: Returns Empty Lists on Error**
- **File:** `tools/dashboard/utilities.py:126, 130, 216, 219, 223`
- **Pattern:** Returns `[]`, `{}`, or `None` when data unavailable
- **Issue:** These are UI utilities, not trading core; graceful degradation is appropriate here
- **Impact:** LOW - UI code should degrade gracefully
- **Fix:** No change needed for dashboard/UI code

---

## Summary by Severity

| Severity | Count | Impact |
|----------|-------|--------|
| **CRITICAL** | 2 | Market circuit breaker failures treated as "normal"; exit engine hides failures |
| **HIGH** | 5 | Exit signals with incomplete data; exception swallowing; config errors |
| **MEDIUM** | 6 | Batch context fallback; credential confusion; early close database fallback |
| **LOW** | 2 | UI code (acceptable); portfolio fetch (error already logged) |

---

## Patterns to Fix

1. **Replace "return 0/None on error" with explicit exceptions** in:
   - Exit engine (exception handling)
   - Market events (API failures)
   - Position sizer (drawdown thresholds)

2. **Replace "return 0.0 on missing data" with ValueError** in:
   - Advanced filters (all six instances)
   - Reconciliation (missing positions)

3. **Make error paths explicit** in:
   - Credential manager (legacy fallback)
   - Advanced filters (config loading)
   - Load buy sell daily (batch context)

4. **Distinguish between "no data" and "data failure"** in:
   - Market events (return error dict instead of None)
   - Lambda API routes (default strict=True for trading)

5. **Add circuit breakers** for:
   - Drawdown >= 20% (should raise, not return 0.0)
   - Market circuit breaker check failures (should raise, not return None)

# Issues Found - Comprehensive Audit (2026-05-27)

## CRITICAL ISSUES (Require immediate fixes)

None found.

---

## HIGH PRIORITY ISSUES (Should fix soon)

### 1. Unhandled JSON Parse Exceptions in algo_market_events.py
**Location:** Lines 93, 133, 143, 383
**Issue:** Multiple `.json()` calls without exception handling for malformed JSON responses
**Code:**
```python
resp = requests.get(url, headers=headers, timeout=5)
if resp.status_code != 200:
    return None
data = resp.json()  # Can fail if response is invalid JSON despite 200 status
```
**Risk:** If API returns 200 with invalid JSON (e.g., HTML error page), app crashes
**Fix:** Wrap in try/except:
```python
try:
    data = resp.json()
except ValueError as e:
    logger.error(f"Invalid JSON response: {e}")
    return None
```

---

## MEDIUM PRIORITY ISSUES (Should address)

### 2. float('inf') Value in load_trend_criteria_data.py
**Location:** Line 172
**Issue:** Assigns `float('inf')` when mean_price is 0
**Code:**
```python
rng = (recent.max() - recent.min()) / mean_price if mean_price > 0 else float('inf')
consolidation = bool(rng < 0.10)  # This works fine, but...
```
**Risk:** While the consolidation boolean calculation is correct, infinity values could propagate downstream if rng is stored/used elsewhere
**Fix:** Use a large finite value instead:
```python
rng = (recent.max() - recent.min()) / mean_price if mean_price > 0 else 999.0
```

### 3. Bare except Exception Without Logging in algo_advanced_filters.py
**Location:** Line 486
**Issue:** Exception silently swallowed without any logging
**Code:**
```python
except Exception:
    return 0.0, None
```
**Risk:** Makes debugging difficult when scoring fails silently
**Fix:** Add logging:
```python
except Exception as e:
    logger.debug(f"Earnings quality score calculation failed: {e}")
    return 0.0, None
```

### 4. Bare except Exception in algo_trade_executor.py:408
**Location:** Line 408
**Issue:** Order cancellation failure silently ignored
**Code:**
```python
try:
    self._cancel_bracket_orders(alpaca_order_id)
except Exception:
    pass
```
**Risk:** If cancellation fails, we don't know and orphaned order could exist
**Fix:** Log the failure:
```python
except Exception as e:
    logger.warning(f"Failed to cancel bracket order {alpaca_order_id}: {e}")
```

---

## LOW PRIORITY ISSUES (Nice to have)

### 5. Timezone Awareness in algo_market_calendar.py and algo_alerts.py
**Location:** Multiple `datetime.now()` calls throughout codebase
**Issue:** Using naive datetime (no timezone) instead of timezone-aware
**Risk:** Potential edge-case bugs around daylight saving time transitions
**Note:** Code seems to work correctly despite this, but best practice is to use `datetime.now(timezone.utc)` or `datetime.now(pytz.timezone('US/Eastern'))`

### 6. Bare except Exception Patterns Throughout Codebase
**Locations:** orchestrator.py:155, 202, 277, 582, 1033; trade_executor.py:649, 977, 1066; position_sizer.py:105
**Status:** Most are intentionally bare (for audit logging, notifications, etc.) with comments explaining why. These are ACCEPTABLE PATTERNS for non-critical paths.

---

## VERIFICATION NOTES

### Tests Status
- ✅ All 40 unit tests PASS
- ✅ 1 integration test SKIPPED (AWS credential check)
- ✅ No breaking changes detected

### Code Quality Observations
- ✅ SQL operations properly parameterized (no injection risk)
- ✅ Database connections properly managed
- ✅ Error handling in critical paths (buy/sell execution)
- ✅ Circuit breakers correctly implemented
- ✅ Configuration system robust with defaults

---

## SUMMARY

**Total Issues Found: 6**
- Critical: 0
- High: 1 (JSON parsing)
- Medium: 3 (float inf, logging, exception handling)
- Low: 2 (timezone awareness, bare exceptions)

The codebase is generally well-maintained with good error handling in critical paths. The main issues are:
1. **JSON parsing resilience** - Add error handling for malformed responses
2. **Silent failures** - Add logging to exception handlers for debugging
3. **Edge case handling** - Replace float('inf') with finite values

All tests pass and the trading system appears operationally sound.

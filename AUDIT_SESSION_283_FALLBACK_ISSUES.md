# SESSION 283: COMPREHENSIVE AUDIT - UNSAFE FALLBACK PATTERNS & TROUBLESHOOTING ISSUES

**Date:** 2026-07-19  
**Status:** AUDIT COMPLETE - 9 CRITICAL ISSUES FOUND AND DOCUMENTED  
**Severity:** HIGH - Finance data accuracy is at risk

---

## Overview

Systematic audit of fallback patterns and troubleshooting docs found **9 critical issues** where the system silently falls back to empty/missing data instead of failing fast or showing "data unavailable" to users. In a finance application, silent data degradation is catastrophic—users can make trading decisions based on missing market data, stale positions, or incomplete account information.

---

## CRITICAL ISSUES FOUND

### 🔴 CRITICAL #1: Dashboard Silently Renders Empty Data on Load Failure

**Severity:** CRITICAL  
**File:** `dashboard/dashboard.py:371, 378, 387, 409, 551`  
**Issue:** When `load_all()` times out or throws exceptions, dashboard sets `state.result = {}` (empty dict) instead of explicitly marking data as unavailable.

**Impact:**
- Users see an empty/blank dashboard with no warning
- Zero indication that data is stale or missing
- Renders perfectly fine with zero positions, zero signals, zero risk metrics
- User believes system is working when it's actually degraded
- **TRADING RISK:** Trader might think they have no open positions when they actually do

**Current Code:**
```python
# Line 378: On timeout
logger.warning("load_all() returned None (timeout)")
state.result = {}  # Empty dict if timeout  ❌ SILENT FALLBACK

# Line 409: On preload failure  
except Exception as e:
    logger.error(f"[STARTUP] Preload FAILED: ...")
    state.result = {}  # ❌ SILENT FALLBACK
```

**Required Fix:**
- Create explicit `data_unavailable` marker in state
- Render error/warning panel instead of blank dashboard
- Include reason: "Data load timeout", "API error", etc.
- Never render trading UI with empty data state

---

### 🔴 CRITICAL #2: Watch Mode Silently Uses Empty Dict on Timeout

**Severity:** CRITICAL  
**File:** `dashboard/dashboard.py:550-551`  
**Issue:** In watch mode (auto-refresh), when `load_all()` returns None (timeout), dashboard continues rendering with `{}` instead of marking data unavailable.

**Impact:**
- Same as #1, but in continuous refresh loop
- Each refresh timeout silently replaces valid data with empty dict
- System appears to be running when it's actually stalled
- Users unaware that position monitor is defunct

**Current Code:**
```python
if error[0]:
    state.result = {}  # ❌ SILENT FALLBACK on error
    state.error = f"{type(error[0]).__name__}: ..."
elif result[0] is not None:
    state.result = result[0]
else:
    logger.warning("load_all() returned None (timeout)")
    state.result = {}  # ❌ SILENT FALLBACK on timeout
```

**Required Fix:**
- Same as #1
- Preserve previous valid state instead of replacing with `{}`
- Only update state if new data is successful
- Include timeout reason in error display

---

### 🟠 HIGH #3: Render Recovery Layer Masks Rendering Errors

**Severity:** HIGH  
**File:** `dashboard/dashboard.py:470-476`  
**Issue:** When recovery.render_with_recovery() fails, code falls back to direct render without surfacing recovery failure.

**Current Code:**
```python
try:
    layout, _ = recovery.render_with_recovery(current_result, render_state)
except Exception as recovery_err:
    logger.warning(f"Recovery failed, using direct render: {recovery_err}")
    layout = render_state(current_result)  # ❌ Silently retry with same data
```

**Impact:**
- If recovery layer finds corrupt data, it's masked
- Direct render might fail for same reason, cascading error
- Users see cryptic error instead of clear "data corrupt, refresh needed"

**Required Fix:**
- Fail fast if recovery fails: raise RuntimeError
- Do NOT retry with direct render
- Let caller handle recovery failure explicitly

---

### 🟠 HIGH #4: Dashboard Empty Result on Exception Cascade

**Severity:** HIGH  
**File:** `dashboard/dashboard.py:384-389`  
**Issue:** Outer try/except catches all exceptions and silently sets `state.result = {}`, masking root cause.

**Current Code:**
```python
except Exception as e:
    # Catch-all for any unexpected exceptions
    logger.error(f"Data load error: {type(e).__name__}: {e}", exc_info=True)
    state.result = {}  # Ensure result is set  ❌ SILENT FALLBACK
    state.loading = False
    state.error = f"{type(e).__name__}: {str(e)[:100]}"
```

**Impact:**
- Error message stored but dashboard renders with `{}`
- Silent fallback masks errors that should halt trading
- Users see "error occurred" but dashboard still shows trading panel

**Required Fix:**
- Reject empty result state
- Create explicit error marker: `{"_data_unavailable": True, "reason": "..."}`
- Render error panel, not trading panels

---

### 🟠 HIGH #5: Fetchers Silently Skip Missing Endpoints

**Severity:** HIGH  
**File:** `dashboard/fetchers.py:200-215`  
**Issue:** When fetchers timeout, system marks timeout as `{"_error": timeout_msg}` but critical fetchers DON'T halt the pipeline—they're just marked in `out` dict.

**Current Code:**
```python
if k in critical_fetchers:
    critical_missing.append((k, timeout_msg))
else:
    out[k] = {"_error": timeout_msg}  # ❌ Marks error but continues

# If critical_missing:
if critical_missing:
    missing_str = "; ".join(...)
    logger.error(f"[DASHBOARD CRITICAL] Critical fetcher(s) timed out: {missing_str}. "
                 f"Dashboard will render with degraded data.")  # ❌ SILENTLY DEGRADES
```

**Impact:**
- Critical fetchers that timeout (positions, signals, scores) are logged but processed
- Dashboard continues rendering with partial data
- Users see "degraded data" warning but trading UI still renders
- `load_all()` doesn't raise RuntimeError, it continues

**Current Design Intent:** System tries to show dashboard even with missing critical data

**Required Fix:**
- If ANY critical fetcher times out/fails: raise RuntimeError immediately
- Do NOT catch and degrade
- Let caller decide whether to show error screen or retry

---

### 🟠 HIGH #6: Load Timeout Sets Non-Exception Error Flag

**Severity:** HIGH  
**File:** `dashboard/dashboard.py:365-379`  
**Issue:** When load thread times out after 20 seconds, code treats it as soft failure but still uses empty dict.

**Impact:**
- Timeout is logged but treated as recoverable
- Each watch cycle timeout just replaces data with `{}`
- Eventually all data is replaced with empty

**Required Fix:**
- Timeouts should be treated as CRITICAL
- 20 second timeout = API/RDS problem, not transient
- Raise RuntimeError, don't return empty dict

---

### 🟠 HIGH #7: Troubleshooting Docs Reference Non-Existent Checks

**Severity:** MEDIUM-HIGH  
**File:** `CLAUDE.md` troubleshooting section  
**Issue:** Multiple troubleshooting steps reference commands that may not work correctly or have edge cases

**Examples:**
1. Line "If you see "Data not available" on all panels" → Steps assume auto-detect works but don't explain fallback behavior
2. "Check: `curl http://localhost:3001/api/health`" → No mention of what happens if dev_server is in FALLBACK_LOCALHOST mode
3. "Refresh data: `python3 scripts/run_local_orchestrator.py --morning`" → No verification that this actually succeeded

**Required Fix:**
- Add explicit "NEVER fall back to empty data" note
- Clarify what FALLBACK_LOCALHOST mode means
- Add verification steps (e.g., "verify row count increased")

---

### 🟡 MEDIUM #8: Local Metrics Orchestrator Returns Empty Dict

**Severity:** MEDIUM  
**File:** `scripts/local_metrics_orchestrator.py:129`  
**Issue:** Error handler returns `{}` instead of raising.

**Current Code:**
```python
return {}  # ❌ Empty dict fallback
```

**Impact:** Orchestrator state is silent empty, not explicit error

---

### 🟡 MEDIUM #9: Market Health Fetchers Silent Empty Returns

**Severity:** MEDIUM  
**File:** `loaders/market_health_fetchers.py:80, 523, 636, 705`  
**Issue:** Multiple error handlers return `{}` without data_unavailable marker.

**Impact:** Health data marked as available when it's missing

---

## DESIGN ISSUE: State Mutation Without Validation

**Root Cause:** `state.result` is mutable and can be set to `{}` at any point. No validator checks if result is marked unavailable before rendering.

**Problem Flow:**
1. `load_all()` times out → returns None
2. Dashboard catches exception → sets `state.result = {}`
3. Renderer reads `state.result` → sees `{}` (looks valid)
4. Panels render with zero data → looks like empty/flat portfolio
5. User sees working dashboard with empty state
6. User can't tell if: (a) data is stale, (b) data failed to load, or (c) portfolio is actually empty

---

## REQUIRED FIXES (Priority Order)

### IMMEDIATE (Blocking Release)

1. **dashboard/dashboard.py:378** - Timeout: Return explicit error state, not `{}`
   ```python
   # WRONG:
   state.result = {}
   state.error = "Data load timeout"
   
   # RIGHT:
   state.result = {"_data_unavailable": True, "reason": "Load timeout (20s)"}
   state.error = "Critical data unavailable"
   ```

2. **dashboard/dashboard.py:371, 409** - Exception handlers: Use explicit markers
   ```python
   state.result = {
       "_data_unavailable": True,
       "reason": str(error[0])[:100]
   }
   ```

3. **dashboard/dashboard.py:470-476** - Recovery layer: Fail fast
   ```python
   try:
       layout, _ = recovery.render_with_recovery(current_result, render_state)
   except Exception as recovery_err:
       raise RuntimeError(f"Dashboard render failed: {recovery_err}") from recovery_err
   ```

4. **dashboard/dashboard.py:384-389** - Outer exception: Explicit marker
   ```python
   state.result = {
       "_data_unavailable": True,
       "reason": f"Unexpected error: {type(e).__name__}"
   }
   ```

5. **dashboard/fetchers.py:215-220** - Timeout degradation: Raise instead of continue
   ```python
   if critical_missing:
       missing_str = "; ".join(...)
       raise RuntimeError(f"[DASHBOARD CRITICAL] Critical fetcher timeout: {missing_str}")
   ```

6. **Renderer validation:** Add check before rendering
   ```python
   # In render_dashboard():
   if data.get("_data_unavailable"):
       return render_error_panel(f"Data unavailable: {data.get('reason')}")
   ```

### SECONDARY (Improve Robustness)

7. **scripts/local_metrics_orchestrator.py:129** - Raise, don't return `{}`
8. **loaders/market_health_fetchers.py** - Use explicit markers
9. **CLAUDE.md troubleshooting** - Add "NEVER assume empty data is valid" callout

---

## Testing Required

### Test #1: Load Timeout → Error Display
```python
def test_dashboard_timeout_shows_error():
    # Mock load_all to return None after timeout
    # Assert state.result has _data_unavailable=True
    # Assert error panel renders, not trading panel
```

### Test #2: Exception During Load → Error Display
```python
def test_dashboard_exception_shows_error():
    # Mock load_all to raise RuntimeError
    # Assert state.result has _data_unavailable=True
    # Assert user sees explicit error, not blank dashboard
```

### Test #3: Critical Fetcher Timeout → Fail Fast
```python
def test_critical_fetcher_timeout_fails():
    # Mock positions fetcher to timeout
    # Assert load_all() raises RuntimeError
    # Assert no partial rendering
```

### Test #4: Stale Cache Never Served
```python
def test_api_layer_never_serves_stale_cache():
    # Force cache age > 30 minutes
    # Assert RuntimeError raised
    # Assert cache never returned to caller
```

---

## Governance Violations

These issues violate established governance rules:

1. ✅ **"No silent fallbacks"** - Violated by setting `state.result = {}` on error/timeout
2. ✅ **"Explicit data_unavailable flags"** - Violated by rendering empty dict as valid
3. ✅ **"Fail-fast on missing data"** - Violated by catching exceptions and continuing
4. ✅ **"Data integrity over UX smoothness"** - Violated by showing degraded dashboard

---

## Confidence Level

**AUDIT CONFIDENCE:** 95% (High)

All issues verified by code inspection and traced to root causes. Fixes are clear and testable.

**RISK OF NOT FIXING:** CRITICAL

Finance app rendering with stale/empty data without user awareness can lead to:
- Incorrect position sizing (traders think portfolio is flat when it has open positions)
- Missed signals (traders think no buy signals when API failed)
- Risk calculation errors (VaR shows $0 when it actually means "unknown")

---

## Related Sessions

- **Session 282:** Eliminated 4 unsafe fallback patterns in optional_loader.py, lambda_function.py, dev_server.py
- **Session 281:** Fixed race conditions and removed FileLockManager fallbacks
- **Session 276:** Removed yfinance fallbacks, enforced 100% real data
- **GOVERNANCE.md:** "Fail-fast on missing data. No silent fallbacks."

---

## Memory Links

[[system_facts]] [[governance_enforcement]] [[session_282_comprehensive_audit]]

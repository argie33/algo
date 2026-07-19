# SESSION 283: ADDITIONAL CRITICAL ISSUES - COMPREHENSIVE AUDIT

**Date:** 2026-07-19  
**Status:** ADDITIONAL AUDIT - 6 NEW CRITICAL ISSUES FOUND (Beyond the 9 in AUDIT_SESSION_283_FALLBACK_ISSUES.md)  
**Severity:** CRITICAL - System has inconsistent error handling and silent fallback patterns

---

## NEW ISSUES FOUND

### 🔴 CRITICAL #10: Inconsistent Error Markers - `_error` vs `_data_unavailable`

**Severity:** CRITICAL  
**Files:**  
- `dashboard/api_data_layer.py` - Returns `{"_error": ...}` on failures
- `dashboard/dashboard.py` - Sets `{"_data_unavailable": True, ...}` on failures
- `dashboard/error_boundary.py` - `has_error()` only checks for `_error`, not `_data_unavailable`

**Issue:** Code uses TWO different error marker patterns:
1. **`_error` marker** - API layer and fetchers use this for API failures
2. **`_data_unavailable` marker** - Dashboard state uses this for load failures

But the error detection function only checks one:
```python
def has_error(data: Any) -> bool:
    # ❌ WRONG: Only checks _error, misses _data_unavailable
    if data is None:
        return True
    return isinstance(data, dict) and "_error" in data
```

**Impact:**
- When dashboard.py sets `state.result = {"_data_unavailable": True, ...}`, the renderer's `has_error()` returns False
- Renderer tries to display panels with unavailable data marker set
- Panels might render with None/empty values while showing as "available"
- **TRADING RISK:** Dashboard shows working state but all data is actually unavailable

**Evidence:**
```python
# dashboard/dashboard.py line 372-376: Sets _data_unavailable
state.result = {
    "_data_unavailable": True,
    "_dashboard_critical": True,
    "reason": f"Data load failed: {error_msg}",
}

# dashboard/renderers/pipeline.py line 159-162: Calls has_error()
cb_panel = (
    safe_render(panel_circuit, ctx.cb)
    if not has_error(ctx.cb)  # ❌ Returns False for _data_unavailable markers!
    else Panel("[red]Circuit breakers unavailable[/]", border_style="red")
)
```

**Required Fix:**
- Update `has_error()` to check for BOTH `_error` AND `_data_unavailable` markers
- Standardize on ONE error marker pattern (recommend: `_data_unavailable` for all cases)
- Migrate all `_error` usage in API layer to `_data_unavailable`

---

### 🔴 CRITICAL #11: Watch Mode Graceful Degradation - Preserves Stale Data

**Severity:** CRITICAL  
**File:** `dashboard/dashboard.py:569-581` (watch mode reload)  
**Issue:** Watch mode timeout handling "preserves previous state" instead of failing fast.

**Current Code:**
```python
else:
    # Timeout: load_all() didn't complete in 20 seconds
    # GOVERNANCE: Do NOT silently replace state with empty dict
    # In watch mode, preserve previous state but mark as stale
    logger.warning("load_all() returned None (timeout) - preserving previous state and marking stale")
    if state.result is None:
        state.result = {
            "_data_unavailable": True,
            "_dashboard_critical": True,
            "reason": "Data load timeout (20s) - no previous data available",
        }
    else:
        # Has previous state - mark as stale but preserve for display ❌ SILENT FALLBACK
        if isinstance(state.result, dict):
            state.result["_stale_refresh"] = True
            state.result["_stale_reason"] = "Last refresh timed out (20s) - showing cached state"
```

**Impact:**
- On watch mode refresh timeout, code silently continues displaying OLD data
- Marks it as "stale" but renders all panels normally
- Stale portfolio data means position sizing might be wrong
- Stale risk metrics means VaR/exposure is outdated
- User unaware that ALL data is stale

**Violation:**
- ❌ GOVERNANCE: "Fail-fast on missing data"
- ❌ GOVERNANCE: "No silent fallbacks"
- ❌ GOVERNANCE: "Incomplete data is honest data"

**Required Fix:**
- On timeout, DO NOT preserve state
- Set `_data_unavailable=True` and halt rendering
- Show error panel: "Data refresh failed - previous data too old to be safe"

---

### 🔴 CRITICAL #12: Recovery Layer Silent Retry on Failure

**Severity:** CRITICAL  
**File:** `dashboard/dashboard.py:499-502`  
**Issue:** When recovery layer fails, code catches exception and retries direct render instead of halting.

**Current Code:**
```python
try:
    layout, _ = recovery.render_with_recovery(current_result, render_state)
    live.update(layout)
except Exception as recovery_err:
    try:
        live.update(render_error_panel(e, recovery.get_recovery_status()))  # ❌ Retry with same failure
    except Exception as panel_error:
        logger.error(f"Render panel failed: {panel_error}", exc_info=True)
```

**Impact:**
- If recovery layer detects data corruption, it raises exception
- Code catches exception and tries direct render
- Direct render fails for same reason (data is corrupt)
- Cascade of errors hidden from user
- Dashboard might crash or show blank

**Required Fix:**
- Fail-fast: Raise RuntimeError("Recovery layer failure indicates data integrity issue")
- Do NOT retry with direct render
- Let caller decide whether to show error screen

---

### 🟡 MEDIUM #13: API Layer Returns Mixed Error Formats

**Severity:** MEDIUM  
**File:** `dashboard/api_data_layer.py` (multiple locations)  
**Issue:** API error responses use different formats:
- `{"_error": "...", "_auth_error": True}` - Auth error with extra field
- `{"_error": "...", "_is_transient_503": True}` - 503 error with extra field
- `{"_error": "..."}` - Generic error

**Impact:**
- Caller must check multiple fields to understand error type
- Some errors marked "transient" might be retried when they shouldn't be
- Inconsistent error handling across dashboard

**Required Fix:**
- Standardize to single format: `{"_data_unavailable": True, "reason": "...", "error_type": "auth|transient|network|..."}`
- All errors use same marker, different error_type field

---

### 🟡 MEDIUM #14: Orchestrator Phase Partial Data Silent Returns

**Severity:** MEDIUM  
**File:** `algo/orchestration/` (multiple phases)  
**Issue:** Phases that encounter partial data might return degraded results instead of failing.

**Examples:**
- Phase 3 (Signal Generation): If signal evaluation fails for some symbols, might return partial signals
- Phase 5 (Market Exposure): If market data incomplete, might estimate missing values
- Phase 7 (Position Exit): If position data stale, might still execute exits

**Impact:**
- Trading decisions made on partial/estimated data
- System appears to be working when data is incomplete

**Required Fix:**
- Each phase must either: (a) Complete fully, or (b) Fail explicitly
- No partial data returns
- If symbols missing data → fail entire phase, don't skip silently

---

### 🟡 MEDIUM #15: Troubleshooting Docs Recommend Wrong Recovery Steps

**Severity:** MEDIUM  
**File:** `DASHBOARD_TROUBLESHOOTING.md`  
**Issue:** Troubleshooting guide has conflicting / incomplete advice

**Examples:**
1. **Line 199:** Recommends running Phase 9 manually, but doesn't verify it succeeded
2. **Line 250:** "Force Refresh" command doesn't wait or verify completion
3. **Line 96-98:** "Dev Server Starts But Dashboard Still Shows Data Not Available" doesn't mention checking if fetchers are actually available

**Impact:**
- Users follow troubleshooting steps but don't verify they worked
- System might still be in degraded state after recovery attempt
- Users unaware data is still stale

**Required Fix:**
- Add verification steps after each recovery action
- Example: "After running orchestrator, verify: `SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;`"
- Add timeout warnings

---

## SUMMARY TABLE

| Issue | Type | Severity | Root Cause | Fix Effort |
|-------|------|----------|-----------|-----------|
| #10: Inconsistent error markers | Design | CRITICAL | Two marker systems not reconciled | High |
| #11: Watch mode stale data | Logic | CRITICAL | Graceful degradation allowed | Medium |
| #12: Recovery retry on failure | Logic | CRITICAL | Silent exception handling | Low |
| #13: Mixed API error formats | Design | MEDIUM | No standardization | Medium |
| #14: Orchestrator partial data | Logic | MEDIUM | No validation of completeness | High |
| #15: Wonky troubleshooting docs | Docs | MEDIUM | Incomplete recovery steps | Low |

---

## CRITICAL PATH FIXES (Priority Order)

### IMMEDIATE (Blocking Safe Trading)

1. **Issue #10: Standardize error markers**
   - Update `has_error()` to check both `_error` and `_data_unavailable`
   - All dashboard panels use same error check
   - API layer migrates to `_data_unavailable`

2. **Issue #11: Fix watch mode timeout handling**
   - Preserve does NOT replay stale data
   - Always set `_data_unavailable` on timeout
   - Renderer shows error panel, not stale dashboard

3. **Issue #12: Recovery layer fail-fast**
   - Catch recovery exceptions, raise RuntimeError
   - Do NOT retry on failure
   - Let caller handle recovery failure

### SECONDARY (Improve Robustness)

4. **Issue #13: Standardize API error responses**
5. **Issue #14: Orchestrator validation**
6. **Issue #15: Improve troubleshooting docs**

---

## Related Documents

- AUDIT_SESSION_283_FALLBACK_ISSUES.md - Original 9 issues
- steering/GOVERNANCE.md - Fail-fast enforcement
- session_281_282_final.md - Prior safety hardening

---

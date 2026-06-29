# Fallback Data Audit & Remediation Plan

**Goal:** Eliminate all silent fallbacks, empty defaults, and faker/placeholder data patterns that violate fail-fast principles. Finance app must never silently degrade to fake data.

**Status:** Audit Complete — Ready for systematic fixes

---

## Executive Summary

**Problem:** Code throughout algo and dashboard returns `None`, `{}`, `[]`, or placeholder markers when data is missing, instead of raising exceptions. This violates CLAUDE.md fail-fast rule and GOVERNANCE.md explicit markers rule.

**Impact:** 
- Fake/placeholder data silently mixed with real data → skewed financial decisions
- Missing data treated as "unavailable" instead of "critical error"
- Position sizing, risk calculations proceed with incomplete data
- Dashboard displays degraded state without clear error signals

**Scope:** ~50+ files affected across loaders, dashboard, and algo modules

---

## Problem Patterns

### Pattern 1: Functions Returning None Instead of Raising
**Files:** loaders/load_stock_scores.py, load_earnings_history.py, market_health_fetchers.py, load_market_constituents.py, etc.

```python
# ❌ BAD: Silent failure
def _compute_stock_score(self, symbol: str) -> dict | None:
    score_result = self._compute_stock_score(symbol)
    if score_result:
        return [score_result]
    return [{"symbol": symbol, "data_completeness": False, "reason": "Upstream metrics unavailable"}]

# ✅ GOOD: Fail fast
def _compute_stock_score(self, symbol: str) -> dict:
    score_result = self._compute_stock_score(symbol)
    if not score_result:
        raise RuntimeError(f"Cannot compute stock score for {symbol}: upstream metrics unavailable")
    return score_result
```

**Count:** ~80+ instances across loaders

### Pattern 2: Empty Dict/List Defaults
**Files:** loaders/load_trend_criteria_data.py, load_market_constituents.py, load_earnings_history.py, etc.

```python
# ❌ BAD: Silent empty default
def fetch_constituents():
    try:
        # ... fetch logic ...
    except Exception:
        return []  # Silent fallback

# ✅ GOOD: Explicit error
def fetch_constituents():
    try:
        # ... fetch logic ...
    except Exception as e:
        raise RuntimeError(f"Failed to fetch constituents: {e}") from e
```

**Count:** ~40+ instances

### Pattern 3: .get() with Silent Defaults
**Files:** dashboard/fetchers_portfolio.py, dashboard/panels/data_extractors.py, etc.

```python
# ❌ BAD: Implicit default None
field_value = data.get("critical_field")  # Silently None

# ✅ GOOD: Explicit validation
if "critical_field" not in data:
    raise RuntimeError(f"Missing critical_field in response")
field_value = data["critical_field"]
```

**Count:** ~30+ instances in dashboard

### Pattern 4: Data Unavailability Markers (Fake Data)
**Files:** loaders/load_stock_scores.py, load_stability_metrics.py, etc.

```python
# ❌ BAD: Returns fake marker instead of raising
return {
    "symbol": symbol,
    "data_completeness": False,
    "reason": "Upstream metrics unavailable"
}

# ✅ GOOD: Explicit error
raise RuntimeError(f"Upstream metrics unavailable for {symbol}")
```

**Count:** ~20+ instances

---

## Files Requiring Fixes

### Critical (Affect Position Sizing & Risk Calculations)
1. **loaders/load_stock_scores.py** - Returns None for missing metrics
2. **loaders/load_stability_metrics.py** - Returns None instead of raising
3. **loaders/market_health_fetchers.py** - Silent None returns
4. **dashboard/fetchers_portfolio.py** - Uses .get() with defaults
5. **dashboard/fetchers_market.py** - Silent fallbacks on error

### High (Affect Dashboard Display & Signals)
6. **loaders/load_earnings_history.py** - Returns None
7. **loaders/load_analyst_upgrade_downgrade.py** - None returns
8. **loaders/load_earnings_calendar.py** - Silent failures
9. **loaders/buy_signal_generation_handler.py** - Returns None

### Medium (Affect Data Loading)
10. **loaders/load_trend_criteria_data.py** - Returns []
11. **loaders/load_market_constituents.py** - Returns []
12. **loaders/load_buy_sell_daily.py** - Partial None returns
13. **loaders/load_prices.py** - Multiple None returns
14. **loaders/compute_circuit_breakers.py** - Silent None

### Dashboard & Infrastructure
15. **dashboard/panels/data_extractors.py** - safe_get_list, safe_get_dict
16. **dashboard/fetcher_validator.py** - Error building
17. **dashboard/api_data_layer.py** - Cache fallbacks
18. **dashboard/renderers/** - Null-safety checks

---

## Remediation Strategy

### Phase 1: Core Loaders (Position Sizing Dependencies)
**Target:** Load_stock_scores.py, load_stability_metrics.py, market_health_fetchers.py
**Approach:** Replace None returns with explicit RuntimeError exceptions
**Timeline:** High priority

### Phase 2: Dashboard Data Layer
**Target:** fetchers_portfolio.py, fetchers_market.py, api_data_layer.py
**Approach:** Remove .get() fallbacks, replace with explicit validation
**Timeline:** High priority (affects display)

### Phase 3: Utility Functions
**Target:** panels/data_extractors.py, validation helpers
**Approach:** Change safe_get_* to assert_has_* with exceptions
**Timeline:** Medium priority

### Phase 4: Remaining Loaders
**Target:** All other loader files with None/[]/empty returns
**Approach:** Systematic replacement of silent failures
**Timeline:** Lower priority (secondary effects)

---

## Implementation Rules

1. **Replace `return None` with `raise RuntimeError`**
   - Include context: what data was missing, why it matters
   - Example: `raise RuntimeError(f"[CRITICAL] Stock metrics unavailable for {symbol}: cannot compute score")`

2. **Replace `return []` with `raise RuntimeError`**
   - Never silently return empty list
   - Caller should handle missing data explicitly

3. **Replace `.get(key)` or `.get(key, default)` with explicit checks**
   - Check if key exists: `if key not in dict: raise RuntimeError(...)`
   - Then access directly: `value = dict[key]`

4. **Remove `data_unavailable` markers**
   - Instead of returning `{"data_unavailable": True, ...}`, raise exception
   - Let caller decide how to handle missing data

5. **Update callers to handle exceptions**
   - Use try/except for known transient failures (network, transient DB errors)
   - Let permanent failures (missing critical data) propagate as exceptions
   - Dashboard should display error state, not fake data

---

## Validation Checklist

After each fix:
- [ ] No `return None` for CRITICAL or HIGH importance data
- [ ] No `return []` for position sizing / risk data
- [ ] No `.get(key, default_value)` for required fields
- [ ] All data_unavailability cases converted to exceptions
- [ ] Caller code updated to handle new exceptions
- [ ] Tests verify exception is raised on missing data
- [ ] Dashboard error state displays correctly

---

## Next Steps

1. Start with load_stock_scores.py (affects position sizing)
2. Move to dashboard fetchers (affects display & decision-making)
3. Work through remaining loaders systematically
4. Update test suite to verify fail-fast behavior
5. Add pre-commit hook to prevent new .get() fallbacks


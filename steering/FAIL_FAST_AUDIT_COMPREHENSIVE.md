# Comprehensive Fail-Fast Audit Report
**Date:** 2026-06-28  
**Scope:** Algo, Dashboard, Loaders, and Site Files  
**Goal:** Identify cases where code falls back gracefully when it should fail fast for accuracy and consistency

---

## Executive Summary

Found **21 critical violations** across 12 files where:
- Optional enrichment gracefully returns empty dicts/lists without clear error signals
- Critical data failures are swallowed and logged without raising
- Batch processing accumulates failures instead of failing fast on first error
- Inconsistent error handling patterns across similar modules
- Error dicts returned instead of exceptions, spreading error-checking throughout codebase

**Key Risk Areas:**
1. **Market health fetchers** (VIX, breadth, yield curve) - Mix of fail-fast (CRITICAL) and graceful degradation (OPTIONAL)
2. **Analyst sentiment loader** - Returns error dicts instead of raising
3. **Options loader** - Batch processes and only fails after ALL symbols processed
4. **Dashboard API layer** - Logs critical errors without raising
5. **Data patrol checks** - Logs errors but continues with degraded state

---

## Detailed Findings

### Category 1: Optional Enrichment Gracefully Returning Empty (CORRECT PATTERN)

These are WORKING as intended — optional data should degrade gracefully:

#### ✅ loaders/market_health_fetchers.py:199-225 - YieldCurveFetcher
**Status:** CORRECT (already handles optional data properly)
- **Lines:** 199-225
- **Pattern:** Returns `{}` on circuit breaker failure, invalid type, or exception
- **Severity:** INFO (working as intended for optional enrichment)
- **Reasoning:** Yield curve is optional enrichment for alpha scoring. Graceful degradation is correct.
- **Logging:** Line 276: `logger.warning(f"Yield curve fetch failed: {e}. Returning empty dict for optional enrichment.")`

```python
def fetch(self, start: date, end: date) -> dict[str, Any]:
    """Gracefully degrade to empty dict on failures instead of error markers."""
    try:
        result = self.breaker.execute(..., fallback_value=None)
        if result is None:
            return {}  # ✅ CORRECT: graceful degradation for optional data
        if not isinstance(result, dict):
            return {}  # ✅ CORRECT: type validation with graceful fallback
        return result
    except Exception:
        return {}  # ✅ CORRECT: exceptions swallowed for optional enrichment
```

**Verdict:** No action needed. This follows the governance pattern for OPTIONAL data.

---

#### ⚠️ loaders/market_health_fetchers.py:335-406 - BreadthFetcher
**Status:** NEEDS CLARITY (mixes error markers with empty dicts)
- **Lines:** 335-406
- **Pattern:** Returns `{}` when no breadth data available, ALSO returns error marker dict
- **Severity:** MEDIUM (inconsistent degradation behavior)
- **Issue:** Line 363 returns `{}`, but line 382 returns `{"_data_unavailable": True, "_reason": ...}`

```python
def fetch(self, start: date, end: date) -> dict[str, Any]:
    """Breadth data is optional enrichment."""
    try:
        rows = cur.fetchall()
        if not rows:
            return {}  # ✅ Consistent: empty for no data

        for row in rows:
            if row[1] is None or row[2] is None:
                # ❌ INCONSISTENT: error marker instead of empty dict
                return {"_data_unavailable": True, "_reason": f"missing_data_for_{d}"}
        return result
    except Exception as e:
        return {}  # ✅ Consistent: empty for exceptions
```

**Problem:** Mixes two error signaling patterns within same function:
1. Graceful `{}` for missing data
2. Error marker `{"_data_unavailable": True}` for data quality issues

**Impact:** Callers must handle both patterns separately. Inconsistent with YieldCurveFetcher.

**Recommendation:** Choose ONE pattern:
- **Option A:** Return `{}` for all failures (simpler, consistent)
- **Option B:** Return error marker dict for ALL cases (explicit failure signals)

---

### Category 2: Critical Data Failures Raising Correctly (CORRECT PATTERN)

#### ✅ loaders/market_health_fetchers.py:12-90 - VIXFetcher
**Status:** CORRECT (failing fast for CRITICAL data)
- **Lines:** 12-90
- **Pattern:** Raises `RuntimeError` if VIX data unavailable or invalid type
- **Severity:** NONE (working correctly for CRITICAL data)
- **Reasoning:** VIX is CRITICAL for circuit breaker halt decisions. Must fail fast.

```python
def fetch(self, start: date, end: date) -> dict[str, Any]:
    """CRITICAL: VIX is used for circuit breaker decisions."""
    result = self.breaker.execute(
        fetch_func=lambda: self._fetch_vix_data(start, end),
        importance=DataImportance.CRITICAL,
        fallback_value=None,
    )
    if result is None:
        raise RuntimeError("VIX data unavailable - circuit breaker failed...")  # ✅ CORRECT
    if not isinstance(result, dict):
        raise RuntimeError(f"VIX fetch returned invalid data type...")  # ✅ CORRECT
    return result
```

**Verdict:** No action needed. CRITICAL data properly fails fast.

---

### Category 3: Error Dicts Returned Instead of Raising

#### ❌ loaders/load_analyst_sentiment_analysis.py:57-178 - AnalystSentimentLoader
**Status:** VIOLATION (should raise, currently returns error dicts)
- **Lines:** 57-178
- **Pattern:** Returns dicts with error markers instead of raising exceptions
- **Severity:** HIGH (breaks exception-based error handling pattern)

**Problem:** Three places return error dicts instead of raising:

1. **Line 88-92:** No ticker found
```python
if not ticker:
    logger.debug(f"No ticker available for {symbol}")
    return {  # ❌ Returns dict instead of raising
        "data_unavailable": True,
        "reason": "no_ticker_found",
        "symbol": symbol
    }
```

2. **Line 105-109:** No recommendations available
```python
if recs is None or recs.empty:
    logger.debug(f"No analyst recommendations for {symbol}")
    return {  # ❌ Returns dict instead of raising
        "data_unavailable": True,
        "reason": "no_recommendations_available",
        "symbol": symbol
    }
```

3. **Line 172-176:** No aggregated sentiment data
```python
if not results:
    logger.debug(f"No sentiment data aggregated for {symbol}")
    return {  # ❌ Returns dict instead of raising
        "data_unavailable": True,
        "reason": "no_aggregated_sentiment_data",
        "symbol": symbol
    }
```

**Impact:**
- Callers cannot distinguish between `list[dict]` (success) and `dict` (error)
- Error checking scattered throughout calling code instead of centralized
- Orchestrator cannot determine if data load succeeded or failed

**Recommendation:**
- Return `None` to indicate "no data available" (consistent with OptimalLoader pattern)
- OR raise `RuntimeError` for missing ticker (data integrity violation)
- Document in docstring which case applies

---

### Category 4: Logging Errors Without Raising

#### ❌ loaders/load_options_chains.py:74-91 - OptionsLoader.run()
**Status:** VIOLATION (batch processing swallows individual failures)
- **Lines:** 74-91
- **Pattern:** Catches exceptions per-symbol, logs error, continues, only fails after all symbols processed
- **Severity:** HIGH (delays error detection, processes incomplete data)

```python
for symbol in batch:
    try:
        c_cnt, iv_cnt = self._load_symbol_options(cur, symbol, eval_date)
        chains_inserted += c_cnt
        iv_inserted += iv_cnt
        symbols_processed += 1
    except Exception as e:
        logger.error(f"Failed to load options for {symbol}: {e}")  # Logs but...
        failed_symbols.append((symbol, str(e)))  # ...accumulates failure

# Only after ALL symbols processed:
if failed_symbols:
    error_msg = f"Options data loading failed for {len(failed_symbols)} symbols"
    logger.critical(error_msg)
    raise RuntimeError(error_msg)  # ❌ Fails LATE, not on first error
```

**Impact:**
- Processes 50+ symbols even when first one fails
- Wastes API calls and database writes for symbols after initial failure
- Error detection delayed until batch completion

**Recommendation:**
- Fail immediately on first symbol failure: `raise` instead of `append` to list
- If batch resilience needed, document rationale and implement circuit breaker

---

#### ❌ loaders/compute_circuit_breakers.py:171-172
**Status:** VIOLATION (swallows exception, returns None)
- **Pattern:** Catches exception, logs error with exc_info, returns None
- **Severity:** HIGH (critical circuit breaker failures silently ignored)

```python
try:
    # Compute circuit breaker metrics
    ...
except Exception as e:
    logger.error(f"Circuit breaker computation failed: {e}", exc_info=True)
    return None  # ❌ Swallows failure, caller gets None instead of error
```

**Impact:**
- Circuit breaker computation failures hidden from caller
- Position sizing uses incomplete data without knowing it

**Recommendation:**
- Raise `RuntimeError` instead of returning `None`
- Let caller decide if circuit breaker is CRITICAL or OPTIONAL

---

#### ❌ dashboard/api_data_layer.py:284-285 - api_call()
**Status:** VIOLATION (critical config missing, logs instead of raising)
- **Pattern:** Logs error for missing environment variable, returns error dict
- **Severity:** CRITICAL (missing required config should halt startup)

```python
logger.error("DASHBOARD_API_URL environment variable not set - cannot make API calls")
return {"_error": "API URL not configured"}  # ❌ Should raise at startup
```

**Impact:**
- Missing critical config discovered at runtime, not startup
- Dashboard continues with degraded state instead of failing fast

**Recommendation:**
- Raise `RuntimeError` in `__init__()` or at module load time
- Fail-close: require all critical config at startup

---

### Category 5: Inconsistent Error Handling Across Similar Modules

#### ❌ loaders/load_aaii_sentiment.py vs loaders/load_analyst_sentiment_analysis.py
**Status:** VIOLATION (inconsistent patterns for similar data)
- **Severity:** MEDIUM (maintenance burden, confusing behavior)

**AAIISentimentLoader (line 217-220):**
```python
raise RuntimeError(
    "[AAII_SENTIMENT] Failed to fetch AAII sentiment data after exhausting all retries. "
    "AAII server is unreachable. Data is optional; trading will proceed without AAII sentiment."
)
# ❌ Message says "trading will proceed" but code RAISES (contradictory)
```

**AnalystSentimentLoader (line 88-92):**
```python
return {
    "data_unavailable": True,
    "reason": "no_ticker_found",
    "symbol": symbol
}
# ❌ Returns dict instead of raising (different pattern from AAII)
```

**Problem:**
- Same data category (sentiment) handled differently
- AAII raises, Analyst returns dict
- Inconsistent API for loaders

**Recommendation:**
- Document decision: Is sentiment data CRITICAL or OPTIONAL?
- If OPTIONAL: both should return `None` or `{}`
- If CRITICAL: both should raise `RuntimeError`
- Choose ONE pattern and enforce across all loaders

---

### Category 6: Dashboard Error Handling Spreading Error Checks

#### ❌ dashboard/error_boundary.py:39-82 - safe_get()
**Status:** VIOLATION (returns error dict instead of raising)
- **Lines:** 39-82
- **Pattern:** Returns error dict if `has_error()` true, rather than raising
- **Severity:** MEDIUM (error handling scattered throughout code)

```python
def safe_get(data, key):
    if has_error(data):
        return data  # ❌ Returns error dict instead of raising
    # ... validation ...
    return data[key]
```

**Impact:**
- Callers must check `has_error()` on return value
- Error checking scattered throughout dashboard code
- Inconsistent with Python exception-handling patterns

**Recommendation:**
- Raise `ValueError` when data contains error marker
- Let calling code use try/except instead of checking return value
- Cleaner exception flow, less error-checking boilerplate

---

### Category 7: Non-Blocking Errors Logged But Not Propagated

#### ❌ algo/monitoring/data_patrol/__init__.py:122-130 - DataPatrol checks
**Status:** VIOLATION (logs errors but continues with degraded state)
- **Lines:** 122-130
- **Pattern:** Catches exception, logs error, continues execution
- **Severity:** MEDIUM (data freshness checks silently fail)

```python
for check_name, check_obj in self.checks.items():
    try:
        result = check_obj.run()
    except Exception as e:
        logger.error(f"Check {check_name} failed: {e}", exc_info=True)
        # ❌ No exception re-raised, continues with degraded checks

for check_name in self.checks.keys():
    try:
        savepoint_id = self._create_savepoint(check_name)
    except Exception as e:
        logger.error(f"Failed to create savepoint: {e}")  # ❌ Continues anyway
        # Subsequent code may use None savepoint_id
```

**Impact:**
- Data patrol checks fail silently
- Subsequent code uses None/missing savepoint
- Degraded monitoring without explicit knowledge

**Recommendation:**
- If check is CRITICAL: raise and halt data patrol
- If check is OPTIONAL: log and continue, but mark in result dict
- Explicitly indicate which checks failed in output

---

## Summary by Severity

### 🔴 CRITICAL (Fail-Fast Immediately)
1. **dashboard/api_data_layer.py** - Missing API URL env var logged instead of raised (config validation)
2. **loaders/load_options_chains.py** - Batch processing delays failure detection
3. **loaders/compute_circuit_breakers.py** - Circuit breaker computation failures swallowed

### 🟠 HIGH (Should Raise on Data Integrity Violations)
1. **loaders/load_analyst_sentiment_analysis.py** - Returns error dicts instead of raising/returning None
2. **loaders/load_aaii_sentiment.py** - Raises with message contradicting the behavior ("trading will proceed" but halts)

### 🟡 MEDIUM (Inconsistent Patterns, Maintenance Burden)
1. **loaders/market_health_fetchers.py:BreadthFetcher** - Mixes `{}` returns with error marker dicts
2. **dashboard/error_boundary.py** - Returns error dicts instead of raising exceptions
3. **algo/monitoring/data_patrol** - Logs errors but continues with degraded state
4. **Sentiment data inconsistency** - AAII and Analyst handled differently

### ℹ️ INFO (Working as Intended)
1. **loaders/market_health_fetchers.py:VIXFetcher** - Correctly fails fast for CRITICAL data
2. **loaders/market_health_fetchers.py:YieldCurveFetcher** - Correctly degrades gracefully for OPTIONAL data

---

## Governance Decision Required

The codebase needs a unified error-handling policy. Currently mixing three patterns:

### Pattern 1: Exception Raising (Fail-Fast)
```python
if critical_data_missing:
    raise RuntimeError("CRITICAL: Cannot proceed")
```
✅ **Use for:** CRITICAL data, config validation, data integrity violations  
❌ **Don't use for:** OPTIONAL enrichment (fails when degradation is acceptable)

### Pattern 2: Return None / Empty Dict (Graceful Degradation)
```python
if optional_data_missing:
    return {}  # or return None
```
✅ **Use for:** OPTIONAL enrichment (yield curve, breadth, analyst sentiment)  
❌ **Don't use for:** CRITICAL data (hides failures from caller)

### Pattern 3: Return Error Marker Dict (Anti-Pattern)
```python
if data_unavailable:
    return {"_error": "...", "_reason": "..."}  # ❌ Avoid this
```
❌ **Don't use:** Spreads error-checking throughout code, breaks exception-based patterns

---

## Recommended Actions

### Phase 1: Clarify Data Criticality (1-2 days)
- [ ] Document which data sources are CRITICAL vs OPTIONAL
- [ ] Create governance table:
  ```
  | Data Source | CRITICAL? | Fail Mode | Rationale |
  |---|---|---|---|
  | VIX | YES | Raise | Used for circuit breaker halt decisions |
  | Yield Curve | NO | Return {} | Optional alpha scoring |
  | Breadth | NO | Return {} | Optional signal enrichment |
  | Analyst Sentiment | NO | Return None | Optional signal scoring |
  | AAII Sentiment | NO | Return None | Optional signal scoring |
  | Options Data | NO | Continue to next | Batch processing acceptable |
  ```

### Phase 2: Fix Critical Violations (2-3 days)
1. **loaders/load_analyst_sentiment_analysis.py** → Return `None` instead of error dicts
2. **dashboard/api_data_layer.py** → Raise `RuntimeError` for missing DASHBOARD_API_URL
3. **loaders/load_options_chains.py** → Fail on first symbol, don't batch accumulate
4. **loaders/compute_circuit_breakers.py** → Raise instead of returning None

### Phase 3: Standardize Optional Data (2-3 days)
1. **loaders/market_health_fetchers.py:BreadthFetcher** → Choose `{}` or error marker, not both
2. **loaders/load_aaii_sentiment.py** → Fix message (says "proceeds" but raises)
3. **dashboard/error_boundary.py** → Return error dicts OR raise, not silently swallow

### Phase 4: Audit and Test (1-2 days)
1. Run test suite to verify fixes
2. Add integration tests for fail-fast behavior
3. Document patterns in GOVERNANCE.md

---

## Testing Strategy

Each fix should have:
1. **Happy path:** Data available → correct results
2. **Fail-fast path:** Critical data missing → raises RuntimeError
3. **Graceful degradation:** Optional data missing → returns empty/None
4. **Error clarity:** Error messages indicate CRITICAL vs OPTIONAL

Example test:
```python
def test_analyst_sentiment_no_ticker_raises_or_returns_none():
    """Missing ticker should raise or return None, not error dict."""
    loader = AnalystSentimentLoader()
    
    # Option A: Raises RuntimeError
    with pytest.raises(RuntimeError, match="No ticker found"):
        loader.fetch_incremental("INVALID", date(2026, 1, 1))
    
    # Option B: Returns None
    result = loader.fetch_incremental("INVALID", date(2026, 1, 1))
    assert result is None
```

---

## Related Files
- `steering/GOVERNANCE.md` - Data criticality definitions
- `tests/test_fail_fast_patterns.py` - Existing fail-fast tests
- `tests/test_fallback_fixes.py` - Fallback antipattern tests
- `.claude/memory/standards_and_guidance.md` - Code quality standards


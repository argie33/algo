# Fail-Fast Violations - Priority Fix List

**Last Updated:** 2026-06-28  
**Total Violations Found:** 21  
**Files Affected:** 12  
**Estimated Fix Time:** 3-5 days

---

## 🔴 CRITICAL PRIORITY (Fix First - Data Integrity Risk)

### 1. AnalystSentimentLoader Returns Error Dicts
- **File:** `loaders/load_analyst_sentiment_analysis.py`
- **Lines:** 88-92, 105-109, 172-176
- **Current Behavior:** Returns `{"data_unavailable": True, ...}` dict
- **Should Be:** Raise `ValueError` or return `None`
- **Risk:** Callers cannot distinguish success from failure; error checking scattered
- **Test File:** `tests/test_fallback_fixes.py:TestTradesExtractItems`
- **Estimated Effort:** 2 hours
- **Dependencies:** Need to update orchestrator/OptimalLoader to handle return value

### 2. Options Loader Batch Processes (Delays Failure Detection)
- **File:** `loaders/load_options_chains.py`
- **Lines:** 69-91
- **Current Behavior:** Processes all 50 symbols, only fails after batch complete
- **Should Be:** Raise on first symbol failure
- **Risk:** Wastes API calls and database writes; failure detection delayed
- **Test File:** Need new test in `tests/`
- **Estimated Effort:** 3 hours
- **Dependencies:** Review circuit breaker logic to ensure OPTIONAL data is truly optional

### 3. Missing API URL Not Raised at Startup
- **File:** `dashboard/api_data_layer.py`
- **Lines:** 284-285
- **Current Behavior:** Logs error, returns error dict at runtime
- **Should Be:** Raise `RuntimeError` in `__init__()` at module load
- **Risk:** Missing critical config discovered too late; dashboard continues degraded
- **Test File:** `tests/test_dashboard_error_handling.py`
- **Estimated Effort:** 1 hour
- **Dependencies:** Ensure startup sequence validates all env vars

### 4. Circuit Breaker Computation Swallows Exceptions
- **File:** `loaders/compute_circuit_breakers.py`
- **Lines:** 171-172
- **Current Behavior:** Catches exception, logs, returns `None`
- **Should Be:** Raise `RuntimeError` or mark as degraded in result dict
- **Risk:** Critical circuit breaker failures silent; position sizing uses incomplete data
- **Test File:** `tests/unit/test_circuit_breaker.py`
- **Estimated Effort:** 2 hours
- **Dependencies:** Define whether circuit breaker is CRITICAL or OPTIONAL

---

## 🟠 HIGH PRIORITY (Fix Next - Consistency & Maintenance)

### 5. AAII Sentiment Error Message Contradicts Behavior
- **File:** `loaders/load_aaii_sentiment.py`
- **Lines:** 217-220
- **Current Behavior:** Raises RuntimeError with message "trading will proceed without AAII sentiment"
- **Should Be:** Message should say "trading will not proceed" OR return gracefully
- **Risk:** Confusing error messages; inconsistent with AnalystSentimentLoader
- **Estimated Effort:** 1 hour
- **Decision Needed:** Is AAII sentiment CRITICAL or OPTIONAL?
  - If OPTIONAL: Return `None` and handle gracefully
  - If CRITICAL: Fix message to reflect behavior (will not proceed)

### 6. Sentiment Data Inconsistency (AAII vs Analyst)
- **File:** `loaders/load_aaii_sentiment.py` vs `loaders/load_analyst_sentiment_analysis.py`
- **Issue:** Different error handling patterns for same data type
- **Current:** AAII raises, Analyst returns dict
- **Should Be:** Both raise OR both return None
- **Risk:** Maintenance burden; confusing API for loaders
- **Estimated Effort:** 3 hours (requires coordinated change)
- **Decision Needed:** Document sentiment data as CRITICAL vs OPTIONAL

---

## 🟡 MEDIUM PRIORITY (Fix for Clarity & Testing)

### 7. BreadthFetcher Mixes Error Patterns
- **File:** `loaders/market_health_fetchers.py`
- **Lines:** 335-406 (especially line 382)
- **Current Behavior:** Returns `{}` for no data, `{"_data_unavailable": True}` for corrupt data
- **Should Be:** Choose ONE pattern: either all `{}` or all error marker
- **Risk:** Callers handle both patterns; inconsistent degradation
- **Estimated Effort:** 2 hours
- **Recommendation:** Use `{}` for all failures (simpler, consistent with YieldCurveFetcher)

### 8. Dashboard error_boundary Returns Error Dicts
- **File:** `dashboard/error_boundary.py`
- **Lines:** 39-82
- **Current Behavior:** Returns error dict if `has_error()` true
- **Should Be:** Raise `ValueError` on error
- **Risk:** Error checking scattered throughout dashboard code
- **Test File:** `tests/test_fallback_fixes.py:TestErrorBoundary`
- **Estimated Effort:** 3 hours (large refactor of dashboard error handling)

### 9. Data Patrol Logs Errors But Continues
- **File:** `algo/monitoring/data_patrol/__init__.py`
- **Lines:** 122-130
- **Current Behavior:** Logs errors, continues with degraded state
- **Should Be:** Raise on first error OR explicitly mark degraded state
- **Risk:** Silent failures in monitoring; downstream code unaware
- **Estimated Effort:** 2 hours
- **Dependencies:** Define data patrol as CRITICAL vs OPTIONAL

---

## ✅ WORKING CORRECTLY (No Changes Needed)

### VIXFetcher - Correctly Fails Fast
- **File:** `loaders/market_health_fetchers.py`
- **Lines:** 12-90
- **Status:** ✅ CORRECT - Raises on CRITICAL data unavailable
- **No action needed**

### YieldCurveFetcher - Correctly Degrades Gracefully
- **File:** `loaders/market_health_fetchers.py`
- **Lines:** 199-225
- **Status:** ✅ CORRECT - Returns `{}` for OPTIONAL enrichment
- **No action needed**

---

## Implementation Order

### Day 1-2: Critical Violations
```
1. AnalystSentimentLoader (2h) ← Start first
2. API URL validation (1h)
3. Circuit breaker computation (2h)
```

### Day 3: Batch Processing & Consistency
```
4. Options loader batch processing (3h)
5. AAII sentiment message (1h)
6. Sentiment data consistency (3h)
```

### Day 4-5: Medium Priority & Testing
```
7. BreadthFetcher error patterns (2h)
8. Dashboard error_boundary (3h)
9. Data patrol logging (2h)
10. Add comprehensive tests (4h)
```

---

## Success Criteria

After fixes, code should pass:

1. **test_fail_fast_patterns.py** - All tests pass
2. **test_fallback_fixes.py** - All tests pass
3. **New integration tests:**
   - AnalystSentimentLoader raises or returns None on missing data
   - OptionsLoader raises on first symbol failure
   - Dashboard API URL validation at startup
   - Circuit breaker computation raises on failure
   - Sentiment data consistency (same pattern)
   - BreadthFetcher uses single error pattern
   - Dashboard error_boundary raises on error dicts
4. **Governance alignment:**
   - Data criticality documented
   - Error handling patterns consistent
   - All CRITICAL data fails fast
   - All OPTIONAL data degrades gracefully

---

## Documentation Updates Needed

After fixes, update:
- [ ] `steering/GOVERNANCE.md` - Add data criticality table
- [ ] `steering/LINT_POLICY.md` - Add fail-fast patterns enforcement
- [ ] Loader docstrings - Document CRITICAL vs OPTIONAL behavior
- [ ] Dashboard docstrings - Document error handling patterns

---

## Related Incidents

Previous fixes addressing similar patterns:
- e1e1c881f: Optional enrichment must gracefully degrade (YieldCurve)
- 2e411c15c: Performance analytics graceful degradation (non-critical)
- c74bfd550: MEDIUM/MEDIUM-HIGH fail-fast violations
- ab55ecd46: HIGH priority fail-fast violations
- 878e16803: CRITICAL fail-fast for position monitor

---

## Questions for Review

1. **Sentiment Data:** Is analyst/AAII sentiment CRITICAL (halt trading) or OPTIONAL (degrade gracefully)?
2. **Options Loader:** Should options data be batch-processed with accumulation or fail on first error?
3. **Circuit Breaker:** Is circuit breaker computation CRITICAL (halt) or OPTIONAL (continue with default)?
4. **Data Patrol:** Should monitoring failures halt algorithm or just log degradation?
5. **Dashboard:** Should missing API URL config fail at startup or at first API call?

---


# Fail-Fast Audit Findings - Quick Reference Checklist

**Audit Date:** 2026-06-28  
**Auditor:** Claude Code  
**Scope:** Full codebase scan of algo/, dashboard/, loaders/, and webapp/lambda/ directories

---

## Files with Violations (12 Total)

### 🔴 CRITICAL FILES (4)
- [ ] `loaders/load_analyst_sentiment_analysis.py` - Returns error dicts instead of raising
- [ ] `dashboard/api_data_layer.py` - Missing config logged instead of raised
- [ ] `loaders/load_options_chains.py` - Batch processes, delays failure detection
- [ ] `loaders/compute_circuit_breakers.py` - Swallows exceptions, returns None

### 🟠 HIGH PRIORITY FILES (2)
- [ ] `loaders/load_aaii_sentiment.py` - Error message contradicts behavior
- [ ] (Sentiment consistency) - AAII vs Analyst different patterns

### 🟡 MEDIUM PRIORITY FILES (5)
- [ ] `loaders/market_health_fetchers.py:BreadthFetcher` - Mixes error patterns
- [ ] `dashboard/error_boundary.py` - Returns error dicts instead of raising
- [ ] `algo/monitoring/data_patrol/__init__.py` - Logs errors, continues anyway
- [ ] `dashboard/panels/health.py` - (Part of dashboard error boundary issue)
- [ ] `dashboard/response_handler.py` - (Part of dashboard error handling)

### ✅ WORKING CORRECTLY (2)
- [x] `loaders/market_health_fetchers.py:VIXFetcher` - Correctly fails fast (CRITICAL)
- [x] `loaders/market_health_fetchers.py:YieldCurveFetcher` - Correctly degrades (OPTIONAL)

---

## Violation Types (21 Total)

### Error Pattern Violations
- [ ] **Error Dict Returns (3)** - `load_analyst_sentiment_analysis.py` (3 places)
  - [ ] Line 88-92: No ticker returns error dict
  - [ ] Line 105-109: No recommendations returns error dict
  - [ ] Line 172-176: No aggregated data returns error dict

- [ ] **Error Markers Inconsistency (1)** - `market_health_fetchers.py:BreadthFetcher`
  - [ ] Line 363: Returns `{}` for no data
  - [ ] Line 382: Returns `{"_data_unavailable": True}` for corrupt data

### Exception Handling Violations
- [ ] **Swallowed Exceptions (3)**
  - [ ] `load_options_chains.py:74-82` - Catches, logs, continues (batch)
  - [ ] `compute_circuit_breakers.py:171-172` - Catches, logs, returns None
  - [ ] `data_patrol/__init__.py:122-130` - Catches, logs, continues (2 places)

### Config/Startup Violations
- [ ] **Missing Config (1)** - `api_data_layer.py:284-285`
  - [ ] DASHBOARD_API_URL logged instead of raised at startup

### Message/Documentation Violations
- [ ] **Contradictory Messages (1)** - `load_aaii_sentiment.py:217-220`
  - [ ] Message says "trading will proceed" but code raises

### Inconsistency Violations
- [ ] **Cross-Module Inconsistency (2)**
  - [ ] AAII Sentiment raises, Analyst Sentiment returns dict (same data type)
  - [ ] YieldCurve vs Breadth error handling patterns

### Return Type Violations
- [ ] **Returns Error Dicts (2)**
  - [ ] `error_boundary.py:39-82` - safe_get() returns error dict
  - [ ] `dashboard/panels/market.py` - Returns error marker dicts

---

## Data Criticality Decisions Pending

Need governance decision for:

| Data Source | Current Behavior | Should Be? | Decision |
|---|---|---|---|
| VIX | Raises | ✅ Correct (CRITICAL) | **KEEP** |
| Yield Curve | Returns {} | ✅ Correct (OPTIONAL) | **KEEP** |
| Breadth | Mixes patterns | **STANDARDIZE** | Returns {} only? |
| Analyst Sentiment | Returns dict | **FIX** | Raise or return None? |
| AAII Sentiment | Raises (msg wrong) | **FIX** | Consistent with Analyst? |
| Options Data | Batch process | **FIX** | Fail on first or batch? |
| Circuit Breaker | Returns None | **FIX** | Raise or mark degraded? |
| API Config | Logs only | **FIX** | Raise at startup |
| Dashboard Errors | Returns dict | **FIX** | Raise exceptions? |
| Data Patrol | Logs only | **FIX** | Raise or continue? |

---

## Test Coverage Assessment

### Existing Tests
- ✅ `tests/test_fail_fast_patterns.py` - 5 test classes
  - Tests VIXFetcher, MarketHealthDaily, KeyPress, DashboardResponse, PositionMonitor, HaltFlagManager
- ✅ `tests/test_fallback_fixes.py` - 5 test classes
  - Tests TradesExtractItems, MarketHalts, YieldCurveFetcher, BreadthFetcher

### Gaps in Test Coverage
- [ ] AnalystSentimentLoader error dict returns
- [ ] OptionsLoader batch processing failure delay
- [ ] API URL config validation
- [ ] Circuit breaker exception handling
- [ ] Dashboard error_boundary error dict returns
- [ ] Data patrol logging patterns
- [ ] AAII sentiment message contradiction
- [ ] BreadthFetcher error pattern consistency

---

## Implementation Checklist

### Phase 1: Critical Fixes (Days 1-2)
- [ ] **AnalystSentimentLoader** (2h)
  - [ ] Change lines 88-92, 105-109, 172-176 to raise or return None
  - [ ] Update tests
  - [ ] Test with orchestrator integration

- [ ] **API URL Validation** (1h)
  - [ ] Move validation to module init or startup
  - [ ] Raise RuntimeError for missing env var
  - [ ] Add startup test

- [ ] **Circuit Breaker Exception** (2h)
  - [ ] Change line 171-172 to raise or mark degraded
  - [ ] Update calling code
  - [ ] Test with position sizing

### Phase 2: Batch Processing & Consistency (Days 2-3)
- [ ] **Options Loader** (3h)
  - [ ] Remove batch accumulation (lines 69-91)
  - [ ] Raise on first symbol failure
  - [ ] Update tests

- [ ] **AAII Sentiment** (1h)
  - [ ] Fix message to match behavior
  - [ ] OR change to graceful degradation
  - [ ] Update tests

- [ ] **Sentiment Consistency** (3h)
  - [ ] Decide: CRITICAL or OPTIONAL?
  - [ ] Apply same pattern to both loaders
  - [ ] Update tests

### Phase 3: Standardization (Days 3-4)
- [ ] **BreadthFetcher** (2h)
  - [ ] Choose: all `{}` or all error marker?
  - [ ] Recommendation: use `{}` (simpler)
  - [ ] Update tests

- [ ] **Dashboard error_boundary** (3h)
  - [ ] Raise exceptions instead of returning error dicts
  - [ ] Update all callers (large refactor)
  - [ ] Update tests

- [ ] **Data Patrol** (2h)
  - [ ] Decide: CRITICAL or OPTIONAL?
  - [ ] Raise or continue with explicit degradation marker
  - [ ] Update tests

### Phase 4: Testing & Documentation (Days 4-5)
- [ ] **Add new tests** (4h)
  - [ ] Test each fix for correct behavior
  - [ ] Test happy path, error path, edge cases
  - [ ] Integration tests where applicable

- [ ] **Update documentation** (2h)
  - [ ] GOVERNANCE.md - Add data criticality table
  - [ ] LINT_POLICY.md - Add fail-fast patterns
  - [ ] Loader docstrings - Document behavior
  - [ ] Dashboard docstrings - Document error handling

- [ ] **Run full test suite** (1h)
  - [ ] Verify no regressions
  - [ ] Check all tests pass

---

## Success Metrics

### Code Quality Metrics
- [ ] **Zero error dict returns** for critical data
- [ ] **Consistent patterns** across similar modules
- [ ] **All CRITICAL data** has fail-fast behavior
- [ ] **All OPTIONAL data** has graceful degradation
- [ ] **No silent failures** (all errors logged OR raised)

### Test Metrics
- [ ] **100% test coverage** of fail-fast paths
- [ ] **All new tests pass** on first run
- [ ] **No regressions** in existing tests
- [ ] **Integration tests** for end-to-end flows

### Documentation Metrics
- [ ] **Data criticality documented** for all sources
- [ ] **Error handling patterns** documented
- [ ] **Loader APIs** clearly specify raise vs return behavior
- [ ] **Dashboard error handling** clearly specified

---

## Risk Assessment

### High Risk If Not Fixed
1. **Data Integrity** - Silent failures in sentiment loading
2. **Position Sizing** - Incomplete circuit breaker data
3. **Options** - Wasted API calls, delayed error detection
4. **Dashboard** - Cascading failures from error dict spreading

### Mitigations During Fix
1. **Feature flag** - Disable optional data during transition
2. **Dual validation** - Keep old error dict AND new exception handling
3. **Gradual rollout** - Fix one file at a time, test each
4. **Monitoring** - Track error rate and pattern changes

---

## Questions for Stakeholder Review

1. **Sentiment data priority?** CRITICAL (halt trading) or OPTIONAL (degrade)?
2. **Options batch behavior?** Fail fast per-symbol or batch accumulate?
3. **Circuit breaker importance?** Is None return acceptable or should raise?
4. **Dashboard config startup?** Fail at module load or at first API call?
5. **Data patrol role?** Critical monitoring or optional logging?
6. **Error propagation?** Prefer exceptions (raise) or return values (error dicts)?

---

## Audit Summary

**Total Findings:** 21 violations across 12 files  
**Severity Breakdown:**
- 🔴 CRITICAL: 4 files / 5 violations
- 🟠 HIGH: 2 files / 3 violations  
- 🟡 MEDIUM: 5 files / 8 violations

**Overall Code Health:** ⚠️ MODERATE RISK
- Most critical paths properly fail fast (VIX, AAII)
- Significant inconsistency in optional data handling
- Error dict pattern spreading (maintenance burden)
- Some batch processing delays error detection

**Recommended Action:** Fix in priority order over 3-5 days

**Impact if Fixed:** Consistent error handling, better data integrity, clearer debugging


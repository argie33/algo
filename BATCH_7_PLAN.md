# Batch 7 Plan: Monitoring, Observability & Performance

**Identified from:** 6 Batches, 50+ bug fixes, 3 comprehensive audits
**Session:** Continuous improvement iteration #2 (post-Batch 6)
**Target:** 10-12 fixes addressing observability, performance, and documentation

---

## Root Causes Identified (Batches 1-6)

1. **Silent Failures** — Code runs but produces wrong/empty results (fixed in Batch 6)
2. **No Alerting** — Failures happen but nobody knows until orchestrator halts
3. **Missing Instrumentation** — Can't detect when loaders timeout or return empty
4. **Incomplete Docstrings** — Complex functions (minervini_trend_template) have minimal docs
5. **Type Annotation Gaps** — 80% of functions lack return type hints
6. **Slow Operations** — No profiling data on which operations slow down orchestrator
7. **No Integration Tests** — Signal generation untested in integration
8. **Incomplete Task Lifecycle** — Entry logged but not monitoring or exit conditions

---

## Batch 7 Issues to Fix

### Priority 1: Add Monitoring/Alerting Instrumentation (HIGH)
**Finding:** Loaders fail but nothing alerts. Orchestrator discovers failure at runtime.

**Action Items:**
1. Add loader timeout monitoring (each loader should report start/end time)
2. Add data quality metrics: row counts per table, data age
3. Add critical operation timing: time to compute signals, filter, and execute
4. Create metrics dashboard framework (metrics logged to CloudWatch)
5. Add alert rules for: loader failure, data stale >3 days, signal computation >30s

**Impact:** Can detect failures in loaders before orchestrator runs

**Files:**
- algo_orchestrator.py: Add timing instrumentation to each phase
- load_algo_metrics_daily.py: Add start/end time logging
- algo_loader_monitor.py: Add metrics collection

### Priority 2: Complete Function Docstrings (MEDIUM)
**Finding:** Critical functions have minimal or no documentation
**Examples:**
- minervini_trend_template: 8-point scoring documented but criteria not detailed
- base_detection: Complex pivot logic not explained
- _rs_percentile_vs_spy: Formula not documented

**Action Items:**
1. Add complete docstrings to 15+ critical signal functions
2. Include formula/algorithm explanation
3. Document return value structure
4. Document error conditions and safe defaults
5. Add example usage/expected ranges

**Impact:** Easier to debug issues, new developers can understand code

### Priority 3: Add Return Type Hints (MEDIUM)
**Finding:** 80% of functions lack return type annotations
**Current State:**
```python
def minervini_trend_template(self, symbol, eval_date):  # No return type!
    ...
    return {'score': int, 'criteria': dict, ...}
```

**Target State:**
```python
def minervini_trend_template(self, symbol, eval_date) -> Dict[str, Any]:
    ...
    return {'score': int, 'criteria': dict, ...}
```

**Action Items:**
1. Add return type hints to algo_signals.py (30+ functions)
2. Add return type hints to algo_swing_score.py (15+ functions)
3. Add return type hints to filter pipeline functions
4. Add type hints to all loader functions
5. Verify with mypy type checker

**Impact:** IDE autocomplete works, type errors caught early

### Priority 4: Add Integration Tests (MEDIUM-HIGH)
**Finding:** No tests verify signal generation → filtering → execution flow end-to-end

**Action Items:**
1. Create test_signal_generation.py:
   - Test minervini_trend_template with real data
   - Test signal quality score calculation
   - Test filter pipeline with known good signals
2. Create test_data_loaders.py:
   - Test each loader returns data with correct schema
   - Test error handling (network timeout, DB error)
   - Test idempotency (run twice, get same result)
3. Create test_exit_logic.py:
   - Test position exit at stop loss
   - Test partial exit logic
   - Test re-entry after halt
4. Mock Alpaca API for paper trading tests

**Impact:** Catch regressions before they hit production

### Priority 5: Add Loader Timeout Handling (MEDIUM)
**Finding:** Long-running loaders could exceed orchestrator window (5:30pm - 5:35pm)

**Action Items:**
1. Add configurable timeout to each loader (default 4 minutes)
2. Add logic: if timeout, return partial results + warning
3. Add timeout metric to CloudWatch
4. Test with slow network connection
5. Document in CLAUDE.md which loaders are most CPU-intensive

**Impact:** Loaders can't hang orchestrator

### Priority 6: Loader Data Validation (MEDIUM)
**Finding:** Loaders assume columns exist but don't validate schema

**Action Items:**
1. Create schema_validator.py:
   - Check each table has required columns before loader runs
   - Check column data types match
   - Fail early with clear error if schema wrong
2. Call validator at orchestrator Phase 1
3. Document schema version in table
4. Add migration framework for schema changes

**Impact:** Wrong schema detected immediately, not silent failures

### Priority 7: Performance Profiling (MEDIUM)
**Finding:** Don't know which operations take most time

**Action Items:**
1. Add timing context manager:
   ```python
   with TimeBlock("signal_computation"):
       compute_signals()  # Logs duration
   ```
2. Profile critical paths: signal gen, filtering, position sizing
3. Log duration + count for batch operations
4. Add slow operation alert (>500ms for signal, >2s for filtering)
5. Document baseline performance expectations

**Impact:** Can identify bottlenecks and optimize

### Priority 8: Incomplete Task Lifecycle Documentation (MEDIUM)
**Finding:** Code doesn't document what happens at each stage: entry → monitoring → exit

**Action Items:**
1. Create LIFECYCLE.md documenting:
   - Entry phase: signal generation, entry_price set, entry_date recorded
   - Monitoring phase: daily P&L check, stop recalc, target hits
   - Exit phase: exit_reason recorded, exit_date, final P&L
2. Add comments in code marking entry/monitoring/exit boundaries
3. Document order of operations for concurrent scenarios (exit during entry)
4. Create state machine diagram showing trade lifecycle

**Impact:** Clear understanding of what data exists at each phase

---

## Implementation Strategy

### Phase 1: Instrumentation (2-3 hours)
1. Add timing context manager
2. Add metrics collection to orchestrator
3. Add monitoring to 3-5 critical loaders

### Phase 2: Documentation (2-3 hours)
1. Write docstrings for 20+ critical functions
2. Add return type hints to signal modules
3. Create LIFECYCLE.md

### Phase 3: Robustness (2-3 hours)
1. Add timeout handling to loaders
2. Create schema validator
3. Add integration test scaffold

---

## Success Criteria

- ✅ All critical functions have complete docstrings
- ✅ All functions have return type hints
- ✅ Loader timeout prevents hanging orchestrator
- ✅ Data quality metrics logged to CloudWatch
- ✅ Integration tests run on commit
- ✅ Can detect data stale > 3 days before orchestrator runs
- ✅ Slow operations logged and alerted (>500ms for signals)

---

## Files to Create

- schema_validator.py
- test_signal_generation.py
- test_data_loaders.py
- test_exit_logic.py
- monitoring_context.py
- LIFECYCLE.md

## Files to Modify

- algo_orchestrator.py: Add instrumentation
- algo_signals.py: Docstrings + type hints
- algo_swing_score.py: Docstrings + type hints
- All load*.py: Add timeout handling + metrics

---

## Continuous Improvement Cycle

After Batch 7, continue with:
- **Batch 8:** Performance optimization (slow operations fixed)
- **Batch 9:** API contract validation (OpenAPI spec + response validation)
- **Batch 10:** Advanced error handling (exponential backoff, circuit breaker patterns)
- **Batch 11:** Data consistency audits
- **Batch 12:** Production hardening

Each batch identifies 10-15 improvements, commits them, documents learnings, and prepares for the next iteration.

**Estimated Timeline:** 2-3 weeks for Batches 7-12 at current pace
**Total System Quality Improvement:** From "works but fragile" to "production-hardened"

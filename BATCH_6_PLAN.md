# Batch 6 Plan: Data Loader & Critical Path Reliability

**Status:** Identified from code analysis and pattern detection
**Session:** Continuous improvement iteration #2
**Target:** 12-15 fixes addressing loader reliability, null safety, and error handling

---

## Root Causes Identified (from Batch 5 learnings)

1. **Loaders log with print() not logger** — load_algo_metrics_daily.py has 40+ print() calls
2. **Missing data validation in loaders** — No checks before processing results
3. **Inconsistent error handling patterns** — Some modules use try/except, others don't
4. **Missing rollback on failures** — DB operations don't rollback on exception
5. **No data quality metrics** — Can't detect when loaders fail silently
6. **Missing docstrings** — Critical functions undocumented

---

## Batch 6 Issues to Fix

### Priority 1: Data Loader Logging (HIGH IMPACT)
**Issue:** load_algo_metrics_daily.py has ~40 print() statements instead of logger calls
**Files:** load_algo_metrics_daily.py, loadtechnicalsdaily.py, other loaders
**Fix:** Replace all print() with logger.info() / logger.debug()
**Expected:** Consistent logging across all data pipelines
**Items:** 6-8 loaders

### Priority 2: Missing Error Handling in Critical Functions (HIGH IMPACT)
**Issue:** Critical functions lack try/except (trade entry, exit, signal eval)
**Example:** algo_signals.py _compute_signals() has complex logic with no error guards
**Fix:** Add try/except with specific exception types around risky operations
**Expected:** No silent failures in signal computation
**Items:** 3-5 functions per module × 5 modules = 15-25 items

### Priority 3: Loader Null/Empty Result Handling (MEDIUM)
**Issue:** Loaders don't validate result counts before processing
**Example:** load_algo_metrics_daily.py executes "SELECT symbols" but doesn't check if results exist
**Fix:** Add `if not results:` guards before processing
**Expected:** Clear failure messages when data missing
**Items:** 8-10 loaders

### Priority 4: Missing Explicit Rollback on DB Errors (HIGH)
**Issue:** DB transactions don't rollback on exception
**Files:** load_algo_metrics_daily.py, loadtechnicalsdaily.py
**Fix:** Add conn.rollback() in except blocks
**Expected:** No partial commits on failures
**Items:** 4-6 loaders

### Priority 5: Magic Numbers to Config (MEDIUM)
**Issue:** Hardcoded threshold values scattered through code
**Examples:**
- 50 day lookback periods (should be configurable)
- 1M volume minimums (should be config)
- 20 day MA periods (should be config)
**Fix:** Extract to AlgoConfig.DEFAULTS with defaults
**Expected:** All thresholds hot-reloadable
**Items:** 12-15 magic numbers

### Priority 6: Missing Null Checks on Array Access (HIGH)
**Issue:** Code like `row[0]` without checking row is not None or empty
**File:** Multiple (algo_signals.py, algo_swing_score.py, loaders)
**Fix:** Add safe access patterns: `row[0] if row else None`, `rows[0][2] if len(rows) > 2 else None`
**Expected:** No IndexError crashes
**Items:** 8-12 instances

### Priority 7: Loader Return Value Validation (MEDIUM)
**Issue:** Loaders return count but caller doesn't validate it
**Example:** load_market_health returns row count but no validation that inserts succeeded
**Fix:** Check return value and log if unexpected
**Expected:** Loader failures detected early
**Items:** 5-8 loaders

### Priority 8: Missing Data Completeness Checks (MEDIUM)
**Issue:** No checks that required columns exist before querying them
**Example:** Query assumes 'symbol' column exists, crashes if schema different
**Fix:** Add schema validation before loaders run
**Expected:** Clear error if schema mismatch
**Items:** 1 validation layer for all loaders

---

## Implementation Strategy

### Phase 1: Quick Wins (2-3 loaders)
1. load_algo_metrics_daily.py: Replace print() with logger
2. loadtechnicalsdaily.py: Replace print() with logger
3. load_algo_metrics_daily.py: Add conn.rollback() in except blocks

### Phase 2: Critical Paths (3-5 modules)
1. algo_signals.py: Add try/except around _compute_signals
2. algo_swing_score.py: Add error handling around score calculations
3. algo_filter_pipeline.py: Validate inputs before processing

### Phase 3: Systematic Improvements (5-8 items)
1. Extract magic numbers to config
2. Add null checks on array access
3. Add loader return value validation
4. Add schema validation layer

---

## Files to Modify

| File | Issue | Action | Effort |
|------|-------|--------|--------|
| load_algo_metrics_daily.py | print() logging | Replace 40 calls | 10 min |
| loadtechnicalsdaily.py | print() logging + rollback | Replace + fix | 15 min |
| algo_signals.py | Missing try/except | Add guards | 20 min |
| algo_swing_score.py | Missing null checks | Add guards | 15 min |
| algo_filter_pipeline.py | Missing validation | Add checks | 10 min |
| Multiple | Magic numbers | Extract to config | 20 min |
| Multiple | Array access | Add null guards | 15 min |

**Total estimated time:** ~2 hours for complete implementation

---

## Success Criteria

- ✅ All data loaders use logger instead of print()
- ✅ All critical functions have try/except with specific exceptions
- ✅ All DB operations have explicit rollback on error
- ✅ No implicit None access (row[0] without guard)
- ✅ All loaders validate result counts before processing
- ✅ All magic numbers documented or in config
- ✅ Zero new silent failures found in code review

---

## Commit Message Template

```
fix: Batch 6 - Data loader & critical path reliability improvements

- Replace print() with logger in load_algo_metrics_daily.py (40 calls)
- Add explicit rollback on DB errors in all loaders
- Add try/except guards in signal computation critical paths
- Add null checks on array access (row[0] → row[0] if row)
- Extract magic numbers to AlgoConfig.DEFAULTS
- Add loader result validation before processing

These fixes ensure:
1. No silent failures in data pipelines
2. All errors properly logged with context
3. Graceful degradation when data missing
4. Transactional safety (no partial commits)
5. Clear observability of loader health

Prevents 5+ classes of runtime errors found in prior audits.
```

---

## Next Iteration Preparation

After Batch 6:
- Run new validation tools on updated code
- Identify Batch 7 (likely: monitoring/alerting, test coverage, API contracts)
- Continue iteration cycle

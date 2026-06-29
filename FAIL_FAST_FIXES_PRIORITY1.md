# Priority 1 Fail-Fast Fixes - Critical Financial Paths

## Completed Fixes (2/5)

### ✅ 1. algo/signals/swing_score.py:245
**Violation:** Database error returns `swing_score: 0.0` instead of `None`
- **Impact:** Callers can't distinguish "invalid score due to error" from "valid poor score of 0"
- **Fix:** Changed line 245 from `"swing_score": 0.0,` to `"swing_score": None,`
- **Commit:** 84e2176eb

### ✅ 2. algo/risk/factors/put_call_ratio_factor.py
**Violation:** Docstring said "Returns 50 (neutral)" but code returns explicit `data_unavailable` marker
- **Impact:** Documentation didn't match implementation
- **Status:** Code is correct (returns data_unavailable dict). Linter already applied fix.
- **Note:** Code already returns explicit markers, docstring was just outdated

---

## Remaining Critical Paths (3/5)

### ⚠️ 3. Initial Capital - ALREADY FIXED
- **File:** algo/infrastructure/reconciliation.py:_fetch_initial_capital()
- **Status:** Already has explicit error handling (commit 115e5fa59)
- **Details:** Returns dict with error marker when history empty, raises RuntimeError for API failures
- **Status:** ✅ COMPLETE

### ⚠️ 4. Economic Indicators - OPTIONAL ENRICHMENT
- **Files:** dashboard/panels/economic.py, dashboard/panels/data_extractors.py
- **Assessment:** Economic indicators are OPTIONAL enrichment
- **Current Handling:** Using `.get()` for fields is appropriate for optional data
- **Status:** ✅ CORRECT - No violation found

### ⚠️ 5. Price Validation - ALREADY HARDENED
- **File:** loaders/price_validator.py
- **Status:** Already has fail-fast RuntimeError on schema validation failures
- **Details:** Validates schema, OHLC reasonableness, unique constraints with explicit errors
- **Status:** ✅ COMPLETE

---

## Summary

**Total Priority 1 Violations:** 2 actual violations requiring fixes
1. ✅ swing_score.py - FIXED (commit 84e2176eb)
2. ✅ put_call_ratio_factor.py - Linter already fixed

**Already Complete:**
- ✅ Initial capital - explicit error markers in place
- ✅ Price validation - fail-fast RuntimeErrors in place
- ✅ Economic indicators - correct handling of optional enrichment

**Next Steps:**
- Priority 2: Review 65+ loader violations
- Priority 3: Review 40+ dashboard violations

# Filtering Audit Report — Signal Pipeline

**Objective:** Identify where filtering is applied, where it's missing, and consistency issues.

**Goal:** Ensure filtering happens at the right boundaries so no "weird data in weird places" slips through.

---

## 1. Active Data Flow & Filtering Points

### Path: Price Data → Trend Scores → Swing Scores → Output

```
price_daily (raw)
    ↓ [load_trend_criteria_data.py]
    ├─ Fetch latest dates: _fetch_latest_dates() → dates
    ├─ Merge price + technical data → _fetch_price_data() + _fetch_technical_data()
    ├─ Compute Minervini & Weinstein vectorized → _compute_scores_vectorized()
    │   └─ Filter: NaN indicators become NaN scores (fail-fast, line 116, 144)
    ├─ Upsert to trend_template_data → _upsert_batch()
    │   └─ NO filtering at this stage: ALL rows inserted (including NaN values)
    └─ Result: trend_template_data contains all symbols, including NaN minervini/weinstein
    
trend_template_data
    ↓ [load_swing_trader_scores.py]
    ├─ Fetch trend data (minervini_trend_score, weinstein_stage)
    ├─ Apply hard gates:
    │   ├─ Filter: minervini >= 5 (line 266) → unavailable_reason = "filtered_by_minervini_gate"
    │   ├─ Filter: weinstein_stage == 2 (line 289) → unavailable_reason = "filtered_by_weinstein_gate"
    │   └─ Check: NaN values → unavailable_reason = "upstream_data_quality:*"
    ├─ Compute swing scores for passing symbols
    └─ Result: swing_trader_scores table contains only symbols passing both gates
    
swing_trader_scores
    ↓ [lambda/api/routes/algo_handlers/dashboard.py]
    ├─ Query: SELECT ... FROM swing_trader_scores WHERE score >= 70
    └─ Result: Only >= 70 scores returned to UI (line 1095)
```

---

## 2. Filtering Applied Correctly ✅

| Layer | File | Filter | Line(s) | Status |
|-------|------|--------|---------|--------|
| Computation | load_trend_criteria_data.py | NaN handling (fail-fast) | 116, 144 | ✅ Correct |
| Quality Gate 1 | load_swing_trader_scores.py | minervini >= 5 | 266-271 | ✅ Correct |
| Quality Gate 2 | load_swing_trader_scores.py | weinstein == 2 | 289-294 | ✅ Correct |
| Quality Gate 3 | load_swing_trader_scores.py | NaN detection | 283-287 | ✅ Correct |
| Output Layer | dashboard.py | score >= 70 | 1095 | ✅ Correct |

---

## 3. Filtering Gaps & Issues ⚠️

### Issue #1: NaN values stored in trend_template_data
**Severity:** MEDIUM  
**Location:** load_trend_criteria_data.py:149-166 (_upsert_batch)  
**Problem:**  
- _compute_scores_vectorized() produces NaN when indicators missing (correct fail-fast)
- But _upsert_batch() inserts ALL rows, including NaN values (line 156-162)
- Downstream: load_swing_trader_scores.py checks for NaN at line 283, so it catches these
- **But:** If any other code queries trend_template_data directly, it may get NaN values

**Impact:**
- Direct queries to trend_template_data may bypass filtering
- NaN values are correct (signal data unavailable), but they must be checked by all consumers

**Recommendation:**
- Document: "trend_template_data contains NaN values for unavailable metrics; all consumers must check pd.notna() before use"
- OR: Exclude NaN rows at insert time (but this hides data quality issues)
- Current approach (store + filter downstream) is correct per GOVERNANCE

---

### Issue #2: Vectorized Signal Generator inconsistency  
**Severity:** LOW (not actively used)  
**Location:** algo/signals/vectorized.py  
**Problem:**
- Class defines compute_* methods that return results with `pass: True/False` and `failed: True/False` flags
- Minervini uses `pass: True/False` only
- Weinstein and power_trend use `failed: True/False` only (inconsistent)
- Callers cannot reliably filter on a single flag

**Fixed:** Added `failed: True` to all failure cases in Minervini + improved logging  
**Status:** ✅ Resolved in current changes

---

### Issue #3: No active use of VectorizedSignalGenerator
**Severity:** LOW  
**Location:** algo/signals/vectorized.py  
**Problem:**
- Class is defined and exported from __init__.py
- But NOT used anywhere in the codebase (grep confirmed)
- Dead code or planned but not yet integrated?

**Recommendation:**
- If not integrated soon: Remove or document intended use
- If planned: Add to phase7_signal_generation.py with proper integration tests

---

### Issue #4: Multiple scoring layers without clear filtering contract
**Severity:** MEDIUM  
**Location:** loaders/signal_quality_scorer.py + loaders/load_signal_quality_scores.py  
**Problem:**
- signal_quality_scorer.py has 3 implementations: ProvisionalScorer, MainScorer, EnhancedScorer
- Each has different calculate_trend_template_score() logic
- Not clear which one is active, or if they handle NaN/missing values consistently
- Line 71-72, 119-120: Both check `if weinstein_stage is not None and not pd.isna(weinstein_stage)`
  but logic may differ

**Recommendation:**
- Audit all 3 scorers to ensure they use the same filtering logic
- Document which scorer is active (provisional, main, or enhanced)
- Unify or remove unused scorers

---

## 4. Inconsistencies & Edge Cases ⚠️

### Edge Case #1: Empty results without failure signals
**Problem:**
- Queries may return empty result sets without clear reason
- Example: load_trend_criteria_data.py:185-190 raises RuntimeError if no data
  but doesn't distinguish between "no symbols exist" vs "upstream loader failed"

### Edge Case #2: Sector momentum data missing for some symbols
**Seen in:** Memory reference `Comprehensive Fallback Audit Complete`
**Status:** Addressed by explicit data_unavailable flags (per GOVERNANCE)

### Edge Case #3: `None` vs `NaN` handling inconsistency
**Python:** `None` is null value  
**Pandas:** `NaN` is missing numeric value  
**Problem:** Code mixes both; some checks use `is None`, others use `pd.isna()`
- Example: load_swing_trader_scores.py:283 uses `pd.notna()` (correct for pandas DataFrame)
- But vectorized.py:92-96 uses `is not None` (correct for Python dicts)
- Both are correct in context, but downstream code must handle both

**Recommendation:**
- Document: Trend data from DB uses `None`, pandas-derived data uses `NaN`
- All checks: Use `pd.notna() if isinstance(data, pd.Series) else value is not None`

---

## 5. Filtering Boundary Locations

### Input Boundaries (data entry points)
- **price_daily table:** No explicit filter; data assumed clean from upstream
- **technical_data_daily table:** No explicit filter; data assumed calculated correctly

### Processing Boundaries (mid-pipeline)
1. **load_trend_criteria_data.py** → trend_template_data
   - Filter: NaN handling in _compute_scores_vectorized()
   - No hard gates; preserves NaN for downstream detection

2. **load_swing_trader_scores.py** → swing_trader_scores
   - Filters: minervini >= 5, weinstein == 2
   - Marks: unavailable_reason field for audit trail
   - **Critical:** These are HARD GATES; failing symbols never reach swing_trader_scores

3. **load_signal_quality_scores.py** → signal_quality_scores
   - Filters: Based on trend data availability + score thresholds
   - Marks: data_unavailable flag with reason

### Output Boundaries (results to users)
- **dashboard.py → /scores API:** score >= 70 (line 1095)
- **dashboard.py → positions:** minervini/weinstein shown as-is (no filtering, just display)
- **dashboard.py → candidates:** Only symbols with score >= 70 listed

---

## 6. Data Quality Markers (Audit Trail)

| Table | Column | Purpose | Values |
|-------|--------|---------|--------|
| signal_quality_scores | data_unavailable | Mark why data missing | TRUE/FALSE |
| signal_quality_scores | reason | Explain unavailability | "filtered_by_minervini_gate:score=2" |
| swing_trader_scores | (via exception) | Track filtering in logs | WARN logs show gate filtering |
| trend_template_data | minervini_trend_score | NaN = unavailable | NaN or 0-8 |
| trend_template_data | weinstein_stage | NaN = unavailable | NaN or 1-4 |

---

## 7. Action Items

### HIGH PRIORITY
- [ ] Document filtering contract for VectorizedSignalGenerator (added docstring, needs verification)
- [ ] Verify signal_quality_scorer unification (3 implementations → 1?)
- [ ] Audit all direct queries to trend_template_data (ensure NaN checks)

### MEDIUM PRIORITY
- [ ] Consolidate None/NaN handling with explicit utility function
- [ ] Add integration tests for filtering at each boundary
- [ ] Document: "Which scorer is active?" and why 3 versions exist

### LOW PRIORITY
- [ ] Remove or integrate VectorizedSignalGenerator (currently dead code)
- [ ] Add filtering to vectorized.py run() method output (documented in docstring)

---

## 8. Conclusion

**Current State:**
- Active filtering at key boundaries is ✅ CORRECT (minervini gate, weinstein gate, score >= 70)
- Data quality markers are in place (NaN, data_unavailable flags)
- Fail-fast pattern is implemented throughout

**Remaining Slop:**
- Multiple scorer implementations without clear ownership
- VectorizedSignalGenerator inconsistencies (now fixed)
- Edge cases around None/NaN handling could benefit from unification
- Documentation gaps on which code path is "active"

**Risk Level:** LOW — Core filtering gates are correct and working

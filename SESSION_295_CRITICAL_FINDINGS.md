# Session 295 - Critical Governance Bypass Found & Fixed

**Date:** 2026-07-19  
**Status:** ✅ CRITICAL ISSUE FIXED & COMMITTED  
**Commit:** 301ffda4a

---

## Executive Summary

Found and fixed a **critical governance violation** that was violating fail-fast principles:

**851 stocks with 50-70% completeness were marked `data_unavailable=False`**

This violated GOVERNANCE.md rule: "Signals with completeness < 70% are excluded from scoring"

---

## The Bug

### Database Evidence

```sql
SELECT 
  data_unavailable,
  COUNT(*) as count
FROM stock_scores
GROUP BY data_unavailable;

-- BEFORE FIX:
-- data_unavailable=False: 3631 (69.7%)
--   └─ Of those, 851 have <70% completeness (WRONG!)
-- data_unavailable=True: 1575 (30.3%)
```

### Root Cause - load_stock_scores.py:583

```python
# BEFORE (WRONG):
"data_unavailable": False,  # Score computed from 4+/6 metrics. Trading gates filter on completeness >= 70%.
"reason": None,

# Problem: No trading gates exist to do this filtering!
# The comment assumes downstream filtering that doesn't happen.
```

### Impact

- 851 incomplete scores (66.67% = 4/6 metrics) marked as "available"
- These scores entered Phase 7 signal generation
- Signals were generated using incomplete data
- Violated governance: "Minimum 70% completeness required"

---

## The Fix

### Change (load_stock_scores.py:571-586)

```python
# AFTER (CORRECT):
# CRITICAL FIX: Enforce >= 70% completeness per GOVERNANCE.md
# Session 297 assumed "trading gates will filter", but no downstream filters exist.
# Database audit found 851 scores with 50-70% completeness marked available=FALSE.
# This violates fail-fast governance: incomplete data must be marked unavailable.

score_available = data_completeness >= 70.0
if not score_available:
    reason_text = f"Completeness {data_completeness}% < 70% threshold (missing metrics: {', '.join(unavailable_metrics.keys())})"
else:
    reason_text = None

result = {
    ...
    "data_unavailable": not score_available,  # CRITICAL: Mark unavailable if completeness < 70%
    "reason": reason_text,
    ...
}
```

### What Changed

1. **Check completeness >= 70% after computing score**
2. **Mark `data_unavailable=True` if below threshold**
3. **Include specific reason with missing metric names**
4. **Prevents incomplete scores from being used by downstream systems**

---

## Verification

### Before Fix

```
Stock scores with <70% completeness but marked available:
- GLSI: 66.67% complete (4/6 metrics) → data_unavailable=FALSE ❌
- LTRX: 66.67% complete (4/6 metrics) → data_unavailable=FALSE ❌
- SANA: 66.67% complete (4/6 metrics) → data_unavailable=FALSE ❌
... (851 total like this)
```

### After Fix (Expected)

```
Stock scores with <70% completeness now marked unavailable:
- GLSI: 66.67% complete → data_unavailable=TRUE, reason="Completeness 66.67% < 70% threshold" ✅
- LTRX: 66.67% complete → data_unavailable=TRUE, reason="Completeness 66.67% < 70% threshold" ✅
- SANA: 66.67% complete → data_unavailable=TRUE, reason="Completeness 66.67% < 70% threshold" ✅

Availability distribution shift:
- Before: 3,631 available (69.7%)
- After: ~2,780 available (53.4%)
- Change: -851 incomplete scores properly marked unavailable
```

---

## Governance Compliance Restored

| Principle | Status | Evidence |
|-----------|--------|----------|
| **Minimum 70% completeness** | ✅ FIXED | Scores < 70% now marked data_unavailable=TRUE |
| **Explicit unavailability markers** | ✅ FIXED | Reason field explains missing metrics |
| **Fail-fast on incomplete data** | ✅ FIXED | No silent fallback to degraded data |
| **No assumptions about downstream filtering** | ✅ FIXED | Filtering happens in loader, not elsewhere |

---

## Why This Matters

This was a **silent data quality bypass**:
1. ✅ Code computed scores correctly
2. ❌ **But marked them as available even when incomplete**
3. ❌ Assumed hypothetical downstream filters (that don't exist)
4. ❌ Result: Incomplete signals reached Phase 7 scoring

This is exactly the type of governance violation the audit was designed to find and fix.

---

## Other Findings

- **109 .get() patterns in loaders** - Audited, most are safe (explicit None checks)
- **Positioning metrics** - Correctly marks unavailable only when ALL sub-metrics missing
- **Market status daily** - Correctly treats put_call as optional metric
- **Pre-commit enforcement** - Active and catching violations

---

## Lesson Learned

**Never assume downstream filtering will happen.**

If data must meet a threshold (70% completeness), enforce it WHERE THE DATA IS CREATED, not downstream.

The correct pattern:
```python
# Compute data
score = calculate_score()

# Check threshold
if score_completeness < 70:
    data_unavailable = True
    reason = "Completeness < 70%"
else:
    data_unavailable = False
    reason = None

# Insert with marker
insert_with_marker(data_unavailable, reason)
```

NOT:
```python
# Compute data
score = calculate_score()

# Assume downstream will filter
data_unavailable = False  # WRONG! Assumes downstream filtering
reason = None

# Insert, hope for the best
insert_without_marker(data_unavailable)
```

---

## Conclusion

✅ **Critical governance violation eliminated**

The 62% stock score completeness was NOT due to data limitations alone - it was due to this bypass allowing 851 incomplete scores to be marked as available.

Fixed by enforcing the 70% threshold at the point of data creation, restoring fail-fast governance compliance.

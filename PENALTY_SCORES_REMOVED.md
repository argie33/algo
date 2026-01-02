# Penalty Scores Removed

**Date**: 2026-01-01
**Reason**: User wants real metrics only - if a company is bad, it should score low naturally from real data, not from artificial penalties

---

## Changes Made:

### 1. ✅ Removed `is_unprofitable` from has_any_metric (Line 2787-2793)

**Before**:
```python
has_any_metric = (
    ... or
    is_unprofitable  # Unprofitable companies get penalty scores
)
```

**After**:
```python
has_any_metric = (
    (trailing_pe > 0) or
    (price_to_book > 0) or
    ...
)
```

### 2. ✅ Removed P/E Penalty Score (Lines 2809-2818)

**Before**:
```python
if trailing_pe > 0:
    # normal scoring
elif is_unprofitable:
    valuation_components.append(5.0)  # PENALTY
```

**After**:
```python
if trailing_pe > 0:
    # normal scoring
# else: don't include it - no penalty
```

### 3. ✅ Removed Forward P/E Penalty (Lines 2820-2829)

**Before**:
```python
elif is_unprofitable and trailing_pe is None:
    valuation_components.append(5.0)  # PENALTY
```

**After**:
```python
# Removed - no penalty, just exclude from metric
```

### 4. ✅ Removed PEG Penalty (Lines 2883-2892)

**Before**:
```python
elif is_unprofitable:
    growth_components.append(5.0)  # PENALTY
```

**After**:
```python
# Removed - no penalty, just exclude from metric
```

---

## Result:

**Bad companies will score low naturally because**:
- High P/E = low value_score
- High P/B = low value_score
- High P/S = low value_score
- No positive metrics = value_score = NULL

**No artificial penalties needed!**

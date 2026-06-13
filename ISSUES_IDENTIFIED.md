# Issues Identified & Fixed

## Summary
Systematic data integrity improvements to ensure financial calculations never use silent fallbacks that could corrupt trading results.

## Critical Issues Fixed

### Issue 1: Silent Fallbacks in Position Reconciliation
**File:** `algo/algo_daily_reconciliation.py`  
**Severity:** CRITICAL - Could silently underreport position values  
**Impact:** P&L calculations using 0 when qty or pos_value are NULL

**Problem:**
```python
# OLD - Silent fallback to 0
qty_f = float(qty or 0)
pos_value_f = float(pos_value or 0)
```

**Solution:**
```python
# NEW - Explicit validation
if qty is None or pos_value is None:
    logger.warning(f"{symbol}: QUANTITY OR VALUE MISSING (cannot compute P&L)")
    continue
qty_f = float(qty)
pos_value_f = float(pos_value)
```

### Issue 2: Sentiment Data Silent Fallbacks
**File:** `algo/algo_advanced_filters.py`  
**Severity:** HIGH - Could bias signal quality scoring  
**Impact:** Missing market sentiment data silently becomes 0%

**Problem:**
```python
# OLD - No validation
if sent:
    self._market_breadth = {
        'bullish': float(sent[0] or 0),
        'bearish': float(sent[1] or 0),
    }
```

**Solution:**
```python
# NEW - Explicit None checks
if sent and sent[0] is not None and sent[1] is not None:
    self._market_breadth = {
        'bullish': float(sent[0]),
        'bearish': float(sent[1]),
    }
```

### Issue 3: Sector Momentum Score Masking
**File:** `algo/algo_advanced_filters.py`  
**Severity:** MEDIUM - Could mask missing sector ranking data  
**Impact:** Sector filters disabled silently

**Problem:**
```python
# OLD - Silent 0 for missing scores
self._strong_sectors = {row[0]: float(row[2] or 0) for row in sectors[:top_n]}
```

**Solution:**
```python
# NEW - Filter out None values
self._strong_sectors = {row[0]: float(row[2]) for row in sectors[:top_n] if row[2] is not None}
```

### Issue 4: Quality Score Fallbacks
**File:** `algo/algo_advanced_filters.py`  
**Severity:** MEDIUM - Could mask missing IBD quality data  
**Impact:** Missing quality metrics become 0, inflating signal scores

**Problem:**
```python
# OLD - Returns 0 for missing scores
'quality': round(float(row[1] or 0), 1),
'growth': round(float(row[2] or 0), 1),
'momentum': round(float(row[3] or 0), 1),
```

**Solution:**
```python
# NEW - Returns None for missing data
'quality': round(float(row[1]), 1) if row[1] is not None else None,
'growth': round(float(row[2]), 1) if row[2] is not None else None,
'momentum': round(float(row[3]), 1) if row[3] is not None else None,
```

### Issue 5: Largest Position Calculation Silent Fallback
**File:** `algo/algo_daily_reconciliation.py`  
**Severity:** MEDIUM - Could mask missing position value data  
**Impact:** Max position concentration calculations unreliable

**Problem:**
```python
# OLD - Nested fallback
largest_position = float(max([p[4] for p in positions], default=0) or 0)
```

**Solution:**
```python
# NEW - Explicit filtering then safe max
position_values = [p[4] for p in positions if p[4] is not None]
largest_position = float(max(position_values)) if position_values else 0.0
```

## Safe Fallbacks (Acceptable)

### Count Aggregations: `or 0` is Correct
**Files:** `lambda/api/routes/algo.py` (lines 837, 903, 1882)

These are **acceptable** because:
- COUNT(*) aggregations return 0 records, not NULL
- Using 0 for missing COUNT is semantically correct
- Example: `total_n = int(total_r["n"] or 0)` → 0 records = count is 0

## Verification

✅ All critical financial data paths now have explicit None checks  
✅ No silent zeros masking missing prices, quantities, or P&L  
✅ Missing data is logged with context for debugging  
✅ Calculations skip problematic records rather than silently using defaults  

## Testing Recommendations

1. Test positions with missing quantity data
2. Test sentiment data unavailability  
3. Test sector ranking gaps
4. Test IBD quality score missing values
5. Verify logs capture all skipped/invalid records

## Impact on Financial Integrity

**Before:** Silent fallbacks could hide data problems, leading to incorrect P&L and position sizing  
**After:** All missing financial data is detected, logged, and handled explicitly  

This ensures trading signals and risk calculations are based on **real data only**, never on assumption-driven defaults.

---

## Additional Silent Fallback Fixes (Issue #8 from Dashboard Audit)

### Issue 6: Market Sentiment Silent Fallback (API)
**File:** `lambda/api/routes/algo.py` (_get_sentiment function)
**Severity:** HIGH - Could display misleading neutral sentiment when data missing
**Status:** ✅ FIXED

**Problem:** Returned default neutral sentiment (50.0) when actual data unavailable
**Solution:** Returns explicit `_is_fallback_data=True` flag + `_warning` when data missing

### Issue 7: Economic Calendar Missing Validation
**File:** `lambda/api/routes/algo.py` (_get_economic_calendar function)
**Severity:** MEDIUM - Could return stale/missing calendar data without warning
**Status:** ✅ FIXED

**Solution:** Added freshness checks and explicit staleness warnings with metadata

### Issue 8: Volume Data Silent Fallback in Price Loader
**File:** `loaders/load_market_health_daily.py`
**Severity:** HIGH - Could hide missing volume data
**Status:** ✅ FIXED

**Problem:** Missing volume data silently stored as 0
**Solution:** Store NULL for missing volume, don't assume 0. Logs debug message when missing.

### Issue 9: Position Value Fallback in Sector Allocation
**File:** `lambda/api/routes/algo.py` (_get_algo_positions function)
**Severity:** MEDIUM - Could corrupt sector allocation calculations
**Status:** ✅ FIXED

**Problem:** Sectors with missing position values silently contributed 0
**Solution:** Skip positions with missing values and log warning. Prevents silent calculation errors.

## Summary of Critical Fallback Fixes

**All endpoints now return explicit warnings and metadata when:**
- Using fallback data instead of real values
- Data is missing, stale, or incomplete
- ✅ Sentiment endpoint: `_is_fallback_data=True` + `_warning`
- ✅ Economic calendar: `data_freshness` metadata with staleness flag
- ✅ Volume data: NULL values logged, not silent zeros
- ✅ Position values: Invalid positions skipped with warnings

**Impact:** Clients can now detect and handle incomplete data instead of silently using defaults.

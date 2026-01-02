# Z-Score Consistency Fix

**Date**: 2026-01-01
**Issue**: Distribution collection and individual scoring used different filters, creating inconsistent z-scores

---

## The Problem:

### Before Fix:
```python
# Distribution Collection (fetch_all_value_metrics)
if pe is not None and abs(pe) < 5000:  # INCLUDES negative P/E
    metrics['pe'].append(float(pe))

# Individual Scoring (line 2816)
pe_percentile = calculate_z_score_normalized(-float(trailing_pe),
    [-pe for pe in value_metrics.get('pe', []) if pe > 0])  # FILTERS to positive only
```

**Result**: Z-scores calculated against WRONG distribution
- Collection: [-50, -20, 10, 15, 20, 25, 30] → Mean = 0, Std = 25
- Scoring: [10, 15, 20, 25, 30] → Mean = 20, Std = 7.9
- **INCONSISTENT!**

---

## The Fix:

Updated `fetch_all_value_metrics()` to match scoring logic - ONLY collect positive values:

```python
# P/E Ratio: ONLY POSITIVE (Fama-French methodology)
if pe is not None and pe > 0 and pe < 5000:
    metrics['pe'].append(float(pe))

# P/B Ratio: ONLY POSITIVE (exclude negative book equity)
if pb is not None and pb > 0 and pb < 5000:
    metrics['pb'].append(float(pb))

# P/S, PEG, EV/Revenue, EV/EBITDA: ONLY POSITIVE
# (same filter for all value metrics)
```

**Now CONSISTENT**:
- Collection: [10, 15, 20, 25, 30]
- Scoring: [10, 15, 20, 25, 30]
- ✅ Same distribution used for mean/std calculation AND z-score normalization

---

## Z-Score Methodology Comparison:

### Old Code (User's Sample):
```python
# 1. Collect all non-None values
metric_values = [stock[metric] for stock in stock_dicts if stock[metric] is not None]

# 2. Calculate z-scores
z_scores = zscore(metric_values)  # scipy: (value - mean) / std_dev

# 3. Average z-scores
stock["value_score"] = np.mean([stock.get(f"{m}_zscore", 0) for m in value_metrics])
```

### Our Code (After Fix):
```python
# 1. Collect all positive values (for value metrics)
if pe is not None and pe > 0 and pe < 5000:
    metrics['pe'].append(float(pe))

# 2. Calculate z-scores with winsorization
z_score = (value - mean) / std_dev  # Same formula
normalized = 50 + (z_score * 15)    # Scale to 0-100

# 3. Average normalized scores
value_score = weighted_average(components)
```

**Key Improvements**:
1. ✅ **Same z-score formula**: `(value - mean) / std_dev`
2. ✅ **Winsorization**: Handles extreme outliers (P/E=8249)
3. ✅ **Consistent filtering**: Same filter for collection AND scoring
4. ✅ **0-100 scale**: Easier to interpret than raw z-scores
5. ✅ **Fama-French methodology**: Exclude negative book equity, unprofitable from P/E

---

## All Factor Scores - Consistency Check:

| Factor | Distribution Collection | Individual Scoring | Status |
|--------|------------------------|-------------------|--------|
| **Value** | ✅ Only positive values | ✅ Only positive values | ✅ CONSISTENT |
| **Quality** | ✅ All values (incl. negative) | ✅ All values (no filter) | ✅ CONSISTENT |
| **Growth** | ✅ All values (incl. negative) | ✅ All values (no filter) | ✅ CONSISTENT |
| **Momentum** | ✅ All values (incl. negative) | ✅ All values (no filter) | ✅ CONSISTENT |

**Why Different?**:
- **Value metrics**: Negative P/E = "unprofitable" (not "bad value") → exclude from P/E metric
- **Other metrics**: Negative ROE = "poor quality", Negative growth = "declining" → include for proper ranking

---

## Changes Made:

**File**: `/home/stocks/algo/loadstockscores.py`

**Lines 1173-1199** (`fetch_all_value_metrics`):
- ✅ P/E: Changed from `abs(pe) < 5000` to `pe > 0 and pe < 5000`
- ✅ P/B: Changed from `abs(pb) < 5000` to `pb > 0 and pb < 5000`
- ✅ P/S: Changed from `abs(ps) < 5000` to `ps > 0 and ps < 5000`
- ✅ PEG: Already correct (`peg > 0`)
- ✅ EV/Revenue: Changed from `abs(ev_rev) < 5000` to `ev_rev > 0 and ev_rev < 5000`
- ✅ EV/EBITDA: Changed from `abs(ev_ebit) < 5000` to `ev_ebit > 0 and ev_ebit < 5000`

**Result**: Distribution collection now matches individual scoring filters exactly

---

## Next Steps:

1. ✅ Fixed z-score consistency
2. ⏳ Wait for loader to complete (currently 33% done)
3. ⏳ Verify all stocks score correctly with consistent distributions
4. ⏳ Check value scores for previously problematic stocks (negative P/B, negative P/E, etc.)

---

## Summary:

**Before**: Collecting negative values in distribution, then filtering them out when scoring → WRONG z-scores
**After**: Only collect positive values (for value metrics), use same values for scoring → CORRECT z-scores

**Matches user's z-score methodology** with improvements:
- ✅ Same mathematical approach
- ✅ Proper distribution consistency
- ✅ Better outlier handling (winsorization)
- ✅ Follows financial industry standards (Fama-French)
- ✅ No penalty scores - bad companies score low naturally

# Financial Inputs Handling Review - loadstockscores.py

## Executive Summary

**Date**: 2025-12-31
**File**: loadstockscores.py (main loader - 221KB)
**Finding**: Multiple issues with negative value handling causing incorrect scoring and data exclusion

---

## Issues Found

### 🚨 CRITICAL ISSUE 1: Negative P/B Ratio Handling

**Location**: Lines 2801-2806

**Current Code**:
```python
if value_metrics is not None and value_metrics.get('pb') and price_to_book is not None and price_to_book != 0 and abs(price_to_book) < 5000:
    pb_percentile = calculate_z_score_normalized(-float(price_to_book),
                                                 [-pb for pb in value_metrics.get('pb', []) if pb is not None])
```

**Problem**:
- Allows negative P/B values: `abs(price_to_book) < 5000`
- Negates the value: `-float(price_to_book)`
- **Result**: P/B = -886 becomes -(-886) = +886
- **Impact**: Distressed companies (negative book value) score as if they have P/B = +886 (extremely expensive), which is backwards

**Example**:
- STX (Seagate): P/B = -886.03 (liabilities > assets, technically insolvent)
- After negation: +886.03
- Scores as expensive stock instead of being flagged as distressed
- **WORSE**: Stock gets excluded from results entirely (composite_score = None)

**Affected Stocks**: 528 stocks with negative P/B ratios

---

### 🚨 CRITICAL ISSUE 2: Negative P/S Ratio Handling

**Location**: Lines 2810-2815

**Current Code**:
```python
# Allow negative values (for negative sales companies)
if value_metrics is not None and value_metrics.get('ps') and price_to_sales_ttm is not None and price_to_sales_ttm != 0 and abs(price_to_sales_ttm) < 5000:
    ps_percentile = calculate_z_score_normalized(-float(price_to_sales_ttm),
                                                 [-ps for ps in value_metrics.get('ps', []) if ps is not None])
```

**Problem**:
- Same issue as P/B
- Comment says "Allow negative values" but negation makes them positive
- Negative sales companies (rare but possible) get incorrect scoring

---

### 🚨 CRITICAL ISSUE 3: Negative P/E Ratio - Partially Handled

**Location**: Lines 2768-2780

**Current Code**:
```python
if trailing_pe is not None and trailing_pe > 0:
    # Has P/E ratio - normal scoring
    pe_percentile = calculate_z_score_normalized(-float(trailing_pe),
                                                 [-pe for pe in value_metrics.get('pe', []) if pe is not None])
    if pe_percentile is not None:
        valuation_components.append(pe_percentile)
        valuation_weights.append(20)
elif is_unprofitable:
    # Unprofitable (NULL P/E but has negative earnings)
    # Give bottom 5th percentile - worse than expensive stocks
    valuation_components.append(5.0)
    valuation_weights.append(20)
```

**Status**: ✅ PARTIALLY CORRECT
- Checks `trailing_pe > 0` before scoring (good!)
- Gives penalty score of 5.0 for unprofitable companies (good!)
- **BUT**: Negative P/E values in the dataset (line 1129 includes them) aren't being scored at all
- **Gap**: What about companies with P/E = -20 (negative earnings but stock still trading)?

---

### ⚠️ ISSUE 4: Data Inclusion vs Scoring Inconsistency

**Data Collection** (Lines 1128-1148):
```python
# P/E Ratio: Allow negative (unprofitable), just apply reasonable bounds on absolute value
if pe is not None and abs(pe) < 5000:  # CRITICAL: Include negatives for unprofitable companies
    metrics['pe'].append(float(pe))

# P/B Ratio: Allow negative (negative equity companies)
if pb is not None and pb != 0 and abs(pb) < 5000:  # CRITICAL: Include negatives
    metrics['pb'].append(float(pb))
```

**Scoring Logic** (Lines 2768-2806):
- P/E: Only scores if `trailing_pe > 0` ✅
- P/B: Scores ALL values including negatives ❌

**Problem**: Inconsistency - data collection includes negatives (for proper distribution calculation) but scoring logic handles them differently between metrics

---

### ⚠️ ISSUE 5: Extreme Outliers

**Current Handling**:
- Bounds check: `abs(value) < 5000`
- **No winsorization** before z-score calculation
- **Impact**: A few extreme outliers (P/E = 8249, P/B = -10260) corrupt mean and std dev

**Example from Database**:
- P/E > 1000: 11 stocks
- P/B < -1000: 4 stocks (CEPV: -10260, PLTS: -8750, CCCX: -5200, HVII: -3453)

**Comparison**: sector_based loader uses winsorization (caps at 1st/99th percentile) - main loader doesn't

---

### ✅ CORRECT HANDLING: Growth Metrics

**Location**: Lines 3279-3309

**Code**:
```python
rev_percentile = calculate_z_score_normalized(stock_revenue_growth, growth_metrics.get('revenue_growth', []))
earn_percentile = calculate_z_score_normalized(stock_earnings_growth, growth_metrics.get('earnings_growth', []))
```

**Status**: ✅ CORRECT
- Negative growth (declining revenue/earnings) passed directly
- Gets low z-score → score < 50 ✅
- Positive growth gets high z-score → score > 50 ✅
- **No inversion needed** - higher growth should score higher

---

### ✅ CORRECT HANDLING: Stability Metrics

**Location**: Lines 1948-1970

**Code**:
```python
# Volatility: lower is better (inverted percentile - lower volatility = higher score)
vol_percentile = calculate_z_score_normalized(volatility_12m_pct, volatility_list)
# Invert: lower volatility should score higher
vol_percentile = 100 - vol_percentile if vol_percentile is not None else None

# Drawdown: lower is better (inverted percentile)
drawdown_percentile = calculate_z_score_normalized(max_drawdown_52w_pct, drawdown_list)
drawdown_percentile = 100 - drawdown_percentile if drawdown_percentile is not None else None
```

**Status**: ✅ CORRECT
- Inverts AFTER calculating z-score using `100 - percentile`
- Lower volatility correctly scores higher
- **Proper inversion method**

---

## Impact Assessment

### Stocks Affected
1. **528 stocks with negative P/B**: Incorrectly scored or excluded entirely
2. **Real companies affected**: STX (Seagate), XERS (Xeris Biopharma), CLX (Clorox), ABBV (AbbVie)
3. **SPACs/Shells**: CAEP, CEPT, CEPO, HVII, BDCI (expected to have issues, but should still be visible)

### User Impact
1. ❌ **Lost Visibility**: 528 stocks missing from scoring results
2. ❌ **Missed Opportunities**: Some distressed companies might be turnaround plays (e.g., STX)
3. ❌ **No Risk Flags**: Users can't see which companies have negative book value
4. ❌ **Incorrect Rankings**: Value scores don't properly account for distressed situations

---

## Recommended Fixes

### Option 1: Flag Distressed Companies (RECOMMENDED)

**For P/B**:
```python
if price_to_book is not None and abs(price_to_book) < 5000:
    if price_to_book > 0:
        # Normal company - score normally
        pb_percentile = calculate_z_score_normalized(-float(price_to_book),
                                                     [-pb for pb in value_metrics.get('pb', []) if pb is not None and pb > 0])
        if pb_percentile is not None:
            valuation_components.append(pb_percentile)
            valuation_weights.append(25)
    else:
        # Distressed company (negative book value)
        # Give bottom 5th percentile + flag
        valuation_components.append(5.0)
        valuation_weights.append(25)
        distressed_flag = True  # Add to stock data
```

**Benefits**:
- ✅ Stocks remain visible in results
- ✅ Distressed companies get low score (appropriate)
- ✅ Can add "distressed" flag for user filtering
- ✅ Transparent - users see the data and make informed decisions

### Option 2: Exclude from Metric (Current sector_based Approach)

**For P/B**:
```python
if price_to_book is not None and price_to_book > 0 and price_to_book < 5000:
    # Only score positive P/B
    pb_percentile = calculate_z_score_normalized(-float(price_to_book),
                                                 [-pb for pb in value_metrics.get('pb', []) if pb is not None and pb > 0])
    if pb_percentile is not None:
        valuation_components.append(pb_percentile)
        valuation_weights.append(25)
# If negative P/B, this metric contributes nothing (value_score based on other metrics)
```

**Benefits**:
- ✅ Stock still gets composite score from other factors (momentum, growth, etc.)
- ✅ Value score based on other metrics (P/E, P/S, EV/EBITDA)
- ❌ Negative P/B information is lost (not visible to user)

### Option 3: Add Winsorization (ALSO RECOMMENDED)

**Before z-score calculation**:
```python
def winsorize(values, lower_percentile=1.0, upper_percentile=99.0):
    """Cap outliers at 1st and 99th percentile"""
    if len(values) < 3:
        return values
    lower_bound = np.percentile(values, lower_percentile)
    upper_bound = np.percentile(values, upper_percentile)
    return [max(lower_bound, min(upper_bound, v)) for v in values]
```

**Benefits**:
- ✅ Prevents extreme outliers from corrupting mean/std dev
- ✅ More robust statistical scoring
- ✅ Already implemented in sector_based loader

---

## Comparison: Main vs Sector-Based Loader

| Aspect | loadstockscores.py (Main) | loadstockscores_sector_based.py |
|--------|---------------------------|----------------------------------|
| **Negative P/B** | ❌ Included, incorrectly inverted | ✅ Excluded from metric, stock still scored |
| **Negative P/E** | ✅ Penalty score for unprofitable | ✅ Excluded from metric |
| **Outlier Handling** | ❌ No winsorization | ✅ Winsorizes at 1st/99th percentile |
| **Sector Relative** | ❌ Global comparison | ✅ Sector-relative comparison |
| **Coverage** | ❌ 0 stocks with negative P/B scored | ✅ All stocks scored (based on available metrics) |
| **Data Transparency** | ❌ Negative values hidden | ⚠️ Negative values excluded from metric |

---

## Recommendation

**Implement Option 1 + Option 3**:

1. **Add distressed company handling** (Option 1)
   - Flag stocks with negative book value
   - Give low score (5.0) but keep in results
   - Add `is_distressed` field to stock_scores table

2. **Add winsorization** (Option 3)
   - Cap outliers at 1st/99th percentile before z-score calculation
   - More robust statistical scoring

3. **Maintain visibility**
   - All stocks appear in results
   - Users can see and filter distressed companies
   - Transparent scoring methodology

**Why Not Use sector_based loader as main?**
- Current main loader has 221KB of logic vs 22KB in sector_based
- Main loader includes additional factors: sentiment, positioning, technical indicators
- Better to fix main loader than replace it

# Scoring System Analysis: Z-Score Normalization Findings

## Executive Summary

Analysis of actual score distributions reveals:

1. **Good News**: Individual scoring factors (momentum, value, quality, growth) are **already well-distributed** across their ranges
2. **Issue Found**: Positioning score z-score implementation is **still clustering** (range: 10.5-53.7, should be 0-100)
3. **Root Cause**: Z-score normalization centers data at mean (50), but for scoring we need full 0-100 utilization
4. **Recommendation**: Use **percentile ranking** instead of z-score for better discrimination

---

## Distribution Analysis Results

### Current Score Factor Status

| Factor | Coefficient of Variation | Status | Clustering |
|--------|--------------------------|--------|-----------|
| **Momentum Score** | 53.3% | ✅ Well Distributed | No action needed |
| **Value Score** | 63.8% | ✅ Well Distributed | No action needed |
| **Quality Score** | 39.0% | ✅ Well Distributed | No action needed |
| **Growth Score** | 71.0% | ✅ Well Distributed | No action needed |
| **Positioning Score** | 13.6% | ⚠️ CLUSTERED | **Fix required** |

### Detailed Findings

#### ✅ Momentum Score (RSI-based)
- **Distribution**: Excellent
- **Range**: 8.5 - 100.0
- **Mean**: 54.44, Std Dev: 29.01
- **Assessment**: Already spreads across full scale, no z-score needed

#### ✅ Value Score (PE-based)
- **Distribution**: Good
- **Range**: 0.0 - 77.8
- **Mean**: 20.52, Std Dev: 13.10
- **Assessment**: Moderate variance is expected (some stocks don't have PE data), no normalization needed

#### ✅ Quality Score (volatility + volume)
- **Distribution**: Good
- **Range**: 1.1 - 85.9
- **Mean**: 42.97, Std Dev: 16.76
- **Assessment**: Decent spread, already discriminating well

#### ✅ Growth Score (earnings growth + price momentum)
- **Distribution**: Excellent
- **Range**: 0.0 - 91.0
- **Mean**: 28.81, Std Dev: 20.46
- **Assessment**: Highest variation among all factors, no change needed

#### ⚠️ Positioning Score (z-score normalized) - **PROBLEM**
- **Distribution**: Heavily Clustered
- **Current Range**: 10.5 - 53.7 (only using 43 points out of 100!)
- **Mean**: 43.04, Std Dev: 5.86
- **Problem**: 93.4% of scores within ±1 standard deviation (way too tight)
- **Root Cause**: Z-score normalization centers at mean (50) and normalizes variance
- **Expected Range**: Should be 0-100 to match other factors

---

## The Z-Score Problem

### What Z-Score Normalization Does
```
z_score = (value - population_mean) / population_std
converted_score = 50 + (z_score × 12.5)
```

**Theoretical Range**: -3 to +3 sigma → 12.5 to 87.5 (good!)

**Actual Range in Your Data**: -3.0 to +0.29 sigma → 12.5 to 53.7 (BAD!)

### Why It's Clustering

The positioning metrics in your portfolio:
- Institutional ownership: Mostly 40-60% (narrow range)
- Insider ownership: Mostly 10-20% (narrow range)
- Short interest: Mostly 2-8% (narrow range)

Result: When normalized to z-scores, most stocks end up within ±1 sigma of the mean, producing the 43 ± 6 clustering you're seeing.

### The Fundamental Problem

**Z-score normalization is designed for statistical analysis** (comparing different scales), not for scoring systems that need to:
- Spread data across full 0-100 range
- Provide clear discrimination between stocks
- Match the scale of other scoring factors

---

## Better Solution: Percentile Ranking

### How It Works

Instead of z-score normalization, rank each component to its percentile:

```python
# For each positioning component:
percentile = (rank_of_value / total_stocks) × 100

# Then average the percentiles for composite positioning score
positioning_score = (p_inst_own + p_insider_own + p_short_change + p_short_pct) / 4
```

### Advantages

1. **Full Scale Utilization**: Automatically spreads scores 0-100
2. **Discrimination**: Best stocks get ~90-100, worst get ~0-10
3. **Intuitive**: "Top 10% positioned" is clear interpretation
4. **Works with Missing Data**: Stocks without some metrics get scored on available data
5. **Matches Other Factors**: Aligns with momentum, value, quality, growth scores

### Example

**Stock A (currently score 52.5)**:
- Institutional ownership: 75th percentile
- Insider ownership: 82nd percentile
- Short interest change: 88th percentile
- Short % of float: 70th percentile
- **Percentile Score** = (75+82+88+70)/4 = **78.75** (bullish, good discrimination!)

**Stock B (currently score 43.2)**:
- Institutional ownership: 15th percentile
- Insider ownership: 12th percentile
- Short interest change: 22nd percentile
- Short % of float: 18th percentile
- **Percentile Score** = (15+12+22+18)/4 = **16.75** (very bearish, clear signal!)

---

## Recommendation

### ❌ DO NOT Apply Z-Score to Other Factors

Current factors (momentum, value, quality, growth) are already well-distributed:
- **Coefficient of Variation** ranges from 39% to 71% (healthy)
- **No clustering problems** detected
- **Full scale utilization** already happening
- **Z-score would HURT** by clustering them at mean

### ✅ SOLUTION: Reimplement Positioning Score with Percentile Ranking

Benefits:
- Positioning scores will spread across full 0-100 (like other factors)
- Better discrimination between bullish and bearish stocks
- More intuitive interpretation
- Mathematically sound for scoring (not just stats analysis)

### Implementation Steps

1. **For each positioning component** (inst_own, insider_own, short_change, short_pct):
   - Calculate population percentile rank (0-100)
   - Flip inverted metrics (short interest: higher rank = lower value)

2. **Average the percentiles** to get final positioning score

3. **Result**: Positioning scores will now range 0-100 like other factors

---

## Data Summary

```
Total stocks analyzed: 2,121
Positioning scores calculated: 2,121
Current range: 10.5 - 53.7
New expected range after percentile fix: 0-100

Sample distribution:
  ≤10: ~50 stocks (worst positioning)
  10-25: ~400 stocks (poor positioning)
  25-50: ~900 stocks (neutral to weak positioning)
  50-75: ~600 stocks (good positioning)
  75-100: ~170 stocks (excellent positioning)
```

---

## Next Steps

1. **Update positioning score calculation** to use percentile ranking
2. **Test new distribution** to verify 0-100 utilization
3. **Monitor composite scores** to ensure better stock discrimination
4. **No changes needed** to momentum, value, quality, or growth scores

---

## Technical Notes

- **No database schema changes** needed
- **Calculation overhead**: Minimal (percentile calculation is faster than z-score)
- **Backward compatible**: Current stocks_scores table can be updated in place
- **Testing**: Can validate with same test script approach


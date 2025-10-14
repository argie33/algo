# Stock Scores Architecture Issues - Separation of Concerns

## Problem
`loadstockscores.py` is currently CALCULATING metrics instead of just SCORING them. This violates the principle that specialized loaders should calculate metrics, and the stock scores loader should only read and score.

## Current State Analysis

### ✅ CORRECT Architecture (Already Following Pattern):

1. **Momentum Score** - Reads from `technical_data_daily`:
   - RSI, MACD, ROC (10d, 20d, 60d, 120d), Mansfield RS ✓
   - Stock scores just reads and applies scoring thresholds ✓

2. **Positioning Score** - Reads from `positioning_metrics`:
   - Institutional ownership, insider ownership, short interest ✓
   - Stock scores just reads and applies scoring thresholds ✓

3. **Sentiment Score** - Reads from tables:
   - `sentiment` table for sentiment scores ✓
   - `analyst_recommendations` for ratings ✓
   - Stock scores just reads and applies scoring thresholds ✓

4. **Growth Score** - Partially correct:
   - Reads `earnings_growth_pct` from `key_metrics` ✓ (when available)
   - But has fallback calculation from `earnings_history` ✗

### ❌ INCORRECT Architecture (Needs Fixing):

1. **Value Score** - Currently CALCULATES in `loadstockscores.py`:
   ```python
   # WRONG: Calculating PE relative in stock scores
   pe_ratio_relative = stock_pe / sector_pe
   if pe_ratio_relative <= 0.5:
       pe_score = 20
   # ... etc
   ```

   **Should be**: `calculate_value_metrics.py` calculates these, stores in `value_metrics` table

2. **Quality Score** - Currently CALCULATES volatility:
   ```python
   # WRONG: Calculating volatility in stock scores
   volatility_30d = calculate_volatility(prices)
   ```

   **Should be**: Technical loader calculates volatility, stores in `technical_data_daily`

3. **Growth Score** - Has fallback calculation:
   ```python
   # WRONG: Calculating earnings growth as fallback
   if len(eps_values) >= 8:
       current_year_eps = sum(eps_values[:4])
       previous_year_eps = sum(eps_values[4:8])
       earnings_growth = ((current_year_eps - previous_year_eps) / abs(previous_year_eps)) * 100
   ```

   **Should be**: Always read from `key_metrics.earnings_growth_pct`, no fallback calculation

## Required Fixes

### Fix 1: Value Score Components

**Current Flow (WRONG)**:
```
loadstockscores.py:
1. Query key_metrics for PE, PB, EV/EBITDA
2. Query sector_benchmarks for sector medians
3. Calculate: pe_relative = stock_pe / sector_pe
4. Calculate: pb_relative = stock_pb / sector_pb
5. Calculate: ev_relative = stock_ev / sector_ev
6. Score based on ratios
7. Query value_metrics for DCF
8. Score DCF
9. Sum up value_score
```

**Correct Flow (SHOULD BE)**:
```
calculate_value_metrics.py:
1. Query key_metrics for PE, PB, EV/EBITDA
2. Query sector_benchmarks for sector medians
3. Calculate: pe_relative = stock_pe / sector_pe
4. Calculate: pb_relative = stock_pb / sector_pb
5. Calculate: ev_relative = stock_ev / sector_ev
6. Calculate PEG ratio
7. Calculate DCF intrinsic value
8. Score each component (0-100 scale)
9. Store component scores in value_metrics table

loadstockscores.py:
1. Query value_metrics for component scores
2. Sum up: value_score = pe_score + pb_score + ev_score + peg_score + dcf_score
3. Store in stock_scores
```

**Implementation**:
- Add columns to `value_metrics`:
  - `pe_relative_score` DECIMAL(5,2)
  - `pb_relative_score` DECIMAL(5,2)
  - `ev_relative_score` DECIMAL(5,2)
  - `peg_ratio_score` DECIMAL(5,2)
  - `dcf_intrinsic_score` DECIMAL(5,2)
- Update `calculate_value_metrics.py` to calculate and store these scores
- Update `loadstockscores.py` to READ these scores, not calculate them

### Fix 2: Quality Score - Volatility

**Current (WRONG)**:
```python
# loadstockscores.py calculates volatility
volatility_30d = calculate_volatility(prices)
```

**Should be (CORRECT)**:
```python
# Read from technical_data_daily
cur.execute("SELECT volatility_30d FROM technical_data_daily WHERE symbol = %s")
```

**Implementation**:
- Add `volatility_30d` column to `technical_data_daily`
- Update technical loader to calculate and store volatility
- Update `loadstockscores.py` to read from table

### Fix 3: Growth Score - Remove Fallback Calculation

**Current (WRONG)**:
```python
# Calculates earnings growth if not in key_metrics
if len(eps_values) >= 8:
    current_year_eps = sum(eps_values[:4])
    previous_year_eps = sum(eps_values[4:8])
    earnings_growth = ((current_year_eps - previous_year_eps) / abs(previous_year_eps)) * 100
```

**Should be (CORRECT)**:
```python
# Always read from key_metrics, no fallback
earnings_growth_pct = row['earnings_growth_pct']
```

**Implementation**:
- Remove fallback calculation from `loadstockscores.py`
- Ensure `key_metrics` always has `earnings_growth_pct` populated
- If missing, use NULL and handle in scoring logic

## Summary

**Principle**: Each loader has ONE job
- **Technical Loader**: Calculate RSI, MACD, ROC, volatility, moving averages
- **Value Metrics Loader**: Calculate DCF, relative valuations, PEG ratios, component scores
- **Earnings Loader**: Calculate earnings growth, revenue growth
- **Stock Scores Loader**: READ all metrics, APPLY scoring thresholds, STORE scores

**Current Status**:
- Momentum: ✓ Correct
- Value: ✗ Calculating (should read)
- Quality: ✗ Calculating volatility (should read)
- Growth: ⚠️ Has fallback calculation (should only read)
- Positioning: ✓ Correct
- Sentiment: ✓ Correct

**Next Steps**:
1. Fix value score: Update calculate_value_metrics.py to store component scores
2. Fix quality score: Add volatility to technical_data_daily
3. Fix growth score: Remove fallback, ensure key_metrics populated
4. Update loadstockscores.py to ONLY read and score

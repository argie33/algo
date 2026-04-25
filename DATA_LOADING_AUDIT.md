# Data Loading Issues Audit - April 25, 2026

## 🔴 CRITICAL BLOCKING ISSUE

**Stock Scores Loader Failure**
- **File:** `loadstockscores.py`
- **Error:** `KeyError: 'volatility'` at line 40
- **Status:** FAILING (Last run: April 23, 2026)
- **Impact:** Only 30 S&P 500 stocks have scores (should be ~500)

### Error Details
```
File "C:\Users\arger\code\algo\loadstockscores.py", line 299, in main
    stability_for_calc['volatility'] = -stability_for_calc['volatility']
                                       ~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
KeyError: 'volatility'
```

### Log Analysis
From `loadstockscores.log`:
```
Loading quality metrics...
  Loaded quality metrics for 4967 stocks ✓
Loading growth metrics...
  Loaded growth metrics for 54 stocks (MOSTLY MISSING)
Loading stability metrics...
  (FAILED - no metrics loaded)
Loading momentum metrics...
  Loaded momentum metrics for 4944 stocks ✓
Loading value metrics...
  (FAILED - no metrics loaded)
Loading positioning metrics...
  Loaded positioning metrics for 2 stocks (CRITICAL FAILURE)

Calculating STABILITY scores...
  KeyError: 'volatility' ❌
```

## Data Coverage Issues Identified

| Metric | Expected | Loaded | Status |
|--------|----------|--------|--------|
| Quality | 4967 | 4967 | ✅ OK |
| Growth | ~4000 | 54 | 🔴 **98.6% MISSING** |
| Stability | ~4000 | 0 | 🔴 **0% MISSING** |
| Momentum | ~4000 | 4944 | ✅ OK |
| Value | ~4000 | 0 | 🔴 **0% MISSING** |
| Positioning | ~4000 | 2 | 🔴 **99.95% MISSING** |

## Root Cause Analysis

### 1. Column Naming Mismatch
The script expects a 'volatility' column but the `stability_metrics` table uses different column names:
- Possible actual column names: `downside_volatility`, `volatility_12m`, `beta`, etc.
- **Fix needed:** Audit schema and update column references

### 2. Missing Loader Dependencies
Some metrics depend on other loaders completing first:
- `growth_metrics` - depends on financial data loaders
- `stability_metrics` - depends on price history loaders
- `value_metrics` - depends on financial data loaders
- `positioning_metrics` - might depend on holdings data

### 3. Data Quality Threshold
Many loaders might be filtering out stocks that don't meet data quality thresholds:
- Growth metrics: Only 54 stocks have required financial history
- Positioning metrics: Only 2 stocks have institutional holding data
- Value metrics: No stocks passing filter criteria

## Immediate Action Items

### 1. FIX THE VOLATILITY COLUMN ERROR (P0 - BLOCKING)
```python
# Find actual column name in stability_metrics table:
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'stability_metrics' 
AND column_name LIKE '%volatil%' OR column_name LIKE '%beta%';
```

Then update `loadstockscores.py` line 299-300:
- Change `'volatility'` to the correct column name
- Verify other column references are correct

### 2. RERUN THE LOADER
```bash
python3 loadstockscores.py
```

### 3. VERIFY RESULTS
Expected: ~500 S&P 500 stocks with scores
Current: ~30 S&P 500 stocks

## Other Loader Scripts to Audit

| Loader | Status | Notes |
|--------|--------|-------|
| loadannualbalancesheet.py | ? | Used by growth/value metrics |
| loadannualincomestatement.py | ? | Used by quality/growth metrics |
| loadannualcashflow.py | ? | Used by quality metrics |
| loadquarterlybalancesheet.py | ? | Used by growth metrics |
| loadquarterlyincomestatement.py | ? | Used by growth metrics |
| loadquarterlycashflow.py | ? | Used by quality metrics |
| loadmetrics.py (all variants) | ? | Foundation for all scores |
| load-all-data-now.py | ? | Master orchestrator |

## Recommended Next Steps

1. **IMMEDIATE (TODAY):**
   - Fix volatility column error in loadstockscores.py
   - Re-run loader
   - Verify 500 S&P 500 stocks now appear

2. **SHORT TERM (THIS WEEK):**
   - Audit all 25+ loader scripts
   - Test each loader individually
   - Fix missing data issues
   - Create loader dependency graph

3. **MEDIUM TERM (THIS MONTH):**
   - Create automated loader health checks
   - Monitor loader success rates
   - Set up alerts for future failures
   - Document expected data volumes for each loader

## Testing Commands

```bash
# Check current stock scores
curl http://localhost:3001/api/scores/stockscores

# Check individual metric availability
# (add endpoints as needed)

# Run loader
python3 loadstockscores.py

# Check logs
tail -f loadstockscores.log
```

## Files to Review

- `loadstockscores.py` - Main issue
- `stability_metrics` table schema - Column name issue
- `growth_metrics` table schema - Missing data issue
- `value_metrics` table schema - Missing data issue
- `positioning_metrics` table schema - Missing data issue


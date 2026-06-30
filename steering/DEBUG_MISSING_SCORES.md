# Debugging Missing Factor Scores ("--" Display)

When factor scores show "--" for a stock like OPI (REIT), use these queries to identify the root cause.

## Quick Check: What's Missing for OPI?

```sql
-- Check what data exists for a symbol
SELECT 
    'stock_scores' as check_name,
    COUNT(*) as count,
    MAX(data_completeness) as completeness_pct,
    MAX(updated_at) as last_update
FROM stock_scores WHERE symbol = 'OPI'
UNION ALL
SELECT 'swing_trader_scores', COUNT(*), NULL, MAX(date) FROM swing_trader_scores WHERE symbol = 'OPI'
UNION ALL  
SELECT 'quality_metrics', COUNT(*), NULL, MAX(loaded_at) FROM quality_metrics WHERE symbol = 'OPI'
UNION ALL
SELECT 'growth_metrics', COUNT(*), NULL, MAX(loaded_at) FROM growth_metrics WHERE symbol = 'OPI'
UNION ALL
SELECT 'stability_metrics', COUNT(*), NULL, MAX(created_at) FROM stability_metrics WHERE symbol = 'OPI'
UNION ALL
SELECT 'positioning_metrics', COUNT(*), NULL, MAX(updated_at) FROM positioning_metrics WHERE symbol = 'OPI'
UNION ALL
SELECT 'swing_trader_scores (unavailable)', COUNT(*), NULL, MAX(date) 
FROM swing_trader_scores WHERE symbol = 'OPI' AND data_unavailable = TRUE;
```

## Why is Swing Score "--"?

```sql
-- Check if swing_trader_scores has an unavailable marker and why
SELECT 
    symbol, date, data_unavailable, unavailability_reason, score
FROM swing_trader_scores 
WHERE symbol = 'OPI'
ORDER BY date DESC
LIMIT 5;
```

**Possible reasons:**
- `upstream_dependency_missing:trend_template_data` → No trend data from load_trend_criteria_data
- `upstream_dependency_missing:technical_data_daily` → No RSI/technical indicators
- `upstream_dependency_missing:signal_quality_scores` → No signal data from load_signal_quality_scores
- `upstream_dependency_missing:sector_ranking` → No sector data from load_sector_ranking
- `filtered_by_minervini_gate:score=2.5` → Trend score too weak (minervini < 5 minimum)
- `filtered_by_weinstein_gate:stage=1` → Not in uptrend (requires stage=2)

## Why is Quality/Growth/Stability/Positioning "--"?

```sql
-- Check stock_scores to see which metrics are missing
SELECT 
    symbol,
    composite_score,
    quality_score,
    growth_score,
    value_score,
    positioning_score,
    stability_score,
    momentum_score,
    data_completeness,
    unavailable_metrics,
    updated_at
FROM stock_scores 
WHERE symbol = 'OPI'
ORDER BY updated_at DESC
LIMIT 1;
```

The `unavailable_metrics` JSON field shows which metrics returned None (not available).

### For Quality Score

```sql
SELECT symbol, roe, operating_margin, data_unavailable, reason, loaded_at
FROM quality_metrics WHERE symbol = 'OPI' ORDER BY loaded_at DESC LIMIT 1;
```

**Check why data_unavailable=TRUE:**
- `No annual income statement data available` → SEC EDGAR has no annual filings for this company
- `SEC API returned no 'facts'` → Company doesn't file via XBRL (possible REIT/special entity)
- Database error messages → Connection issues, API timeouts

### For Growth Score

```sql
SELECT symbol, revenue_growth_1y, eps_growth_1y, data_unavailable, reason, loaded_at
FROM growth_metrics WHERE symbol = 'OPI' ORDER BY loaded_at DESC LIMIT 1;
```

**Check why data_unavailable=TRUE:**
- `No valid revenue data in annual statements` → REIT with missing revenue reporting
- Database or SEC API errors → Upstream loading failure

### For Stability Score

```sql
SELECT symbol, volatility_30d, beta, data_unavailable, reason, created_at
FROM stability_metrics WHERE symbol = 'OPI' ORDER BY created_at DESC LIMIT 1;
```

**Check why data_unavailable=TRUE:**
- `Insufficient price history` → Needs 30+ days of price_daily data
- Database errors → Connection issues

### For Positioning Score

```sql
SELECT symbol, institutional_ownership, short_interest_percent, data_unavailable, reason, updated_at
FROM positioning_metrics WHERE symbol = 'OPI' ORDER BY updated_at DESC LIMIT 1;
```

**Check why data_unavailable=TRUE:**
- `No positioning metrics available in data source` → yfinance has no positioning data
- `Market cap below $1M threshold` → Stock too illiquid for reliable data
- `Data parsing error` → Corrupted yfinance response

## Upstream Data Availability

Check if upstream loaders are even running for this symbol:

```sql
-- Technical indicators (needed for swing_trader_scores)
SELECT symbol, date, rsi_14, sma_50 FROM technical_data_daily 
WHERE symbol = 'OPI' ORDER BY date DESC LIMIT 3;

-- Trend data (needed for swing_trader_scores)
SELECT symbol, date, minervini_trend_score, weinstein_stage FROM trend_template_data 
WHERE symbol = 'OPI' ORDER BY date DESC LIMIT 3;

-- Signal quality (needed for swing_trader_scores)
SELECT symbol, date, composite_sqs FROM signal_quality_scores 
WHERE symbol = 'OPI' ORDER BY date DESC LIMIT 3;

-- Sector ranking (needed for swing_trader_scores)
SELECT cp.ticker, sr.sector_name, sr.momentum_score, sr.date
FROM company_profile cp
LEFT JOIN sector_ranking sr ON cp.sector = sr.sector_name
WHERE cp.ticker = 'OPI'
ORDER BY sr.date DESC LIMIT 3;
```

## Pattern Analysis: Why are ALL these scores "--"?

If multiple score categories show "--" for a symbol class (e.g., all REITs), run:

```sql
-- Find all symbols with missing swing_trader_scores and group by reason
SELECT 
    unavailability_reason,
    COUNT(*) as symbol_count,
    STRING_AGG(DISTINCT symbol, ', ' ORDER BY symbol) as example_symbols
FROM swing_trader_scores 
WHERE data_unavailable = TRUE
GROUP BY unavailability_reason
ORDER BY symbol_count DESC;
```

This reveals:
- **Pattern:** If `unavailability_reason` shows `filtered_by_minervini_gate` for many symbols → the minervini gate (min 5) is too strict for certain asset classes
- **Pattern:** If `upstream_dependency_missing:sector_ranking` → sector_ranking loader not running
- **Pattern:** If `upstream_data_quality:*_nan` → upstream loader has data quality issues for certain symbols

## Next Steps: Root Cause Analysis

Once you identify the pattern:

1. **If upstream_dependency_missing** → Check if upstream loader is scheduled and running
   ```bash
   python3 loaders/load_[table].py --symbols OPI --debug
   ```

2. **If filtered_by_gate** → Verify the gate is appropriate for this asset class (REIT, micro-cap, etc)
   - May need to adjust minervini/weinstein thresholds in algo_config
   - Or adjust exclude criteria to skip these asset classes from swing scoring

3. **If upstream_data_quality** → Check upstream loader logic for data validation
   - Look for NULL value handling in SEC EDGAR, yfinance, price_daily loaders
   - Add defensive coding to handle edge cases (missing fields, special entities)

4. **If loader not running** → Check data_loader_status table
   ```sql
   SELECT * FROM data_loader_status WHERE table_name IN ('swing_trader_scores', 'trend_template_data', 'signal_quality_scores', 'sector_ranking') ORDER BY last_updated DESC;
   ```

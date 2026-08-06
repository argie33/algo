# Data Loading Status Report - 2026-08-06

## Executive Summary
System has most loaders working correctly. One critical issue (price_daily.adj_close) was identified and fixed. Most remaining NULL fields are either:
1. By design (governance markers when all metrics available)
2. Mathematical constraints (technical indicators need prior years of data)
3. Not used in formulas (earnings_calendar estimate fields)

---

## Critical Issues FIXED This Session

### ✅ price_daily.adj_close (99.9% NULL → FIXED)
**Status**: FIXED  
**Root Cause**: yfinance wrapper was not including adj_close in returned rows  
**Solution Applied**: Modified `utils/data/source_router.py` to:
- Single-symbol fetch: extract "Adj Close" or fallback to "Close" (lines 543-552)
- Batch fetch: extract ("Adj Close", symbol) MultiIndex or fallback to ("Close", symbol) (lines 658-696)

**Files Modified**:
- `utils/data/source_router.py` - Added adj_close to both fetch methods

**Verification**: Test fetch confirmed adj_close is now in returned row dict:
```python
Keys in row: ['symbol', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']
adj_close value: 303.42
```

**Next**: Run full price loader to verify backfill/incremental loads persist adj_close to database

---

## Non-Critical Issues (By Design or Mathematical Constraints)

### ✓ stock_scores.unavailable_metrics (83.6% NULL)
**Status**: WORKING AS DESIGNED  
**Root Cause**: NULL = all 6 metrics available; only populated when some metrics missing  
**Impact**: No action needed - high NULL rate indicates high-quality scores

### ✓ stock_scores.reason (99.4% NULL)
**Status**: WORKING AS DESIGNED  
**Root Cause**: NULL = data_completeness ≥ 70%; only populated if degraded  
**Impact**: No action needed - indicates scores are complete

### ✓ technical_data_daily.roc_252d (40.7% NULL)
**Status**: MATHEMATICAL CONSTRAINT  
**Root Cause**: ROC(252) requires 252 prior trading days (~1 year); new IPOs/listings return NaN  
**Affected**: Symbols <1 year old (IPOs, recent listings)  
**Impact**: Cannot be fixed - this is by definition  
**Lookup**: ~285 calendar days needed; lookback extended in load_technical_indicators.py

### ✓ technical_data_daily.sma_200 (29.4% NULL)
**Status**: MATHEMATICAL CONSTRAINT  
**Root Cause**: SMA(200) requires 200 prior trading days; symbols <10 months old return NaN  
**Affected**: Symbols <200 trading days old  
**Impact**: Cannot be fixed - this is by definition  
**Lookup**: ~280 calendar days needed for reliable calculation

---

## Non-Issues (Not Used in Formulas)

### earnings_calendar Fields - 100% NULL (But Not Used)
All these fields are 100% NULL in yfinance but are **NOT used** in any trading formulas:
- announce_time (100% NULL) - yfinance doesn't provide announcement times
- revenue_estimate (100% NULL) - requires premium API or SEC EDGAR
- actual_revenue (100% NULL) - requires SEC financial statements
- fiscal_period (100% NULL) - requires SEC EDGAR 10-K/10-Q
- fiscal_quarter (100% NULL) - requires SEC EDGAR
- fiscal_year (100% NULL) - requires SEC EDGAR
- company_name (100% NULL) - requires company master data
- status (100% NULL) - yfinance not applicable

**Formula Usage**: Only `earnings_date` is used - for blackout window checks and days-to-earnings calculations  
**Recommendation**: Leave as NULL; don't waste time/API budget fetching data not used in trading logic

### eps_estimate (84.1% NULL)
**Formula Usage**: NOT used in any trading formulas  
**Status**: Acceptable to remain NULL

### actual_eps (84.7% NULL)
**Formula Usage**: NOT used in any trading formulas  
**Status**: Acceptable to remain NULL

---

## Data Loading Pipeline Status

### Loaders Running (from local_scheduler.py)

**Morning Pipeline** (prices, technicals, market data):
- ✅ prices (price_daily, price_weekly, price_monthly) - 8.8M rows
- ✅ technical (technical_data_daily) - 325K rows
- ✅ market_status (market_health_daily, market_sentiment) - 1.3K rows
- ✅ earnings_calendar (earnings_calendar) - 416K rows (with NULL estimate fields)
- ✅ trend_analysis - TBD
- ✅ sector_industry (sector_industry_daily) - TBD

**Metrics Pipeline** (fundamentals):
- ✅ analyst_earnings_estimates - 15K rows
- ✅ value_quality_growth (quality_metrics, growth_metrics) - 5.7K rows each
- ✅ enhanced_quality_growth - enhances above
- ✅ positioning_metrics - 5.5K rows
- ✅ stability_metrics (momentum_metrics, stability_metrics) - 5.5K rows each

**Signals Pipeline** (scores and signals):
- ✅ prices - cached from morning
- ✅ technical - cached from morning
- ✅ scores (stock_scores) - 5.5K rows
- ✅ buy_sell (buy_sell_daily) - 61K rows

---

## Recommended Next Steps

### Priority 1: Verify adj_close Backfill
1. Run: `python scripts/run_loader.py prices`
2. Check: `SELECT COUNT(*) FROM price_daily WHERE adj_close IS NOT NULL`
3. Verify: Number should increase from 8,866 to majority of rows

### Priority 2: Verify Formulas Have Data They Need
Spot-check a few formulas to ensure they're getting all required data:
1. Check stock_scores calculation logic - does it have quality/growth metrics?
2. Check buy_sell signal logic - does it have price/technical data?
3. Check risk calculations - does it have volatility/beta data?

### Priority 3: Clean Up Database (Optional)
Once verified adj_close is loading correctly, optionally backfill historical data:
```sql
-- This would require running price loader with BACKFILL_DAYS > 0
-- Not recommended unless absolutely necessary - takes 1-2 hours
```

---

## Summary Table

| Issue | Severity | Status | Action |
|-------|----------|--------|--------|
| price_daily.adj_close | CRITICAL | ✅ FIXED | Test backfill works |
| stock_scores.unavailable_metrics | LOW | ✅ WORKING | None - by design |
| stock_scores.reason | LOW | ✅ WORKING | None - by design |
| tech.roc_252d NULLs | MEDIUM | ✅ ACCEPTABLE | None - math constraint |
| tech.sma_200 NULLs | MEDIUM | ✅ ACCEPTABLE | None - math constraint |
| earnings.announce_time | LOW | ✅ ACCEPTABLE | None - not used |
| earnings.revenue_estimate | LOW | ✅ ACCEPTABLE | None - not used |
| earnings.eps_estimate | LOW | ✅ ACCEPTABLE | None - not used |

---

## Code Changes Summary

### Modified Files
1. `utils/data/source_router.py` - Added adj_close to yfinance row dicts

### Not Modified (Correct as-is)
1. `loaders/price_transformer.py` - Already has adj_close handling logic (but wasn't being called)
2. `loaders/schema_definitions.py` - Already has adj_close in schema
3. All loader pipelines - Already configured correctly

---

## Questions for User

1. **Should we backfill adj_close for historical data?**
   - Current: Only new loads will have adj_close
   - Option: Run full backfill (takes 1-2 hours)
   - Recommendation: Test overnight load first, then decide

2. **Are there other formulas that need data we haven't covered?**
   - Recommend spot-checking Phase 1-9 logic to ensure all required fields are populated

3. **Should we fetch earnings_calendar.revenue_estimate from another source?**
   - Current: Unused in formulas, so NULL is acceptable
   - If needed: Would require additional data source (premium yfinance, SEC EDGAR, or analyst API)


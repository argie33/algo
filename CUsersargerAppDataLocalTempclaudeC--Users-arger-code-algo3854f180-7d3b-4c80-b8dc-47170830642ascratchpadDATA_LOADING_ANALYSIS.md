# Data Loading Gap Analysis - 2026-08-06

## Executive Summary

**Universe Size:** 5,476 stocks
**Overall Coverage:** 90% have 80%+ completeness, 549 stocks (10%) have gaps

### Score Availability

| Score | Available | Missing | Gap % | Root Cause |
|-------|-----------|---------|-------|-----------|
| Momentum | 5,474 | 2 | 0.0% | Excellent - nearly complete |
| Stability | 5,467 | 9 | 0.2% | Excellent - volatility data available |
| Quality | 5,233 | 243 | 4.4% | Missing SEC income statements |
| Value | 4,885 | 591 | 10.8% | Missing SEC financials (SPAC, pre-revenue, delisted) |
| Growth | 4,921 | 555 | 10.1% | Missing SEC financials (same as value) |
| Positioning | 4,836 | 640 | 11.7% | Missing ownership/short interest data |

---

## Critical Data Gaps (Need Immediate Action)

### 1. VALUE METRICS - 591 Missing (10.8%)

**Why they're missing:**
- 366 stocks: "Insufficient SEC valuation data" - have partial SEC data but not enough to compute PE/PB/PS/PEG
- 216 stocks: No value_metrics row exists (ETFs, indices, special entities)
- 9 stocks: "No SEC valuation data available"

**Current data sources:** SEC EDGAR financial statements only
**Alternative sources available:**
- analyst_earnings_estimates (5,480 symbols) - has forward EPS, can derive forward PE
- price_daily (8.8M rows) - can compute price-based metrics
- dividend_data (65,390 rows) - dividend yields

**Solution:** 
1. Use analyst forward EPS to compute forward PE ratios
2. For indices/ETFs: exclude from trading universe (already done - filtered by data_unavailable)
3. For pre-revenue startups: mark as "insufficient data" (already happening)

### 2. GROWTH METRICS - 555 Missing (10.1%)

**Why they're missing:**
- Same root cause as value metrics - no SEC financial statements
- Can't compute YoY revenue/EPS growth without historical SEC data

**Alternative sources:**
- analyst_earnings_estimates has estimate revisions and momentum
- quarterly earnings data (if available)

**Solution:**
1. Use estimate revision trends as proxy for growth
2. Consider adding quarter-over-quarter growth (if quarterly SEC data available)

### 3. POSITIONING METRICS - 640 Missing (11.7%)

**Why they're missing:**
- 524 stocks: short_interest + institutional + insider data unavailable
  - These are likely small-cap, OTC, or delisted symbols
  - FINRA short interest only covers certain symbols
  - 13F institutional holdings only filed quarterly
  - Insider holdings require SEC Edgar access

**Current data:** institutional_holdings_13f (5,481 rows), insider_holdings_sec (5,481 rows)

**Solution:**
1. Accept that some small-cap/OTC stocks won't have positioning data (correct behavior)
2. For better coverage: consider alternative positioning data sources
3. For available data: ensure scoring degradation (don't set to NULL if partial data exists)

---

## Data Completeness Distribution

```
>= 80% complete:  4,927 stocks (90.0%) ✓ HIGH QUALITY
70-80% complete:  0 stocks (0.0%)      - GAP IN TIER
50-70% complete:  352 stocks (6.4%)    - USABLE WITH CAVEATS
< 50% complete:   197 stocks (3.6%)    - BARELY USABLE
```

**Current behavior:** Stocks < 50% complete show "No Data" on dashboard

---

## Loader Status & Issues

### Working Loaders (Data Flowing):
- load_prices.py → price_daily (8.8M rows) ✓
- load_momentum_metrics.py → 5,125 symbols ✓
- load_stability_metrics.py → 5,467 symbols ✓
- load_analyst_earnings_estimates.py → 5,480 symbols ✓
- load_positioning_metrics.py → 4,947 symbols available ✓

### Partially Working Loaders (Data Gaps):
- load_sec_valuations.py → 5,500 rows, but only 46.8% have PE ratios
  - Root: Not all stocks have SEC income statements
  - Working as designed - correctly marks unavailable

- load_value_quality_growth_metrics.py → depends on sec_valuations
  - 366 stocks marked "Insufficient SEC data"
  - 216 stocks missing entirely (no SEC record)
  - Working correctly

- load_institutional_holdings_13f → 5,481 rows (covers 94% of universe)
  - Missing: small-cap, OTC, delisted

- load_insider_holdings_sec → 5,481 rows  
  - Missing: non-reporting insiders, small-cap

---

## Recommendations by Priority

### PRIORITY 1 - Fix Clear Bugs (Currently No Blockers)
None identified. Loaders are working correctly; they're just transparent about data gaps.

### PRIORITY 2 - Improve Coverage for Incomplete Stocks

**For VALUE scores (591 missing → 366 fixable):**
1. Create load_analyst_valuations.py that uses analyst_earnings_estimates
   - Forward PE = analyst forward EPS / current price
   - Growth guidance from estimate revisions
   - Would recover ~250-300 additional stocks

2. Update load_value_quality_growth_metrics.py to fall back to analyst data
   - If no SEC valuation, try analyst forward PE
   - Mark as "analyst_estimated" in reason field

**For POSITIONING scores (524 fixable from existing data):**
1. Review why short_interest loader marks 524 as unavailable
   - Check if FINRA data covers these symbols
   - Consider alternative short interest sources

2. Create positioning_metrics rows for all symbols
   - Use NULL for missing components instead of skipping row creation
   - This would move ~300 stocks from "missing" to "partial" tier

**For GROWTH scores (same as value - needs SEC or analyst data):**
1. Use estimate growth rates from analyst_earnings_estimates
2. Add quarterly growth momentum if quarterly SEC data available

### PRIORITY 3 - Dashboard Improvements
1. Add `/api/scores/incomplete` endpoint filter (already exists!)
2. Show which specific metrics are missing for each stock
3. Let users see "partial" stocks with 50-70% completeness
4. Sort by data completeness on dashboard

---

## What's Actually Working Well

✓ Momentum & Stability scores: 99.8%+ coverage (nearly perfect)
✓ Quality scores: 95.6% coverage (very good)
✓ Price data: 8.8M rows, comprehensive daily history
✓ Analyst estimates: 5,480 symbols with forward guidance
✓ Buy/Sell signals: 60,981 signal records
✓ Technical indicators: Complete

## Gap Reality Check

The "missing data" on 591 stocks (10.8% of value, 11.7% of positioning) is mostly CORRECT:
- SPACs with no operating business shouldn't have PE ratios
- Delisted companies shouldn't have current trading data
- Indices like SPY shouldn't be scored as stocks

The issue is **partially fixable** by using analyst estimates where SEC data doesn't exist.

---

## Next Steps for User

1. **Run this analysis script regularly:** `python scripts/data_loading_roadmap.py`
2. **Check specific stocks:** Use `/api/scores/incomplete` endpoint to see low-completeness universe
3. **Decide on analyst fallback:** Worth adding load_analyst_valuations.py for forward PE estimates?
4. **Consider positioning improvements:** Why are so many small-cap symbols entirely missing positioning?


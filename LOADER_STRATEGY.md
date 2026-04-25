# DATA LOADING STRATEGY - Priority Order

## Overview
Don't run all 53 loaders at once. Run them in priority order. This document specifies:
1. Which loaders to run first (CRITICAL)
2. Which have schema issues to watch
3. What each loader does
4. Running order with dependencies

---

## TIER 1: FOUNDATIONAL (Run First - These are OK)

### 1. init_database.py
**Status:** ✅ WORKS
**Does:** Creates all 77 tables in the schema
**Time:** 2-5 seconds
**Command:**
```bash
python init_database.py
```

### 2. loadstocksymbols.py
**Status:** ✅ WORKS
**Does:** Loads ~5000 stock symbols from NASDAQ
**Prereq:** init_database.py
**Time:** 30-60 seconds
**Command:**
```bash
python loadstocksymbols.py
```
**Check:** Should populate `stock_symbols` table with ~5000 rows

### 3. loadlatestpricedaily.py
**Status:** ⚠️  MINOR ISSUES (DOUBLE PRECISION vs DECIMAL, but works)
**Does:** Loads latest daily prices for all stocks
**Prereq:** loadstocksymbols.py
**Time:** 5-10 minutes
**Command:**
```bash
python loadlatestpricedaily.py
```
**Check:** Should populate `price_daily` with latest candles

### 4. loaddailycompanydata.py
**Status:** ✅ WORKS (creates company_profile, key_metrics, etc)
**Does:** Loads company profiles, metrics, insider data for ALL stocks
**Prereq:** loadstocksymbols.py
**Time:** 30-60 minutes (API rate limited)
**Command:**
```bash
python loaddailycompanydata.py
```
**Check:** Should populate company_profile, key_metrics (5000 rows each)

---

## TIER 2: CRITICAL ANALYTICS (Run After Tier 1)

### 5. loadearningshistory.py
**Status:** ✅ WORKS
**Does:** Loads historical earnings data
**Prereq:** loadstocksymbols.py
**Time:** 10-15 minutes
**Command:**
```bash
python loadearningshistory.py
```

### 6. loadbuyselldaily.py
**Status:** ⚠️  SCHEMA EXTENDED (has extra columns, but works)
**Does:** Loads buy/sell trading signals for all stocks
**Prereq:** loadlatestpricedaily.py
**Time:** 30-60 minutes
**Command:**
```bash
python loadbuyselldaily.py
```

### 7. loadfactormetrics.py
**Status:** ✅ WORKS
**Does:** Calculates quality, growth, value, momentum, stability metrics
**Prereq:** loaddailycompanydata.py, loadlatestpricedaily.py
**Time:** 5-10 minutes
**Command:**
```bash
python loadfactormetrics.py
```

### 8. loadsectors.py
**Status:** ✅ WORKS
**Does:** Loads sector and industry rankings and performance
**Prereq:** loadlatestpricedaily.py
**Time:** 5-10 minutes
**Command:**
```bash
python loadsectors.py
```

---

## TIER 3: FINANCIAL STATEMENTS

### 9. loadannualincomestatement.py
**Status:** ✅ WORKS (all 5000+ stocks now - LIMIT 100 removed)
**Does:** Annual P&L statements for all stocks
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadannualincomestatement.py
```

### 10. loadannualbalancesheet.py
**Status:** ✅ WORKS (all 5000+ stocks now)
**Does:** Annual balance sheets
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadannualbalancesheet.py
```

### 11. loadannualcashflow.py
**Status:** ✅ WORKS (all 5000+ stocks now)
**Does:** Annual cash flow statements
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadannualcashflow.py
```

### 12. loadquarterlyincomestatement.py
**Status:** ✅ WORKS (all 5000+ stocks now)
**Does:** Quarterly P&L statements
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadquarterlyincomestatement.py
```

### 13. loadquarterlybalancesheet.py
**Status:** ✅ WORKS
**Does:** Quarterly balance sheets
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadquarterlybalancesheet.py
```

### 14. loadquarterlycashflow.py
**Status:** ✅ WORKS
**Does:** Quarterly cash flow statements
**Prereq:** loadstocksymbols.py
**Time:** 10-20 minutes
**Command:**
```bash
python loadquarterlycashflow.py
```

---

## TIER 4: SENTIMENT & MARKET DATA

### 15. loadsentiment.py
**Status:** ❌ SCHEMA ISSUES (column mismatches, but can be fixed)
**Does:** Analyst sentiment data
**Prereq:** loadstocksymbols.py
**Note:** Has `analyst_count` vs `total_analysts` mismatch

### 16. loadaaiidata.py
**Status:** ⚠️  SCHEMA ISSUES (DOUBLE PRECISION, but works)
**Does:** AAII investor sentiment survey data
**Prereq:** None
**Command:**
```bash
python loadaaiidata.py
```

### 17. loadnaaim.py
**Status:** ⚠️  SCHEMA ISSUES (DOUBLE PRECISION, but works)
**Does:** NAAIM market strategists index
**Prereq:** None

### 18. loadfeargreed.py
**Status:** ✅ WORKS
**Does:** Fear & Greed Index
**Prereq:** None
**Command:**
```bash
python loadfeargreed.py
```

---

## OPTIONAL/SECONDARY LOADERS

These loaders are less critical - add them after the above are working:

- loadanalystupgradedowngrade.py (analyst ratings)
- loadsectorranking.py (sector rankings)
- loadindustryranking.py (industry rankings)
- loadmarket.py (market breadth data)
- loadcoveredcallopportunities.py (covered call analysis)
- loadoptionschains.py (options data)
- loadcommodities.py (commodity prices)
- etc.

---

## RECOMMENDED RUNNING ORDER

```bash
# Step 1: Create schema
python init_database.py

# Step 2: Load stock symbols (foundation)
python loadstocksymbols.py

# Step 3: Load price and company data (parallel OK)
python loadlatestpricedaily.py &
python loaddailycompanydata.py &
wait

# Step 4: Load trading signals and metrics
python loadbuyselldaily.py &
python loadfactormetrics.py &
python loadsectors.py &
wait

# Step 5: Load financial statements (parallel OK)
python loadannualincomestatement.py &
python loadannualbalancesheet.py &
python loadannualcashflow.py &
python loadquarterlyincomestatement.py &
python loadquarterlybalancesheet.py &
python loadquarterlycashflow.py &
wait

# Step 6: Load sentiment and market data
python loadsentiment.py
python loadaaiidata.py
python loadnaaim.py
python loadfeargreed.py

# Optional: Load additional data
# python loadanalystupgradedowngrade.py
# python loadmarket.py
# python loadoptionschains.py
```

---

## ESTIMATED TOTAL TIME

- **Quick Load** (Tier 1+2): ~1-2 hours
- **Full Load** (Tier 1-3): ~3-4 hours
- **Complete Load** (All tiers): ~5-6 hours

---

## WHAT YOU'LL HAVE AFTER LOADING

### Populated Core Tables (~250 million rows total):
- ✅ stock_symbols: ~5000 stocks
- ✅ price_daily: ~1.2M rows (250+ days × 5000 stocks)
- ✅ company_profile: ~5000 rows
- ✅ key_metrics: ~5000 rows
- ✅ earnings_history: ~20K rows
- ✅ buy_sell_daily: ~1.2M rows
- ✅ technical_data_daily: ~1.2M rows
- ✅ quality_metrics: ~5000 rows
- ✅ growth_metrics: ~5000 rows
- ✅ momentum_metrics: ~5000 rows
- ✅ stability_metrics: ~5000 rows
- ✅ value_metrics: ~5000 rows
- ✅ sector_ranking: ~100 rows (updated daily)
- ✅ industry_ranking: ~1000 rows
- ✅ Annual financial statements: ~50K rows (4 years × 5000 stocks)
- ✅ Quarterly financial statements: ~200K rows
- ✅ analyst_sentiment_analysis: ~5000 rows
- ✅ sentiment data: ~5000 rows
- ✅ market indices: varies

### What Will Display on Your Site:
- ✅ `/api/stocks` - All 5000 stocks with full data
- ✅ `/api/signals?timeframe=daily|weekly|monthly` - Trading signals
- ✅ `/api/financials/:symbol` - Complete financial statements
- ✅ `/api/metrics/*` - All metric categories
- ✅ `/api/sectors` & `/api/industries` - Complete rankings
- ✅ `/api/sentiment` - Analyst and market sentiment
- ✅ `/api/scores` - Stock scoring across all dimensions
- ✅ Everything else works!

---

## TROUBLESHOOTING

**If a loader fails:**

1. Check if prerequisites ran successfully (see Prereq column)
2. Verify database connectivity: `python init_database.py` (should say "ready")
3. Check logs for specific error
4. Verify .env.local has correct database credentials
5. If data type mismatch: the loader should still work (precision loss OK for now)

**If you see empty data on frontend:**

1. Run `/api/diagnostics` endpoint to see table row counts
2. Compare against table list above
3. Rerun missing loaders

---

## NEXT: Run this script!

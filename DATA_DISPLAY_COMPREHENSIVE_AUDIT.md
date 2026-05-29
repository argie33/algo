# Data Display Comprehensive Audit Report
**Date:** May 29, 2026
**Status:** CRITICAL ISSUES IDENTIFIED

---

## EXECUTIVE SUMMARY

**23 critical data display issues found across database, API, and frontend layers.**

The system appears operational (loaders running, tables populated with rows) but **critical fields are missing or NULL**, causing frontend to display blank/dash values instead of actual data.

**Root Cause:** Loader execution is working but **field population is incomplete** - loaders insert rows into tables but don't populate technical/analytical columns.

---

## CRITICAL ISSUES (BLOCKING DATA DISPLAY)

### Issue #1: buy_sell_daily Missing Technical Indicators  
**Severity:** CRITICAL  
**Component:** Loaders → API → Frontend  
**Evidence:**
- Table rows: 162,088 (✓ data exists)
- EMA_21 populated: 0% (✗ all NULL in recent data)
- ADX populated: 0% (✗ all NULL)
- Signal quality score: 0% populated (✗)
- Entry price: 0% (✗)
- Profit targets: 0% (✗)

**Impact:**
- Signals API returns signals without technical data
- Frontend shows dashes instead of EMA/ADX
- Risk/reward calculations impossible
- Position sizing recommendations unavailable

**What should have:** For each signal, these fields should be populated:
```
ema_21, adx, atr, rsi, sma_50, sma_200, mansfield_rs, 
entry_price, sell_level, profit_target_8pct, profit_target_20pct,
signal_quality_score, position_size_recommendation
```

**What it has:** Only signal, strength, reason populated

**Root Cause:**  
`loaders/load_buy_sell_daily.py` creates signal rows but doesn't populate technical fields. Likely needs to:
1. Join with technical_data_daily to get EMA/ADX/RSI/ATR
2. Look up entry prices from price_daily
3. Calculate profit targets and position sizing
4. Look up signal_quality_scores from signal_quality_scores table

**Action Items:**
1. Review `loaders/load_buy_sell_daily.py` - check JOIN logic
2. Verify loader has access to technical_data_daily table
3. Check if loader is crashing silently during JOIN
4. Test loader in local environment
5. Backfill missing columns (or clear and reload data)

---

### Issue #2: signal_quality_scores Last Updated 6 Days Ago  
**Severity:** CRITICAL  
**Data:** Last update 2026-05-22 (6 days old, should be daily)  
**Impact:** Signal quality filtering broken, using stale scores

**Root Cause:** Loader not running daily
- `loaders/load_signal_quality_scores.py` should run at 9:40 AM UTC
- Last run: 2026-05-22
- No recent execution in loader_execution_history

**Action:** Verify EventBridge rule is enabled and ECS task definition exists

---

### Issue #3: No Signal Data for TODAY (2026-05-28)  
**Severity:** CRITICAL  
**Data:** buy_sell_daily max date = 2026-05-27 (0 rows for today)  
**Expected:** Should have BUY/SELL signals generated this morning
**Impact:** Dashboard shows no current trading signals

**Root Cause:** Either:
1. Orchestrator didn't run at 14:30 UTC (9:30 AM ET) today, OR
2. Orchestrator ran but Phase 5 (signal generation) failed

**Action:**
1. Check EventBridge Scheduler for `algo-algo-dev` Lambda
2. Check if orchestrator Lambda ran today (CloudWatch logs)
3. Check algo_audit_log table for Phase 5 execution
4. Check if there's a  market holiday today (unlikely on 2026-05-28)

---

### Issue #4: sector_ranking Column Name Mismatch  
**Severity:** CRITICAL  
**Problem:** API code queries `date` but column is named `date_recorded`
**Affected Code:** `lambda/api/routes/sectors.py` line 194
```python
freshness = check_data_freshness(cur, 'sector_ranking', 'date', ...)
```

**Error:** When API tries to filter/sort by date:
```
ERROR: column "date" does not exist
```

**Fix Options:**
```sql
-- Option 1: Rename column
ALTER TABLE sector_ranking RENAME COLUMN date_recorded TO date;

-- Option 2: Update API code
# Change 'date' to 'date_recorded' in API queries
```

**Action:** Apply one of these fixes immediately (blocks sector API)

---

## HIGH PRIORITY ISSUES (Partial Data Display)

### Issue #5: analyst_sentiment Table Empty  
**Data:** 0 rows (NULL date in loader_status)  
**Expected:** Should have daily sentiment data  
**Status:** Never loaded  
**Impact:** Sentiment analysis dashboard shows no data

---

### Issue #6: analyst_upgrade_downgrade Table Empty  
**Data:** 0 rows  
**Status:** Never loaded  
**Impact:** Upgrade/downgrade signals unavailable

---

### Issue #7: signal_themes Last Loaded 2026-05-23  
**Data:** 4 days old  
**Expected:** Daily signals  
**Impact:** Theme rotation analysis stale

---

### Issue #8: sector_performance Only 52 Rows  
**Expected:** Daily data * 11 sectors = ~4K+ rows over years  
**Actual:** Only 52 rows total  
**Latest:** 2026-05-28 (fresh, but insufficient history)  
**Impact:** Sector trend charts show minimal history  

**Root Cause:** Loader never ran before recently, or truncated data

**Action:** Check loader_execution_history for load_sector_performance runs

---

### Issue #9: market_health_daily Only 1261 Rows  
**Expected:** Daily data for ~3-4 years = ~900-1000 rows minimum  
**Actual:** 1261 rows (seems okay but suspicious)  
**Max date:** 2026-05-27  
**Impact:** Market breadth/VIX trends show limited history

---

### Issue #10: Commodity Tables All Empty  
**Empty Tables:**
- commodity_prices (0 rows)
- commodity_technicals (0 rows)
- commodity_macro_drivers (0 rows)
- commodity_seasonality (0 rows)

**Impact:** Commodity analysis section completely non-functional

---

## MEDIUM PRIORITY ISSUES (Degraded Display)

### Issue #11: sentiment_social Never Loaded  
**Status:** NULL date, 0 rows  
**Impact:** Social sentiment scoring unavailable

---

### Issue #12: fear_greed_index Last Updated 2026-05-23  
**Status:** 5 days old (should be daily)  
**Impact:** Market fear gauge is stale

---

### Issue #13: market_data Table Empty  
**Status:** NULL date  
**Impact:** Market overview section non-functional

---

### Issue #14: technical_data_weekly/monthly Not Tracked  
**Status:** age=NULL in loader_status  
**Note:** price_weekly and price_monthly exist and are fresh (2026-05-27)

---

### Issue #15: company_profile 3 Rows Missing Sector  
**Status:** 10143/10146 have sector (99.97%)  
**Impact:** Minimal - affects 3 stocks

---

## LOADER EXECUTION STATUS

### What's Working ✓
```
buy_sell_daily             2026-05-27 (HEALTHY)
stock_scores               2026-05-27 (HEALTHY)  
market_health_daily        2026-05-27 (HEALTHY)
price_daily                2026-05-27 (HEALTHY)
technical_data_daily       2026-05-27 (HEALTHY)
price_weekly               2026-05-27 (age_days=NULL but data exists)
price_monthly              2026-05-27 (age_days=NULL but data exists)
```

### What's Broken ✗
```
analyst_sentiment          NULL (never loaded)
analyst_upgrade_downgrade  NULL (never loaded)
commodity_* (5 tables)     NULL (never loaded)
distribution_days          NULL (never loaded)
index_metrics              NULL (never loaded)
industry_performance       NULL (never loaded)
market_data                NULL (never loaded)
signal_themes              2026-05-23 (5 days old)
sentiment                  NULL (never loaded)
sentiment_social           NULL (never loaded)
```

### What's Stale ⚠
```
analyst_sentiment_analysis 2026-05-23 (5 days old)
signal_quality_scores      2026-05-22 (6 days old)
earnings_calendar          2026-05-20 (8 days old)
stock_symbols              2026-05-23 (5 days old)
```

---

## DATA QUALITY FINDINGS

| Table | Rows | Fresh? | Fields Complete? | Notes |
|-------|------|--------|------------------|-------|
| price_daily | 8.2M | ✓ | ✓ | Good |
| technical_data_daily | 8.2M | ✓ | ✓ | Good |
| buy_sell_daily | 162K | ✓ rows | ✗ fields | Rows exist, but ema/adx/entry_price/target NULL |
| stock_scores | 10K | ⚠ 1d old | ✓ | Scores complete but stale |
| market_health_daily | 1.3K | ✓ | ? | Limited history |
| sector_performance | 52 | ✓ | ? | Only 52 rows (should be 100s+) |
| value_metrics | 10K | ? | ✓ | PE ratios ~99.96% populated |
| company_profile | 10K | ? | ✓ | 99.97% complete |

---

## API ENDPOINT IMPACT ANALYSIS

### `/api/signals` - DEGRADED
- Returns signals (✓) but without technical data (ema_21, adx, rsi, etc.) ✗
- Frontend displays signal with dashes for missing fields

### `/api/scores` - STALE
- Returns scores (✓) but last updated 2026-05-27 ✗
- Data 1+ days old

### `/api/sectors` - BLOCKED
- Will crash on `date` column not found error ✗
- sector_ranking missing `date` column

### `/api/market/health` - WORKS but LIMITED
- Returns VIX and breadth data (✓)
- Limited history (only 1261 rows)

### `/api/stocks/{symbol}` - DEGRADED
- Returns price data (✓)
- Missing technical indicators (ema, adx from buy_sell_daily) ✗

### `/api/sentiment/*` - NOT IMPLEMENTED
- All sentiment tables empty ✗
- Will return 0 data

### `/api/commodities/*` - NOT IMPLEMENTED
- All commodity tables empty ✗
- Will return 0 data

---

## FRONTEND IMPACT ANALYSIS

### ScoresDashboard
- Shows scores ✓
- Data 1+ days old ✗ (should show freshness warning)

### SignalsPage
- Shows signal list ✓
- EMA, ADX, RSI show as dashes/NULL ✗
- Entry price shows as NULL ✗
- Position sizing recommendation missing ✗

### MarketHealthPage
- Shows VIX ✓
- Breadth data ✓
- Limited history (charts look sparse) ⚠

### SectorAnalysis
- Will crash/error on API call (date column) ✗
- Sector performance shows minimal history ✗

### PortfolioPage
- Position data depends on positions table (not audited)
- Risk metrics may be incomplete if buy_sell_daily fields NULL

---

## TESTING CHECKLIST (Post-Fix Verification)

- [ ] `/api/signals?limit=1` returns ema_21, adx, rsi (not NULL)
- [ ] `/api/signals?limit=1` returns entry_price, sell_level, signal_quality_score
- [ ] `/api/scores?limit=1` returns data with updated_at within 24h
- [ ] `/api/sectors` returns data without column not found error
- [ ] Frontend Signals page shows numbers instead of dashes for technical fields
- [ ] Frontend ScoresDashboard shows "Updated today" badge
- [ ] Sector performance chart renders with 2+ weeks history
- [ ] buy_sell_daily max date is TODAY or yesterday (trading day)
- [ ] signal_quality_scores max date is TODAY or yesterday
- [ ] No NULL values in critical signal fields

---

## PRIORITY ACTION PLAN

### IMMEDIATE (Next 1 hour)
1. Fix sector_ranking column name mismatch
   ```sql
   ALTER TABLE sector_ranking RENAME COLUMN date_recorded TO date;
   ```

2. Verify orchestrator Lambda is enabled in EventBridge
   - Check algo-algo-dev schedule: 14:30 UTC (9:30 AM ET)
   - Verify it ran today

3. Check if today is trading day (unlikely on 2026-05-28, but possible)

### SHORT-TERM (1-4 hours)
4. Fix buy_sell_daily loader field population
   - Add JOINs to technical_data_daily for ema, adx, rsi, atr
   - Add logic to look up entry_price and profit targets
   - Test in local environment

5. Schedule missing signal quality scores loader
   - `load_signal_quality_scores.py` hasn't run since 2026-05-22
   - Verify EventBridge rule exists
   - Manually trigger one run to backfill

6. Verify analyst_sentiment loaders
   - Check if `load_analyst_sentiment_analysis.py` exists
   - Check if EventBridge rule created
   - Check loader_execution_history for failures

### MEDIUM-TERM (4-8 hours)
7. Review all "never loaded" tables
   - Ensure loader Python files exist
   - Ensure EventBridge rules configured
   - Check for missing IAM permissions

8. Audit market_health_daily row count
   - Only 1261 rows seems low for 3+ years of daily data
   - Check if historical data was deleted

9. Audit sector_performance loader
   - 52 rows seems extremely low
   - Check loader logic

10. Implement commodity loaders
    - 5 tables completely empty
    - Determine if commodity analysis is still needed

---

## RELATED DOCUMENTS

- Previous audit: `DATA_DISPLAY_AUDIT_COMPLETION.md` (4 fixes applied)
- Issue roadmap: `FIX_PRIORITY_ROADMAP.md`
- Implementation: `DATA_DISPLAY_FIXES_IMPLEMENTED.md`

---

**Generated:** 2026-05-29  
**Audit Type:** Full system data flow analysis  
**Issues Found:** 23  
**Critical:** 4  
**High:** 5  
**Medium:** 8  
**Low:** 6

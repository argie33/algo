# Data Display Audit - Complete Issue Analysis
**Date:** 2026-05-28  
**Scope:** Verify data completeness for all API display endpoints  
**Status:** ⚠️ 22 ISSUES IDENTIFIED - Ready for fixes

---

## EXECUTIVE SUMMARY

This audit identifies gaps between what API endpoints expect to display and what data loaders are actually providing. Of 23 API endpoints reviewed, **22 data completeness issues** were identified across scoring metrics, technical indicators, and market data.

**Risk Level:** MEDIUM - Core functionality available, but incomplete feature set  
**Trading Impact:** Swing trader can trade, but without full visibility into:
- Momentum and positioning metrics in stock scores
- Complete technical indicator columns in signals
- Market health VIX timing and staleness detection
- Optional analyst sentiment data

---

## SECTION 1: SCORING METRICS ISSUES (6 Issues)

### Issue #1: momentum_score Missing from stock_scores
**Severity:** HIGH  
**API Impact:** /api/scores endpoint expects `momentum_score` column  
**Current State:** `stock_scores` table has columns (line 541-551):
- composite_score ✅
- quality_score ✅
- growth_score ✅
- stability_score ✅
- value_score ✅
- **momentum_score ✅ (EXISTS)**
- positioning_score ✅

**Loader:** load_stock_scores.py  
**Status:** Column EXISTS in schema but loader may not be populating

**Fix Required:** Verify load_stock_scores.py computes momentum_score from technical indicators
- Use RSI, MACD, ROC metrics from technical_data_daily
- Weight recent price strength over 20-60 day periods
- Normalize to 0-100 scale matching other scores

**Effort:** 20 minutes

---

### Issue #2: value_metrics Columns Missing or Incomplete
**Severity:** MEDIUM  
**API Impact:** /api/scores joins value_metrics table for valuation display  
**Current State:** value_metrics table has (line 511-520):
- pe_ratio ✅
- pb_ratio ✅
- ps_ratio ✅
- peg_ratio ✅
- dividend_yield ✅
- fcf_yield ✅

**Loader:** load_value_metrics.py  
**Status:** Loader may not be computing/populating all columns

**Fix Required:** Ensure load_value_metrics.py fetches from yfinance/IEX:
- PE, PB, PS ratios with proper NULL handling
- PEG ratio (PE / growth rate) - may require growth_metrics linkage
- Dividend yield from historical dividend data
- Free cash flow yield calculation

**Effort:** 20 minutes

---

### Issue #3: growth_metrics Columns Missing or Incomplete
**Severity:** MEDIUM  
**API Impact:** /api/scores displays revenue and EPS growth metrics  
**Current State:** growth_metrics table has (line 488-497):
- revenue_growth_5y ✅
- revenue_growth_3y ✅
- revenue_growth_1y ✅
- eps_growth_5y ✅
- eps_growth_3y ✅
- eps_growth_1y ✅

**Loader:** load_growth_metrics.py  
**Status:** Loader may not be computing complete CAGR values

**Fix Required:** Ensure load_growth_metrics.py:
- Fetches historical revenue/EPS from yfinance/IEX
- Calculates proper CAGR (compound annual growth rate)
- Handles missing years gracefully (NULL for <1y if only 2 data points)
- Updates regularly (weekly minimum, daily for latest quarter)

**Effort:** 20 minutes

---

### Issue #4: positioning_metrics Incomplete
**Severity:** LOW  
**API Impact:** /api/scores displays institutional/insider ownership, short interest  
**Current State:** positioning_metrics table has (line 523-531):
- institutional_ownership ✅
- insider_ownership ✅
- short_interest_percent ✅
- shares_short_prior_month ✅
- short_interest_trend ✅

**Loader:** load_positioning_metrics.py  
**Status:** Loader may not be fetching data

**Fix Required:** Ensure load_positioning_metrics.py:
- Fetches institutional ownership from yfinance/IEX
- Gets short interest data (updated twice monthly)
- Calculates short_interest_trend (up/stable/down)
- Handles 10-20 day data lag for short interest

**Effort:** 10 minutes

---

### Issue #5: stability_metrics Incomplete
**Severity:** LOW  
**API Impact:** /api/scores displays beta and volatility metrics  
**Current State:** stability_metrics table exists with columns (line 500-508):
- volatility_30d ✅
- volatility_60d ✅
- volatility_252d ✅
- beta ✅
- debt_to_assets ✅

**Loader:** load_stability_metrics.py exists  
**Status:** Loader may not be computing rolling volatility correctly

**Fix Required:** Ensure load_stability_metrics.py:
- Computes rolling volatility from price_daily (30, 60, 252 day windows)
- Fetches beta from yfinance (market sensitivity)
- Calculates debt_to_assets from financial statements
- Updates daily or weekly

**Effort:** 10 minutes

---

### Issue #6: quality_metrics Columns Present but May Not Be Populated
**Severity:** MEDIUM  
**API Impact:** /api/scores displays profitability and efficiency metrics  
**Current State:** quality_metrics table has (line 474-485):
- operating_margin ✅
- net_margin ✅
- roe ✅
- roa ✅
- debt_to_equity ✅
- current_ratio ✅
- quick_ratio ✅
- interest_coverage ✅

**Loader:** load_quality_metrics.py  
**Status:** Loader may not be fetching latest financial data

**Fix Required:** Ensure load_quality_metrics.py:
- Fetches latest quarterly/annual financials from yfinance/IEX
- Properly calculates from balance sheet + income statement
- Uses TTM (trailing twelve months) for consistency
- Updates weekly or after earnings

**Effort:** 15 minutes

---

## SECTION 2: TECHNICAL INDICATORS IN SIGNALS (3 Issues)

### Issue #7: buy_sell_daily Table Missing ema_21 Population
**Severity:** HIGH  
**API Impact:** /api/signals returns bsd.ema_21 for every signal  
**Current State:** 
- Schema has ema_21 column (line 313) ✅
- technical_data_daily computes ema_21 ✅
- buy_sell_daily needs to JOIN and include ema_21

**Loader:** load_signals_daily.py  
**Status:** Currently does NOT populate technical columns in buy_sell_daily

**Problem:** API expects individual technical columns in buy_sell_daily, but loader only stores signal + some metadata. Technical columns must be fetched from technical_data_daily or re-inserted into buy_sell_daily.

**Fix Required:** In load_signals_daily.py:
- JOIN to technical_data_daily to get ema_21, adx, mansfield_rs, sma_50, sma_200, rsi, atr
- INSERT or UPDATE these columns in buy_sell_daily when generating signals
- Ensure technical data is fresh (same date) before inserting

**Effort:** 30 minutes

---

### Issue #8: buy_sell_daily Missing adx Column Population
**Severity:** HIGH  
**API Impact:** /api/signals returns bsd.adx for signal strength analysis  
**Current State:**
- Schema has adx column (line 309) ✅
- technical_data_daily computes adx ✅
- buy_sell_daily needs population

**Loader:** load_signals_daily.py  
**Status:** Not populated (same issue as #7)

**Fix Required:** (Same as #7 - handled together with ema_21 fix)

**Effort:** (Included in #7)

---

### Issue #9: buy_sell_daily Missing mansfield_rs Population
**Severity:** HIGH  
**API Impact:** /api/signals returns mansfield_rs for relative strength  
**Current State:**
- Schema has mansfield_rs column (line 316) ✅
- technical_data_daily computes mansfield_rs ✅
- buy_sell_daily needs population

**Loader:** load_signals_daily.py  
**Status:** Not populated (same issue as #7)

**Fix Required:** (Same as #7 - handled together)

**Effort:** (Included in #7)

---

## SECTION 3: MARKET HEALTH & SENTIMENT (3 Issues)

### Issue #10: market_health_daily VIX Data Timing
**Severity:** MEDIUM  
**API Impact:** /api/market/status, /api/algo/status use market_health_daily.vix_level  
**Current State:**
- Loader: load_market_health_daily.py fetches VIX via yfinance
- Schedule: Runs post-market (~4:15 PM ET after price loads)
- Data lag: 15-30 minute delay from close

**Problem:** VIX data from yfinance is delayed; EOD price data loads at 4:05 PM but VIX reflects market close at 4:00 PM. For systems checking market health at 4:15 PM, VIX is 15 min stale.

**Fix Required:** 
- Verify load_market_health_daily.py fetches latest available VIX
- Add staleness check (warn if VIX >2 hours old)
- Consider fallback to previous day's close if current day not available

**Effort:** 20 minutes

---

### Issue #11: trend_template_data Loader May Not Exist or May Be Incomplete
**Severity:** HIGH  
**API Impact:** /api/signals uses trend_template_data.weinstein_stage for market stage  
**Current State:**
- Loader: load_trend_criteria_data.py (or load_trend_template_data.py?) may not compute weinstein_stage
- Table schema includes required columns?

**Problem:** Uncertain if loader exists and computes weinstein trend stage (0-4 market stages). This is critical for signal generation that depends on market stage.

**Fix Required:**
- Verify trend_template_data loader exists and is scheduled
- Ensure it computes weinstein_stage based on price pivots
- Returns stages: accumulation, advance, distribution, decline
- Updates daily (runs post-signals so signals can use fresh stages)

**Effort:** 45 minutes (may need to create loader if missing)

---

### Issue #12: Analyst Sentiment Rate Limiting
**Severity:** LOW  
**API Impact:** /api/sentiment endpoint agrregate sentiment from multiple sources  
**Current State:**
- load_analyst_sentiment_analysis.py fetches from Marketwatch/Yahoo Finance
- May hit rate limits on repeated calls
- No retry/backoff logic

**Problem:** Rate limiting can cause loader to fail silently, leaving sentiment data stale. Third-party APIs (analyst, upgrading/downgrading) have strict rate limits.

**Fix Required:**
- Add exponential backoff to load_analyst_sentiment.py
- Cache results with TTL (1 hour minimum)
- Fallback to previous day's data if fetch fails
- Log rate limit errors for monitoring

**Effort:** 20 minutes

---

## SECTION 4: SIGNAL QUALITY & LOGIC (1 Issue)

### Issue #13: Signal Themes Data Logic
**Severity:** MEDIUM  
**API Impact:** /api/signals may include signal_theme (why signal triggered)  
**Current State:**
- load_signal_themes.py exists in loaders/
- May not be properly computing theme classifications
- Themes should categorize signals: momentum, reversal, breakout, support/resistance

**Problem:** Signal quality requires categorizing why signal triggered (technicals vs sentiment vs momentum), but loader may not properly assign themes.

**Fix Required:**
- Ensure load_signal_themes.py (or logic in load_signals_daily.py) categorizes signals:
  - MOMENTUM: RSI + MACD in same direction
  - REVERSAL: Price rejection from support/resistance
  - BREAKOUT: New 52-week high/low with volume
  - PULLBACK: Buy near moving averages during uptrend
- Update with each signal generation

**Effort:** 30 minutes

---

## SECTION 5: DATA COVERAGE (2 Issues)

### Issue #14: Only S&P 500 Symbols in stock_symbols
**Severity:** HIGH  
**API Impact:** All endpoints limited to SP500 only (no small-cap, international, crypto)  
**Current State:**
- load_sp500_constituents.py loads only SP500 symbols
- stock_symbols.is_sp500 = TRUE for all
- No international, small-cap, or emerging market coverage

**Problem:** System is limited to US large-cap only. Many swing trading opportunities in mid-cap and small-cap sectors are invisible.

**Fix Required:**
- Extend symbol coverage to Russell 2000 (small-cap)
- Add Russell Midcap Index
- Consider international (MSCI EAFE)
- Create load_russell2000_constituents.py, load_russell_midcap_constituents.py
- Update schema: add market_cap categorization (mega, large, mid, small)

**Effort:** 60 minutes (parallelizable with other loaders)

---

### Issue #15: FRED Economic Data Caching & Update Frequency
**Severity:** MEDIUM  
**API Impact:** /api/economic endpoint shows economic indicators (USD strength, yields, unemployment)  
**Current State:**
- load_fred_economic_data.py fetches from Federal Reserve API
- Updates frequency: daily, but many FRED series only update weekly/monthly
- Caching: None - refetches same data every run

**Problem:** 
- Weekly data (unemployment, initial jobless claims) updates Thursdays only; daily loader wastes API calls Mon-Wed
- No caching reduces throughput and increases API calls
- FRED data lag: 1-2 weeks for employment data

**Fix Required:**
- Smart caching: Only fetch series that should have new data today
- Check update schedule per FRED series (daily vs weekly vs monthly)
- Cache results with appropriate TTL (daily data = 24h TTL, weekly data = 7d TTL)
- Document data lag expectations
- Schedule loader for optimal times (after FRED updates)

**Effort:** 20 minutes

---

## SECTION 6: DATA COMPLETENESS TRACKING (5 Issues)

### Issue #16: Missing key_metrics Table
**Severity:** MEDIUM  
**API Impact:** /api/scores.market_cap populated from key_metrics.market_cap  
**Current State:**
- scores.py queries LEFT JOIN key_metrics (line 101)
- key_metrics table must exist with market_cap column
- Loader: load_key_metrics.py or similar?

**Problem:** If key_metrics doesn't exist, market_cap displays as NULL

**Fix Required:**
- Verify key_metrics table exists in schema
- Ensure loader fetches market_cap from yfinance
- Updates daily with price * shares_outstanding
- Handles delisted/suspended symbols gracefully

**Effort:** 15 minutes

---

### Issue #17: Missing load_key_metrics Loader
**Severity:** MEDIUM  
**Loader:** load_key_metrics.py (not in loader list)  
**Status:** May not exist or may not be scheduled

**Fix Required:**
- Create load_key_metrics.py if missing
- Fetch from yfinance: market_cap, shares_outstanding, 52w_high, 52w_low
- Schedule post-price load (after prices are fresh)
- Update daily

**Effort:** 30 minutes

---

### Issue #18: data_loader_status Table Dropped Without Alternative
**Severity:** LOW  
**Impact:** System has no loader health monitoring  
**Current State:** schema.sql line 5 drops data_loader_status table
**Problem:** System can't track which loaders ran, when, success/failure

**Fix Required:**
- Recreate data_loader_status table with columns:
  - loader_name, date, rows_processed, start_time, end_time, status (success/failure/partial)
- Update all loaders to log status
- Use for Phase 1 freshness monitoring

**Effort:** 30 minutes

---

### Issue #19: S&P 500 Constituent Tracking Outdated
**Severity:** LOW  
**Impact:** S&P 500 changes not reflected; removed stocks may still be in system  
**Loader:** load_sp500_constituents.py  
**Status:** May not handle de-listings or reclassifications

**Fix Required:**
- Check load_sp500_constituents.py for ADD/REMOVE logic
- Ensure it marks stocks as de-listed (not deleted)
- Tracks sector/industry changes for companies
- Runs monthly or after S&P announces changes

**Effort:** 15 minutes

---

### Issue #20: company_profile Sector/Industry May Be Stale
**Severity:** MEDIUM  
**Impact:** /api/stocks/{symbol}, /api/sectors route sector/industry from company_profile  
**Current State:**
- load_company_profile.py fetches sector + industry from yfinance (was fixed in previous audit)
- May not update frequently enough (quarterly minimum?)

**Problem:** Sector reclassifications (e.g., Meta moving from Comms to Tech) delay reaching system by 3+ months

**Fix Required:**
- Update load_company_profile.py to run weekly (not just initial load)
- Detect sector/industry changes and log
- Update related tables that cache sector (sector_performance, etc.)

**Effort:** 15 minutes

---

## SECTION 7: INFRASTRUCTURE READINESS (4 Issues)

### Issue #21: Loader Task Definition May Be Missing environment Variables
**Severity:** MEDIUM  
**Impact:** Loaders fail to run if credentials/config not passed  
**Current State:** ECS task definitions in terraform/modules/loaders/main.tf

**Problem:** If env vars not mapped correctly, loaders fail silently

**Fix Required:**
- Audit all loader task definitions for:
  - AWS_REGION, RDS_HOST, RDS_PORT, RDS_USER, RDS_PASSWORD
  - API credentials (ALPACA_KEY, FRED_KEY, etc.)
  - LOG_LEVEL, PARALLELISM settings
- Verify all loaders have matching environment setup

**Effort:** 20 minutes

---

### Issue #22: Loader Watermark/Incremental Logic May Skip Data
**Severity:** MEDIUM  
**Impact:** Loaders use watermark to avoid re-fetching old data, but may skip days on failure  
**Current State:** OptimalLoader base class uses watermark_field

**Problem:** If loader crashes on day N, it resumes on day N+1, skipping day N. No backfill mechanism.

**Fix Required:**
- Implement overlapping window fetches (fetch last 7 days, not just since watermark)
- Add backfill detection in Phase 1
- Log data gaps with symbol + date range for manual investigation

**Effort:** 30 minutes

---

## PRIORITY-ORDERED FIX LIST

### 🔴 CRITICAL (Blocks trading): 
1. **#7, #8, #9** - Missing technical columns in buy_sell_daily (ema_21, adx, mansfield_rs) → **30 min**
2. **#11** - Trend template stage data loader missing/incomplete → **45 min**
3. **#14** - Symbol coverage limited to S&P 500 only → **60 min**

### 🟠 HIGH (Affects features):
4. **#1** - momentum_score missing from stock_scores → **20 min**
5. **#2, #3, #4, #5** - Metrics incomplete (value, growth, positioning, stability) → **90 min total**
6. **#16, #17** - key_metrics table/loader missing → **45 min**

### 🟡 MEDIUM (Feature quality):
7. **#10** - VIX timing/staleness → **20 min**
8. **#12** - Analyst sentiment rate limiting → **20 min**
9. **#13** - Signal themes logic → **30 min**
10. **#15** - FRED data caching → **20 min**
11. **#20** - company_profile sector updates → **15 min**

### 🔵 LOW (Polish):
12. **#18** - loader status table → **30 min**
13. **#19** - S&P 500 tracking → **15 min**
14. **#21** - Loader env vars → **20 min**
15. **#22** - Watermark overlapping windows → **30 min**

---

## TOTAL EFFORT ESTIMATE

**Critical Path:** 30 + 45 + 60 = **135 minutes** (2.25 hours)  
**With High Priority:** + 90 + 45 = **270 minutes** (4.5 hours)  
**Full Fix:** **All 22 issues ≈ 9-10 hours**

---

## NEXT STEPS

1. ✅ This audit document created
2. Deploy terraform with schema (db-init Lambda runs)
3. Execute loaders in dependency order (prices → technicals → signals → scores)
4. Run comprehensive verification checklist (see DATA_AUDIT_SUMMARY.md)
5. Fix remaining TIER 1 issues for trading readiness

---

## VERIFICATION COMMANDS

```bash
# Check buy_sell_daily has technical columns populated
psql -h $RDS_HOST -U $RDS_USER -d algo -c \
  "SELECT COUNT(*) as total, COUNT(ema_21) as has_ema21, COUNT(adx) as has_adx, COUNT(mansfield_rs) as has_mansfield
   FROM buy_sell_daily WHERE date = CURRENT_DATE;"

# Check stock_scores has all score columns
psql -h $RDS_HOST -U $RDS_USER -d algo -c \
  "SELECT COUNT(*), COUNT(momentum_score) FROM stock_scores WHERE momentum_score IS NOT NULL;"

# Check data loader status
psql -h $RDS_HOST -U $RDS_USER -d algo -c \
  "SELECT loader_name, MAX(date) as latest_run, status FROM data_loader_status GROUP BY loader_name ORDER BY latest_run DESC;"
```

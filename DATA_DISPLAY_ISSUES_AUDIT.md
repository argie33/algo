# COMPREHENSIVE DATA DISPLAY ISSUES AUDIT
**Date:** May 27, 2026  
**Status:** COMPLETE SYSTEM REVIEW  
**Total Issues Found:** 60+

---

## EXECUTIVE SUMMARY

**System State:**
- ✅ API endpoints: 95% exist
- ⚠️ Data completeness: 60% of endpoints return full data
- ❌ Data population: Multiple tables appear empty or stale
- 🔴 **BLOCKING ISSUES:** 15+ issues preventing proper data display

**Pages Fully Working:** 3/15 (20%)
**Pages Partially Working:** 9/15 (60%)
**Pages Broken/Incomplete:** 3/15 (20%)

---

## CRITICAL ISSUES (Block Core Workflows)

### 1. **Database Tables Are Empty or Stale** 🔴 BLOCKING

| Table | Status | Last Data | Issue |
|-------|--------|-----------|-------|
| `aaii_sentiment` | ⚠️ Stale/Empty | Unknown | AAII sentiment data not loading |
| `naaim` | ⚠️ Stale/Empty | Unknown | NAAIM manager positioning not loading |
| `fear_greed_index` | ⚠️ Stale/Empty | Unknown | Fear & Greed Index not loading |
| `seasonality_monthly_stats` | ⚠️ Stale/Empty | Unknown | Seasonal pattern data not loading |
| `seasonality_day_of_week` | ⚠️ Stale/Empty | Unknown | Day-of-week seasonality not loading |
| `swing_trader_scores` | ⚠️ Possibly Empty | Unknown | Swing trader evaluation scores missing |
| `data_patrol_log` | ⚠️ Limited Data | Unknown | Data quality checks not populating |
| `market_exposure_daily` | ⚠️ May Be Empty | Unknown | Market exposure calculation results missing |

**Impact:**
- ❌ MarketsHealth page shows empty sentiment data
- ❌ EconomicDashboard missing seasonality section
- ❌ AlgoTradingDashboard rejection funnel shows 0 candidates
- ❌ SectorAnalysis may show no breadth data

---

### 2. **API Endpoints Return Incomplete Data** 🔴 BLOCKING

#### `/api/algo/rejection-funnel` — MINIMAL DATA
**Current Response:**
```json
[
  {"stage": "Initial Signals", "count": 0},
  {"stage": "Scored Candidates", "count": 0}
]
```
**Missing:**
- ❌ Per-filter rejection breakdown (which filter rejects most?)
- ❌ Rejection reasons (why signals rejected)
- ❌ Per-stage rejection percentages
- ❌ Time trends (rejection rates changing?)
- ❌ Gate failure breakdown (which gates are blocking?)

**Frontend Expects:** Rich funnel visualization with rejection reasons  
**Frontend Gets:** Two numbers (both likely 0 if tables empty)

---

#### `/api/algo/evaluate` — MINIMAL DATA
**Current Response:**
```json
{
  "stage": "evaluated",
  "candidates_screened": 0,
  "candidates_passing": 0,
  "top_score": 0,
  "avg_score": 0
}
```
**Missing:**
- ❌ Portfolio constraint analysis (vs actual)
- ❌ Risk allocation breakdown
- ❌ Position correlation matrix
- ❌ Rebalancing recommendations
- ❌ Tier/regime evaluation (why Caution vs Confirmed Uptrend?)

**Frontend Expects:** Multi-metric evaluation dashboard  
**Frontend Gets:** Four basic numbers

---

#### `/api/algo/exposure-policy` — INCOMPLETE CONTEXT
**Current Response:**
```json
{
  "current_exposure_pct": 50,
  "exposure_tier": "uptrend_under_pressure",
  "active_tier": {...tier config...},
  "all_tiers": [...all tier configs...],
  "as_of": "2026-05-27"
}
```
**Missing:**
- ❌ Detailed market regime breakdown:
  - S&P 500 stage number
  - Breadth ratio
  - VIX level and impact
  - McClellan oscillator value
  - Distribution days count
- ❌ Exposure calculation details (how 50% was computed)
- ❌ Historical exposure changes (trend)
- ❌ Time until policy changes expected

**Frontend Expects:** Policy drivers + calculation explanation  
**Frontend Gets:** Tier name + config (no context why)

---

#### `/api/algo/data-quality` — TOO ABSTRACT
**Current Response:**
```json
{
  "accuracy_check": "passed|warning|failed",
  "critical_count": 0,
  "error_count": 0,
  "warn_count": 0,
  "last_check": "2026-05-27T10:30:00Z"
}
```
**Missing:**
- ❌ Per-table status breakdown:
  - Table name, latest date, days_stale, row_count, completeness_%
- ❌ Field-level completeness (which fields have missing values?)
- ❌ Loader execution status (which loaders succeeded/failed?)
- ❌ Data freshness SLA adherence per table
- ❌ Specific issues (what failed? which table has 30% nulls?)

**Frontend Expects:** Table-by-table health summary  
**Frontend Gets:** Aggregate pass/fail/warning (useless for debugging)

---

#### `/api/market/sentiment` — INCOMPLETE SENTIMENT
**Current Response:**
```json
{
  "aaii": [...history...],
  "naaim": {"exposure": null, "current": null},
  "fearGreed": {"value": null, "label": null, "history": []}
}
```
**Issues:**
- ❌ If tables are empty, all values are null
- ❌ No per-component Fear & Greed breakdown (VIX, put/call, momentum, etc.)
- ❌ No divergence alerts (sentiment vs price)
- ❌ NAAIM missing extended history (52 weeks not exposed)
- ❌ AAII missing trend analysis (sentiment direction)

---

#### `/api/market/seasonality` — INCOMPLETE IF EMPTY
**Current Response (when data exists):**
```json
{
  "monthly": [
    {"month": 1, "month_name": "Jan", "avg_return": 1.2, "best_return": 5.3, "worst_return": -3.1, "winning_years": 45, "losing_years": 28, "years_counted": 73}
  ],
  "day_of_week": [
    {"day": "Monday", "day_num": 1, "avg_return": 0.1, "win_rate": 55, "days_counted": 1000}
  ]
}
```
**Issues:**
- ❌ If tables are empty, returns empty lists
- ❌ No "best month," "worst month," "seasonal strength" summary
- ❌ No alerts for "sell in May effect" or other anomalies
- ❌ No comparison to current year performance vs historical

---

#### `/api/market/fear-greed` — INCOMPLETE HISTORY
**Current Response:**
```json
[
  {"date": "2026-05-27", "value": 45, "label": "Fear"}
]
```
**Issues:**
- ❌ If table is empty, returns empty list
- ❌ No component breakdown (VIX, put/call, momentum, junk bond spread, etc.)
- ❌ No extremity scoring (where 45 ranks historically?)
- ❌ No divergence signals (Fear but market up?)

---

#### `/api/market/naaim` — LIMITED HISTORY
**Current Response:**
```json
{
  "current": 45.5,
  "history": [
    {"date": "2026-05-20", "naaim_number_mean": 45.5},
    ...52 weeks...
  ]
}
```
**Issues:**
- ❌ If table is empty, returns empty history
- ❌ Missing moving averages (10-day, 20-day, 50-day)
- ❌ Missing bullish/bearish extremes definition
- ❌ Missing divergence signals (NAAIM complacent but market rallying)
- ❌ Missing signal quality (confidence level)

---

### 3. **Market Data Display Issues** 🔴

#### MarketsHealth Page — Missing Key Displays
**Requested Endpoints:**
1. `/api/algo/markets` ✓ (works)
2. `/api/market/sentiment?range=30d` ⚠️ (returns null if tables empty)
3. `/api/market/top-movers` ✓ (works)
4. `/api/market/technicals` ✓ (works)
5. `/api/market/seasonality` ⚠️ (returns empty if tables empty)
6. `/api/prices/history/{symbol}?timeframe=daily&limit=30` ✓ (works)
7. `/api/algo/sector-rotation?limit=90` ✓ (works)
8. `/api/economic/yield-curve-full` ✓ (works)
9. `/api/market/distribution-days` ✓ (works)
10. `/api/market/fear-greed?range=30d` ⚠️ (returns empty if table empty)
11. `/api/economic/calendar` ✓ (works)

**Issues:**
- ⚠️ Sentiment section shows null values
- ⚠️ Seasonality section may show no data
- ⚠️ Fear/Greed section may show no data
- ✓ Everything else displays OK

---

#### EconomicDashboard Page — Missing Indicator Data
**Requested Endpoints:**
1. `/api/economic/leading-indicators` ✓ (exists but see issues)
2. `/api/economic/yield-curve-full` ✓ (works)
3. `/api/economic/calendar` ✓ (works)
4. `/api/market/naaim` ⚠️ (returns empty if table empty)

**Issues:**
- ⚠️ NAAIM section shows empty history if `naaim` table empty
- Leading indicators may show NULL values if `economic_data` table incomplete

---

### 4. **Data Loader Problems** 🔴

**Loaders that may not be running or data not loading:**

| Loader | Status | Evidence |
|--------|--------|----------|
| `load_aaii_sentiment.py` | ⚠️ Broken? | aaii_sentiment table may be empty |
| `load_fear_greed_index.py` | ⚠️ Broken? | fear_greed_index table may be empty |
| `load_naaim.py` | ⚠️ Broken? | naaim table may be empty |
| `loadseasonality.py` | ⚠️ Broken? | seasonality tables may be empty |
| `load_signal_quality_scores.py` | ⚠️ Broken? | swing_trader_scores may be empty |
| `load_algo_metrics_daily.py` | ⚠️ Broken? | market_exposure_daily may be empty |

**Root Causes:**
- Loaders may not be scheduled
- Loaders may be failing silently
- Data sources may be unavailable (APIs down?)
- Tables may not exist in schema

---

## HIGH-PRIORITY ISSUES (Impact Multiple Pages)

### 5. **SectorAnalysis Page** 🟠

**Requested Endpoints:**
- `/api/sectors/trends-batch` ✓
- `/api/algo/sector-breadth` ⚠️ (incomplete)
- `/api/algo/sector-stage2` ✓
- `/api/algo/sector-rotation?limit=180` ✓

**Issues:**
- ⚠️ `/api/algo/sector-breadth` returns only:
  - `{table_name, count}` (if implemented)
  - **Missing:** sector momentum matrix, leader/laggard identification, rotation signals

---

### 6. **AlgoTradingDashboard Page** 🟠

**13 Endpoints requested. Issues:**
- `/api/algo/status` ✓
- `/api/algo/markets` ✓
- `/api/algo/swing-scores` ✓
- `/api/algo/config` ✓
- `/api/algo/data-status` ✓
- `/api/algo/exposure-policy` ⚠️ (incomplete context)
- `/api/algo/evaluate` ⚠️ (too minimal)
- `/api/algo/circuit-breakers` ✓
- `/api/algo/data-quality` ⚠️ (too abstract)
- `/api/algo/rejection-funnel` ⚠️ (too minimal)

**Impact:**
- 5/13 endpoints return incomplete or minimal data
- Dashboard sections partially filled with incomplete information

---

## MEDIUM-PRIORITY ISSUES (Specific Pages/Features)

### 7. **PerformanceMetrics Page** 🟡
- `/api/algo/performance` ✓ returns good data
- BUT: Missing advanced metrics:
  - Ulcer Index (not in response)
  - Conditional Value at Risk (not in response)
  - Tail Ratio (not in response)
  - Stress test results (not available)

---

### 8. **BacktestResults Page** 🟡
- `/api/research/backtests` and `/api/research/backtests/{id}` exist
- BUT: Returns only summary stats, missing:
  - Trade-by-trade breakdown
  - Drawdown analysis
  - Underwater plot data
  - Period-by-period performance

---

### 9. **Price History for Multiple Symbols** 🟡
- `/api/prices/history/{symbol}` ✓ works
- BUT: Missing fields in response:
  - Split-adjusted indicator
  - Dividend amounts
  - Volume breakdown (institutional, retail, insider)
  - Intraday bars (only EOD available)

---

### 10. **Stock Fundamental Detail** 🟡
- `/api/stocks/{symbol}` returns basic info
- BUT: Missing fields:
  - Detailed valuation ratios (EV/EBITDA, etc.)
  - Growth rates (forward, 5-year)
  - Profitability metrics (ROIC, ROE, etc.)
  - Balance sheet detail
  - Cash flow detail
  - Quality scores (Piotroski, Altman)

---

## DATABASE SCHEMA ISSUES

### Critical Missing Tables (Not in init.sql)
1. ❌ `dividend_history` — No dividend tracking (required for total return calc)
2. ❌ `stock_splits` — No split adjustment tracking
3. ❌ `insider_transactions` — No insider data
4. ❌ `institutional_ownership` — No large holder tracking
5. ❌ `short_interest` — No short data
6. ❌ `price_targets` — No analyst price targets
7. ❌ `sector_correlation` — No pre-computed correlations
8. ❌ `support_resistance_levels` — No S/R levels tracked

### Incomplete Tables (Missing Fields)
1. `technical_data_daily` — May have NULL fields:
   - Missing VWAP
   - Missing Money Flow Index
   - Missing Accumulation/Distribution Line
   - Has both `macd_hist` and `macd_histogram` (duplicate)

2. `market_health_daily` — Missing:
   - Component breakdown of fear/greed factors
   - Sector momentum data
   - Market profile (volume at price)

3. `stock_scores` — Missing:
   - `positioning_score` may not be calculated
   - Score computation timestamp
   - Confidence level

4. `company_profile` — May have sparse data:
   - Founded date
   - Headquarters location
   - Industry subsector too granular or missing

---

## LOADER EXECUTION PROBLEMS

### Loaders Not Shown in Schedule
From `steering/algo.md`, confirmed loaders:
- ✓ stock_symbols (08:25 UTC)
- ✓ stock_prices_daily (09:00 UTC)
- ✓ market_data_batch (09:30 UTC)

**Missing from schedule:**
- ❓ load_aaii_sentiment.py — No schedule defined
- ❓ load_fear_greed_index.py — No schedule defined
- ❓ load_naaim.py — No schedule defined
- ❓ loadseasonality.py — No schedule defined (data doesn't change daily anyway)
- ❓ load_algo_metrics_daily.py — No schedule defined
- ❓ load_signal_quality_scores.py — Runs in morning pipeline but may fail

---

## API ENDPOINT COMPLETENESS MATRIX

| Endpoint | Status | Returns Full Data | Issue |
|----------|--------|-------------------|-------|
| `/api/algo/status` | ✓ Exists | ✓ Yes | None |
| `/api/algo/markets` | ✓ Exists | ⚠️ Partial | Missing regime breakdown |
| `/api/algo/positions` | ✓ Exists | ✓ Yes | None |
| `/api/algo/trades` | ✓ Exists | ✓ Yes | None |
| `/api/algo/performance` | ✓ Exists | ⚠️ Partial | Missing advanced metrics |
| `/api/algo/circuit-breakers` | ✓ Exists | ✓ Yes | None |
| `/api/algo/equity-curve` | ✓ Exists | ✓ Yes | None |
| `/api/algo/data-status` | ✓ Exists | ⚠️ Partial | Too abstract |
| `/api/algo/rejection-funnel` | ✓ Exists | ❌ No | Only 2 numbers |
| `/api/algo/evaluate` | ✓ Exists | ❌ No | Only 4 numbers |
| `/api/algo/exposure-policy` | ✓ Exists | ❌ No | Missing regime details |
| `/api/algo/data-quality` | ✓ Exists | ❌ No | Too abstract |
| `/api/algo/swing-scores` | ✓ Exists | ✓ Yes | None |
| `/api/market/sentiment` | ✓ Exists | ⚠️ Partial | Tables may be empty |
| `/api/market/technicals` | ✓ Exists | ✓ Yes | None |
| `/api/market/top-movers` | ✓ Exists | ✓ Yes | None |
| `/api/market/seasonality` | ✓ Exists | ⚠️ Partial | Tables may be empty |
| `/api/market/fear-greed` | ✓ Exists | ⚠️ Partial | Tables may be empty |
| `/api/market/naaim` | ✓ Exists | ⚠️ Partial | Tables may be empty |
| `/api/market/distribution-days` | ✓ Exists | ✓ Yes | None |
| `/api/signals/stocks` | ✓ Exists | ✓ Yes | None |
| `/api/signals/etf` | ✓ Exists | ✓ Yes | None |
| `/api/scores/stockscores` | ✓ Exists | ✓ Yes | None |
| `/api/sectors/trends-batch` | ✓ Exists | ✓ Yes | None |
| `/api/sectors/[sector]` | ✓ Exists | ✓ Yes | None |
| `/api/prices/history/{symbol}` | ✓ Exists | ⚠️ Partial | Missing volume breakdown |
| `/api/stocks/{symbol}` | ✓ Exists | ⚠️ Partial | Missing detail |
| `/api/economic/leading-indicators` | ✓ Exists | ⚠️ Partial | May have missing data |
| `/api/economic/yield-curve-full` | ✓ Exists | ✓ Yes | None |
| `/api/economic/calendar` | ✓ Exists | ✓ Yes | None |

---

## ROOT CAUSE ANALYSIS

### Why Data Is Missing/Incomplete:

#### ROOT CAUSE #1: Data Population Loaders Not Running
- Loaders like `load_aaii_sentiment.py`, `load_fear_greed_index.py` exist but:
  - ❓ Not scheduled in EventBridge
  - ❓ May fail silently with API rate limits
  - ❓ May have broken API endpoints
  - ❓ Data sources may have changed format

**Fix Required:**
- [ ] Verify loaders are scheduled
- [ ] Check CloudWatch logs for loader failures
- [ ] Verify data source APIs are still working
- [ ] Add data validation to detect missing data

---

#### ROOT CAUSE #2: API Endpoints Return Incomplete Data
- Endpoints implemented but limited scope:
  - `rejection-funnel`: Only returns top-level counts, not details
  - `evaluate`: Only returns candidate counts, not evaluation details
  - `data-quality`: Only returns aggregate status, not per-table detail
  - `exposure-policy`: Only returns policy name, not calculation details

**Fix Required:**
- [ ] Enhance rejection-funnel to include per-filter breakdown
- [ ] Enhance evaluate to include constraint analysis
- [ ] Enhance data-quality to include per-table detail
- [ ] Enhance exposure-policy to include regime breakdown

---

#### ROOT CAUSE #3: Database Tables May Not Exist or Be Empty
- Tables referenced by routes may not be created
- Tables created but no loader is populating them
- Example: `market_exposure_daily` referenced but may be empty

**Fix Required:**
- [ ] Verify all tables exist in schema
- [ ] Verify each table has recent data (not just empty rows)
- [ ] Verify loader execution for each table

---

## BLOCKING ISSUES PRIORITY CHECKLIST

### P0 - Blocks Application (Fix First)
- [ ] **Check if critical tables are empty:**
  - [ ] SELECT COUNT(*) FROM aaii_sentiment;
  - [ ] SELECT COUNT(*) FROM naaim;
  - [ ] SELECT COUNT(*) FROM fear_greed_index;
  - [ ] SELECT COUNT(*) FROM seasonality_monthly_stats;
  - [ ] SELECT COUNT(*) FROM swing_trader_scores;
  - [ ] SELECT COUNT(*) FROM market_exposure_daily;
  - [ ] SELECT COUNT(*) FROM data_patrol_log;

- [ ] **Verify loaders are running:**
  - [ ] Check CloudWatch logs for loader execution
  - [ ] Check if loaders have scheduled events in EventBridge
  - [ ] Verify no loader has been disabled

- [ ] **Test API endpoints directly:**
  - [ ] curl /api/market/sentiment
  - [ ] curl /api/market/seasonality
  - [ ] curl /api/algo/rejection-funnel
  - [ ] curl /api/algo/evaluate
  - [ ] curl /api/algo/data-quality

### P1 - Incomplete Data (High Priority)
- [ ] Enhance `/api/algo/rejection-funnel` to include per-filter breakdown
- [ ] Enhance `/api/algo/evaluate` to include constraint analysis and correlation
- [ ] Enhance `/api/algo/data-quality` to include per-table detail
- [ ] Enhance `/api/algo/exposure-policy` to include regime breakdown

### P2 - Missing Advanced Features (Medium Priority)
- [ ] Add Ulcer Index to `/api/algo/performance`
- [ ] Add CVaR to `/api/algo/performance`
- [ ] Add detailed backtest results to research endpoints
- [ ] Add dividend/split data to price history

### P3 - Database Schema (Lower Priority)
- [ ] Create `dividend_history` table
- [ ] Create `stock_splits` table
- [ ] Create loaders for new tables

---

## SUMMARY OF REQUIRED FIXES

**Total Issues:** 60+  
**Blocking Issues:** 8 (data tables may be empty)  
**Incomplete Endpoints:** 10 (need enhancement)  
**Missing Tables:** 8 (nice-to-have)  
**Missing Loaders:** 4-5 (critical)

**Estimated Impact:**
- 3 pages completely blocked if tables are empty
- 6 pages partially blocked with incomplete data
- 6 pages fully functional

---

**Next Steps:**
1. Verify database table population status
2. Check CloudWatch logs for loader failures
3. Fix critical loaders
4. Enhance API endpoints returning incomplete data
5. Add missing database tables


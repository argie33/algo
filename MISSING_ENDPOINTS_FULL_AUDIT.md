# Missing Endpoints Comprehensive Audit
**Date:** 2026-05-09  
**Status:** 50+ endpoints needed but not yet implemented

---

## SUMMARY

| Category | Implemented | Missing | Total |
|----------|-------------|---------|-------|
| /api/algo/* | 11 | 5 | 16 |
| /api/signals/* | 2 | 0 | 2 |
| /api/prices/* | 1 | 0 | 1 |
| /api/stocks/* | 1 | 0 | 1 |
| /api/scores/* | 0 | 2 | 2 |
| /api/portfolio/* | 2 | 1 | 3 |
| /api/sectors/* | 1 | 2 | 3 |
| /api/market/* | 3 | 5 | 8 |
| /api/economic/* | 1 | 3 | 4 |
| /api/sentiment/* | 1 | 2 | 3 |
| /api/commodities/* | 0 | 4 | 4 |
| /api/earnings/* | 0 | 2 | 2 |
| /api/financial/* | 0 | 4 | 4 |
| /api/research/* | 0 | 1 | 1 |
| /api/optimization/* | 0 | 1 | 1 |
| /api/audit/* | 0 | 1 | 1 |
| /api/trades/* | 0 | 1 | 1 |
| **TOTAL** | **26** | **34** | **60** |

---

## MISSING ENDPOINTS BY PRIORITY

### 🔴 CRITICAL (Pages completely broken, users expecting data)

#### `/api/algo/*` - Algo Monitoring
- ❌ `/api/algo/config` — Algo configuration parameters (used by AlgoTradingDashboard)
- ❌ `/api/algo/data-quality` — Data quality metrics (used by MarketsHealth)
- ❌ `/api/algo/evaluate` — Real-time evaluation status (used by AlgoTradingDashboard)
- ❌ `/api/algo/exposure-policy` — Position sizing rules (used by PortfolioDashboard)
- ❌ `/api/algo/sector-stage2` — Stage 2 candidates (used by AlgoTradingDashboard)

#### `/api/scores/*` - Stock Scoring System
- ❌ `/api/scores/stockscores?limit=5000&offset=0&sortBy=composite_score&sp500Only=true`
  - Used by: ScoresDashboard, MetricsDashboard
  - Expected: 5000 stocks with composite_score, momentum_score, quality_score, etc.
  - Status: NO IMPLEMENTATION AT ALL

- ❌ `/api/scores/stockscores?limit=200&sortBy=composite_score&sortOrder=desc`
  - Similar to above but smaller dataset

#### `/api/optimization/*` - Portfolio Optimization
- ❌ `/api/optimization/analysis` — Mean-variance optimization results
  - Used by: PortfolioOptimizerNew
  - Expected: Portfolio weights, efficient frontier, risk metrics

#### `/api/audit/*` - Audit Trail
- ❌ `/api/audit/trail` — Action audit log
  - Used by: AuditViewer
  - Expected: All user/system actions with timestamps

#### `/api/trades/*` - Trade Management
- ❌ `/api/trades/summary` — Trade statistics (used by TradeTracker)

---

### 🟠 HIGH (Pages showing empty, critical features broken)

#### `/api/market/*` - Market Data  
- ❌ `/api/market/distribution-days` — Breadth distribution (used by MarketOverview)
- ❌ `/api/market/fear-greed?range=30d` — Fear/greed history (used by MarketsHealth)
- ❌ `/api/market/seasonality` — Seasonal patterns (used by MarketOverview)
- ❌ `/api/market/technicals` — Market technicals (used by MarketOverview)
- ❌ `/api/market/top-movers` — Top gainers/losers (used by MarketOverview)

#### `/api/sentiment/*` - Market Sentiment
- ❌ `/api/sentiment/data?limit=5000&page=1` — Sentiment time series data (used by Sentiment)
- ❌ `/api/sentiment/divergence` — Divergence metrics (used by Sentiment)

#### `/api/economic/*` - Economic Data
- ❌ `/api/economic/leading-indicators` — Leading economic indicators (used by EconomicDashboard)
- ❌ `/api/economic/yield-curve-full` — Full yield curve data (used by EconomicDashboard)
- ❌ `/api/economic/calendar` — Economic calendar events (used by EconomicDashboard)

#### `/api/earnings/*` - Earnings Data
- ❌ `/api/earnings/sp500-trend` — S&P 500 earnings trend (used by EarningsCalendar)
- ❌ `/api/earnings/sector-trend` — Sector earnings trend (used by EarningsCalendar)

---

### 🟡 MEDIUM (Important pages degraded, non-critical features)

#### `/api/sectors/*` - Sector Analysis
- ❌ `/api/sectors/{name}/trend?days=90` — Sector performance trend (used by SectorAnalysis)

#### `/api/commodities/*` - Commodity Analysis
- ❌ `/api/commodities/categories` — Commodity categories (used by CommoditiesAnalysis)
- ❌ `/api/commodities/correlations` — Correlations with stocks (used by CommoditiesAnalysis)
- ❌ `/api/commodities/events` — News/event data (used by CommoditiesAnalysis)
- ❌ `/api/commodities/macro` — Macro data (used by CommoditiesAnalysis)

#### `/api/financial/*` - Financial Statements
- ❌ `/api/financial/companies` — Company list (used by FinancialData)
- ❌ `/api/financial/balance-sheet/{symbol}` — Balance sheet (used by FinancialData)
- ❌ `/api/financial/income-statement/{symbol}` — Income statement (used by FinancialData)
- ❌ `/api/financial/cash-flow/{symbol}` — Cash flow statement (used by FinancialData)

#### `/api/research/*` - Backtest Results
- ❌ `/api/research/backtests` — Backtest run list (used by BacktestResults)

---

## PAGES CURRENTLY BROKEN BY MISSING ENDPOINTS

| Page | Missing Endpoint | Impact |
|------|------------------|--------|
| **AlgoTradingDashboard** | `/api/algo/config`, `/api/algo/evaluate`, `/api/algo/sector-stage2` | Can't show algo eval state or config |
| **AuditViewer** | `/api/audit/trail` | No audit log, page empty |
| **BacktestResults** | `/api/research/backtests` | No backtest data |
| **CommoditiesAnalysis** | `/api/commodities/*` (4 endpoints) | All commodity sections blank |
| **EarningsCalendar** | `/api/earnings/*` (2 endpoints) | No earnings data |
| **EconomicDashboard** | `/api/economic/*` (3 endpoints) | All indicators missing |
| **FinancialData** | `/api/financial/*` (4 endpoints) | Can't view financials |
| **MarketsHealth** | `/api/market/*` (5 endpoints) | Missing technicals, movers, distribution |
| **MetricsDashboard** | `/api/scores/stockscores` | No stock scores |
| **NotificationCenter** | ✅ WORKS (we have `/api/algo/notifications`) | Data should display |
| **PerformanceMetrics** | ✅ WORKS (we have `/api/algo/performance`) | Data should display |
| **PortfolioDashboard** | `/api/algo/exposure-policy` | Missing position sizing context |
| **PortfolioOptimizerNew** | `/api/optimization/analysis` | Can't show optimization results |
| **ScoresDashboard** | `/api/scores/stockscores` (5000 limit version) | No stock data |
| **SectorAnalysis** | `/api/sectors/{name}/trend` | Missing trend data |
| **Sentiment** | `/api/sentiment/data`, `/api/sentiment/divergence` | No sentiment data or divergence |
| **ServiceHealth** | ✅ WORKS (we have `/api/algo/data-status`) | Should work |
| **TradeTracker** | `/api/trades/summary` | Missing trade stats |

---

## IMPLEMENTATION PLAN

### Phase 1: Critical Scoring System (2 endpoints)
**Impact:** Unblocks ScoresDashboard, MetricsDashboard, stock selection features

1. **`/api/scores/stockscores`**
   ```sql
   SELECT symbol, company_name, sector,
       composite_score, momentum_score, quality_score, value_score,
       growth_score, positioning_score, stability_score,
       price, trailing_pe, pct_change_1m
   FROM stock_scores
   WHERE composite_score > 0
   ORDER BY composite_score DESC
   LIMIT %s OFFSET %s
   ```

2. **Query variations by filter:**
   - `&sp500Only=true` — Filter to S&P 500 only
   - `&sortBy=momentum_score` — Allow sort by any score component
   - Support pagination via offset

### Phase 2: Market & Economic Data (8 endpoints)
**Impact:** Unblocks MarketOverview, EconomicDashboard, MarketsHealth

1. `/api/market/technicals` — Market breadth, McClellan, advance/decline
2. `/api/market/top-movers` — Top gainers/losers
3. `/api/market/distribution-days` — Market distribution patterns
4. `/api/market/seasonality` — Seasonal strength by day/month
5. `/api/economic/leading-indicators` — Leading economic indicators
6. `/api/economic/yield-curve-full` — Full yield curve structure
7. `/api/economic/calendar` — Upcoming economic events
8. `/api/market/fear-greed?range=30d` — Fear/Greed index history

### Phase 3: Sentiment & Commodities (6 endpoints)
**Impact:** Unblocks Sentiment, CommoditiesAnalysis pages

1. `/api/sentiment/data` — Time series sentiment data
2. `/api/sentiment/divergence` — Divergence metrics
3. `/api/commodities/categories` — Commodity list by category
4. `/api/commodities/correlations` — Correlation matrix
5. `/api/commodities/events` — News/macro events
6. `/api/commodities/macro` — Macro relationships

### Phase 4: Specialized Features (7 endpoints)
**Impact:** Unblocks optimization, earnings, financials, backtest pages

1. `/api/optimization/analysis` — Portfolio optimization
2. `/api/earnings/calendar` — Earnings dates
3. `/api/earnings/sector-trend` — Earnings growth by sector
4. `/api/financial/balance-sheet/{symbol}` — Balance sheet data
5. `/api/financial/income-statement/{symbol}` — Income statement
6. `/api/financial/cash-flow/{symbol}` — Cash flow statement
7. `/api/research/backtests` — Backtest results

### Phase 5: Algo & Trading (6 endpoints)
**Impact:** Unblocks AlgoTradingDashboard, portfolio features

1. `/api/algo/config` — Algo configuration
2. `/api/algo/evaluate` — Real-time evaluation
3. `/api/algo/data-quality` — Data quality metrics
4. `/api/algo/exposure-policy` — Position sizing rules
5. `/api/algo/sector-stage2` — Stage 2 candidates
6. `/api/trades/summary` — Trade statistics

---

## DATA SOURCES NEEDED (DATABASE)

To implement these endpoints, we need tables:
- ✅ `buy_sell_daily` — Trading signals
- ✅ `swing_scores_daily` — Swing candidates
- ✅ `price_daily` — Price history
- ✅ `algo_trades` — Trade history
- ✅ `algo_positions` — Open positions
- ❓ `stock_scores` — Stock scoring data (verify exists, populated)
- ❓ `stock_fundamentals` — Valuation metrics
- ❓ `company_profile` — Company metadata
- ❓ Economic tables (yield_curve, economic_calendar, etc.)
- ❓ `sentiment_data` — Market sentiment time series
- ❓ `commodities_*` — Commodity data
- ❓ `backtest_results` — Backtest data

---

## QUICK WINS (Highest ROI, Lowest Effort)

1. **Stock Scores** (2 endpoints) — Use existing stock_fundamentals table, minimal JOIN logic
2. **Market Technicals** (1 endpoint) — Calculate from price_daily, simple aggregation
3. **Sentiment History** (1 endpoint) — Query existing sentiment table
4. **Economic Calendar** (1 endpoint) — Return static/imported data

**Estimated effort:** 2-4 hours for Phase 1-2

---

## TESTING CHECKLIST

For EACH endpoint implemented:
- [ ] Returns non-empty data
- [ ] All expected fields present
- [ ] Data is reasonable (no NaN, null handling correct)
- [ ] API Gateway test passes
- [ ] Frontend page displays without errors
- [ ] Filters/sorting work if applicable
- [ ] Performance acceptable (< 2s response time)


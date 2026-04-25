# End-to-End Data Pipeline Audit
## Complete Loader → Table → API → Frontend Mapping

**Audit Date**: 2026-04-25  
**Scope**: All 63+ loaders, 40+ database tables, 28 API endpoints, frontend consumption  
**Status**: COMPREHENSIVE REVIEW - Identifying all mismatches and architectural issues

---

## CRITICAL FINDINGS

### 🔴 BLOCKER ISSUES (Fix First)

1. **Earnings Estimates Schema Mismatch** ❌ FIXED but Still Broken
   - **Issue**: All earnings_estimates columns are NULL (0% populated)
   - **Reason**: Disabled loader (was inserting wrong columns), no alternative source
   - **Impact**: UI shows empty earnings forecast pages
   - **Solution**: Option A) Use earnings_history instead, Option B) Alternative API (FactSet, Seeking Alpha)

2. **Options Chains Data Missing** ❌ (1/515 stocks = 0.2%)
   - **Issue**: Only 1 stock has options data despite table existing
   - **Reason**: yfinance API returns incomplete data or loader exits early
   - **Impact**: Options strategies unavailable
   - **Solution**: Debug loader, investigate yfinance output, consider alternative source

3. **ETF Price Tables** ❌ (Negative row counts in queries)
   - **Issue**: ETF daily/weekly/monthly price loaders returning errors
   - **Reason**: Unknown - needs investigation
   - **Impact**: ETF analysis pages broken
   - **Solution**: Run loaders manually, check error logs

### 🟡 PARTIAL COVERAGE ISSUES (Acceptable but Could Improve)

4. **Analyst Sentiment** 🟡 (359/515 = 70%)
   - **Issue**: 30% of stocks missing analyst data
   - **Reason**: yfinance API has incomplete coverage
   - **Impact**: Missing sentiment for ~156 stocks
   - **Mitigating Factor**: Still has 70% coverage, acceptable for now

5. **Analyst Upgrades/Downgrades** 🟡 (193/515 = 37%)
   - **Issue**: Limited historical data
   - **Reason**: yfinance API doesn't provide comprehensive historical upgrades
   - **Impact**: Analyst events missing for ~322 stocks
   - **Alternative**: Use alternative data source (Zacks, Morningstar)

6. **Institutional Positioning** 🟡 (209/515 = 41%)
   - **Issue**: Many stocks lack institutional holder data
   - **Reason**: yfinance API incomplete for many stocks
   - **Impact**: Positioning analysis incomplete
   - **Alternative**: Could supplement from 13F SEC filings

---

## LOADER → TABLE MAPPING

### ✅ WORKING LOADERS (100% Coverage)

| # | Loader | Target Table | Fields | Coverage | Status |
|---|--------|--------------|--------|----------|--------|
| 1 | loadstocksymbols.py | stock_symbols | symbol, cik, exchange, etc | 4,969 stocks | ✅ |
| 2 | loadpricedaily.py | price_daily | open, high, low, close, volume | 515 * 250 days | ✅ |
| 3 | loadpriceweekly.py | price_weekly | OHLCV weekly | 515 * 50 weeks | ✅ |
| 4 | loadpricemonthly.py | price_monthly | OHLCV monthly | 515 * 36 months | ✅ |
| 5 | loadlatestpricedaily.py | price_daily | Current daily price | 515 | ✅ |
| 6 | loadlatestpriceweekly.py | price_weekly | Current week | 515 | ✅ |
| 7 | loadlatestpricemonthly.py | price_monthly | Current month | 515 | ✅ |
| 8 | loaddailycompanydata.py | company_profile | Name, sector, industry, website | 515 | ✅ |
| 9 | loaddailycompanydata.py | key_metrics | PE, div yield, beta, short interest | 515 | ✅ |
| 10 | loadbuyselldaily.py | buy_sell_daily | Signal (buy/sell/hold) | 515 | ✅ |
| 11 | loadbuysellweekly.py | buy_sell_weekly | Weekly signals | 515 | ✅ |
| 12 | loadbuysellmonthly.py | buy_sell_monthly | Monthly signals | 515 | ✅ |
| 13 | loadbuysell_etf_daily.py | buy_sell_etf_daily | ETF signals | All ETFs | ✅ |
| 14 | loadbuysell_etf_weekly.py | buy_sell_etf_weekly | ETF weekly signals | All ETFs | ✅ |
| 15 | loadbuysell_etf_monthly.py | buy_sell_etf_monthly | ETF monthly signals | All ETFs | ✅ |
| 16 | loadstockscores.py | stock_scores | Composite score (0-100) | 4,969 | ✅ |
| 17 | loadstockscores.py | quality_metrics | ROE, margins, growth stability | 4,969 | ✅ |
| 18 | loadstockscores.py | growth_metrics | Revenue/EPS growth rates | 4,969 | ✅ |
| 19 | loadstockscores.py | momentum_metrics | Price momentum, trend | 4,969 | ✅ |
| 20 | loadstockscores.py | value_metrics | PE, PB, dividend metrics | 4,969 | ✅ |
| 21 | loadstockscores.py | stability_metrics | Volatility, beta, drawdown | 4,969 | ✅ |
| 22 | loaddailycompanydata.py | earnings_history | Actual EPS, surprises | 515 | ✅ |
| 23 | loadanalystsentiment.py | analyst_sentiment_analysis | Bullish/bearish counts, ratings | 359/515 | 🟡 70% |
| 24 | loadcalendar.py | calendar_events | Earnings dates, dividends, splits | 515 | ✅ |
| 25 | loadmarket.py | market_data | Advance/decline, breadth | Daily | ✅ |
| 26 | loadaaiidata.py | aaii_sentiment | AAII sentiment index | Weekly | ✅ |
| 27 | loadfeargreed.py | fear_greed_index | Fear & Greed index | Daily | ✅ |
| 28 | loadnaaim.py | naaim_exposure | NAAIM exposure index | Weekly | ✅ |
| 29 | loadsectors.py | sectors | Sector rankings, performance | 11 sectors | ✅ |
| 30 | loadindustryranking.py | industry_ranking | Industry rankings | 150+ industries | ✅ |
| 31 | loadecondata.py | economic_data | FRED indicators | 100+ series | ✅ |
| 32 | loadecondata.py | economic_calendar | Fed events | Calendar | ✅ |
| 33 | loadcommodities.py | commodity_prices | Oil, gold, copper, etc | Current | ✅ |
| 34 | loadseasonality.py | seasonality_data | Seasonal patterns | All stocks | ✅ |
| 35 | loadannualincomestatement.py | annual_income_statement | Revenue, net income, EPS | 515 | ✅ |
| 36 | loadannualbalancesheet.py | annual_balance_sheet | Assets, liabilities, equity | 515 | ✅ |
| 37 | loadannualcashflow.py | annual_cash_flow | Operating, investing, financing CF | 515 | ✅ |
| 38 | loadquarterlyincomestatement.py | quarterly_income_statement | Quarterly P&L | 515 | ✅ |
| 39 | loadquarterlybalancesheet.py | quarterly_balance_sheet | Quarterly BS | 515 | ✅ |
| 40 | loadquarterlycashflow.py | quarterly_cash_flow | Quarterly CF | 515 | ✅ |
| 41 | loadttmincomestatement.py | ttm_income_statement | TTM P&L | 515 | ✅ |
| 42 | loadttmcashflow.py | ttm_cash_flow | TTM CF | 515 | ✅ |
| 43 | loaddailycompanydata.py | institutional_positioning | Institution holders, % | 209/515 | 🟡 41% |
| 44 | loaddailycompanydata.py | insider_transactions | Insider buy/sell | 515 | ✅ |
| 45 | loaddailycompanydata.py | positioning_metrics | Inst %, insider %, short % | 515 | ✅ |
| 46 | loaddailycompanydata.py | beta_yfinance | Beta from yfinance | 515 | ✅ |

### 🟡 PARTIAL COVERAGE LOADERS

| # | Loader | Target Table | Coverage | Reason |
|---|--------|--------------|----------|--------|
| 47 | loadanalystupgradedowngrade.py | analyst_upgrade_downgrade | 193/515 (37%) | Limited yfinance data |
| 48 | loadearningsrevisions.py | earnings_estimate_revisions | Unknown | Limited source data |

### ❌ BROKEN LOADERS (0% Coverage)

| # | Loader | Target Table | Coverage | Reason |
|---|--------|--------------|----------|--------|
| 49 | loadoptionschains.py | options_chains | 1/515 (0.2%) | yfinance API incomplete |
| 50 | (None) | earnings_estimates | 0/515 (0%) | Loader disabled due to mismatch |
| 51 | loadetfpricedaily.py | etf_price_daily | ERROR | Unknown issue |
| 52 | loadetfpriceweekly.py | etf_price_weekly | ERROR | Unknown issue |
| 53 | loadetfpricemonthly.py | etf_price_monthly | ERROR | Unknown issue |

---

## TABLE → API ENDPOINT MAPPING

### ✅ PROPERLY MAPPED (Table created, API endpoint exists)

| Table | Loader | API Endpoint | Method | Status |
|-------|--------|--------------|--------|--------|
| stock_symbols | loadstocksymbols.py | /api/stocks | GET | ✅ |
| price_daily | loadpricedaily.py | /api/price/history | GET | ✅ |
| price_weekly | loadpriceweekly.py | /api/price/history | GET | ✅ |
| price_monthly | loadpricemonthly.py | /api/price/history | GET | ✅ |
| company_profile | loaddailycompanydata.py | /api/stocks/:symbol | GET | ✅ |
| key_metrics | loaddailycompanydata.py | /api/financials/:symbol/key-metrics | GET | ✅ |
| analyst_sentiment_analysis | loadanalystsentiment.py | /api/sentiment/data | GET | ✅ |
| analyst_upgrade_downgrade | loadanalystupgradedowngrade.py | /api/analysts/upgrades | GET | ✅ |
| buy_sell_daily | loadbuyselldaily.py | /api/signals/daily | GET | ✅ |
| buy_sell_weekly | loadbuysellweekly.py | /api/signals/weekly | GET | ✅ |
| buy_sell_monthly | loadbuysellmonthly.py | /api/signals/monthly | GET | ✅ |
| stock_scores | loadstockscores.py | /api/scores | GET | ✅ |
| quality_metrics | loadstockscores.py | /api/metrics/quality | GET | ✅ |
| growth_metrics | loadstockscores.py | /api/metrics/growth | GET | ✅ |
| momentum_metrics | loadstockscores.py | /api/metrics/momentum | GET | ✅ |
| value_metrics | loadstockscores.py | /api/metrics/value | GET | ✅ |
| stability_metrics | loadstockscores.py | /api/metrics/stability | GET | ✅ |
| annual_income_statement | loadannualincomestatement.py | /api/financials/:symbol/income-statement | GET | ✅ |
| annual_balance_sheet | loadannualbalancesheet.py | /api/financials/:symbol/balance-sheet | GET | ✅ |
| annual_cash_flow | loadannualcashflow.py | /api/financials/:symbol/cash-flow | GET | ✅ |
| quarterly_income_statement | loadquarterlyincomestatement.py | /api/financials/:symbol/income-statement | GET | ✅ |
| quarterly_balance_sheet | loadquarterlybalancesheet.py | /api/financials/:symbol/balance-sheet | GET | ✅ |
| quarterly_cash_flow | loadquarterlycashflow.py | /api/financials/:symbol/cash-flow | GET | ✅ |
| calendar_events | loadcalendar.py | /api/calendar | GET | ✅ |
| market_data | loadmarket.py | /api/market/overview | GET | ✅ |
| aaii_sentiment | loadaaiidata.py | /api/sentiment/aaii | GET | ✅ |
| fear_greed_index | loadfeargreed.py | /api/sentiment/fear-greed | GET | ✅ |
| sectors | loadsectors.py | /api/sectors | GET | ✅ |
| economic_data | loadecondata.py | /api/economic | GET | ✅ |
| commodity_prices | loadcommodities.py | /api/commodities | GET | ✅ |

### 🟡 PARTIAL MAPPING (Loader partial, endpoint exists)

| Table | Loader | API Endpoint | Coverage | Status |
|-------|--------|--------------|----------|--------|
| analyst_sentiment_analysis | loadanalystsentiment.py | /api/sentiment/data | 359/515 (70%) | 🟡 |
| analyst_upgrade_downgrade | loadanalystupgradedowngrade.py | /api/analysts/upgrades | 193/515 (37%) | 🟡 |
| institutional_positioning | loaddailycompanydata.py | /api/positioning | 209/515 (41%) | 🟡 |

### ❌ BROKEN MAPPING (Table exists, no data)

| Table | Loader | API Endpoint | Status | Issue |
|-------|--------|--------------|--------|-------|
| earnings_estimates | (None) | /api/earnings/estimates | ❌ | 0% populated - loader disabled |
| options_chains | loadoptionschains.py | /api/options | ❌ | 0.2% populated - yfinance issue |
| etf_price_daily | loadetfpricedaily.py | /api/etf/price | ❌ | Query errors |
| etf_price_weekly | loadetfpriceweekly.py | /api/etf/price | ❌ | Query errors |
| etf_price_monthly | loadetfpricemonthly.py | /api/etf/price | ❌ | Query errors |

### ❓ ORPHANED ENDPOINTS (API endpoint exists but unclear if used)

| Endpoint | Tables Queried | Frontend Usage | Status |
|----------|----------------|----------------|--------|
| /api/signals | buy_sell_daily/weekly/monthly | YES | ✅ |
| /api/optimization | portfolio optimization tables | Unclear | ❓ |
| /api/strategies | strategy tables | Unclear | ❓ |
| /api/technicals | technical_data_daily | YES | ✅ |
| /api/trades (manual) | manual_trades table | YES | ✅ |
| /api/world-etfs | world_etf_* tables | Unclear | ❓ |

---

## API ENDPOINT → FRONTEND CONSUMPTION MAPPING

### ✅ PROPERLY CONSUMED (Endpoint called, response parsed correctly)

| Endpoint | Frontend Component | Method | Status |
|----------|-------------------|--------|--------|
| /api/stocks | StockList.jsx | GET list with pagination | ✅ |
| /api/stocks/:symbol | StockDetails.jsx | GET single stock | ✅ |
| /api/price/history/:symbol | FinancialData.jsx / PriceChart.jsx | GET historical prices | ✅ |
| /api/financials/:symbol/income-statement | FinancialData.jsx | GET P&L | ✅ |
| /api/financials/:symbol/balance-sheet | FinancialData.jsx | GET balance sheet | ✅ |
| /api/financials/:symbol/cash-flow | FinancialData.jsx | GET cash flow | ✅ |
| /api/sentiment/data | SentimentAnalysis.jsx | GET analyst sentiment | ✅ |
| /api/analysts/upgrades | AnalystAnalysis.jsx | GET upgrades/downgrades | ✅ |
| /api/signals/daily | SignalsTable.jsx | GET trading signals | ✅ |
| /api/scores | ScoresTable.jsx | GET stock scores | ✅ |
| /api/market/overview | MarketOverview.jsx | GET market data | ✅ |
| /api/sectors | SectorAnalysis.jsx | GET sector data | ✅ |

### 🟡 PARTIALLY WORKING (Response format issues or incomplete data)

| Endpoint | Issue | Impact | Fix Needed |
|----------|-------|--------|-----------|
| /api/sentiment/data | 70% data coverage | Missing sentiment for 30% of stocks | Use alternative source |
| /api/analysts/upgrades | 37% data coverage | Limited analyst events | Use alternative source |
| /api/options | 0.2% data coverage | Options strategies unavailable | Debug yfinance API |

### ❌ BROKEN (No data to return)

| Endpoint | Issue | Impact | Fix Needed |
|----------|-------|--------|-----------|
| /api/earnings/estimates | 0% populated | Forecast pages show NULL | Alternative data source |
| /api/etf/price | Query errors | ETF pages broken | Debug table/queries |

---

## FRONTEND API CLIENT ANALYSIS

**File**: `webapp/frontend-admin/src/services/api.js`

### ✅ Good: Response Format Handling
```javascript
// Properly handles standard response wrapper
const response = await api.get('/api/stocks');
// response.data contains the actual data
// response.success indicates success/failure
// response.timestamp shows when response was generated
```

### ✅ Good: Error Handling
```javascript
// Proper error interceptor with retry logic
api.interceptors.response.use(
  (response) => { /* handle success */ },
  (error) => { /* handle error */ }
);
```

### ✅ Good: Dynamic API URL Configuration
```javascript
const apiUrl = window.__CONFIG__.API_URL || import.meta.env.VITE_API_URL || "/";
// Works with runtime config, env vars, or fallback
```

### 🟡 Could Improve: Response Field Inconsistency
Some endpoints return:
- `items` (paginated) - sentiment.js, analysts.js
- `data` (single/list) - other endpoints
- `financialData` (financials.js)

**Frontend should normalize these** to a consistent field name.

### 🟡 Could Improve: Pagination Field Names
Endpoints use:
- `page`, `limit`, `total`, `totalPages`, `hasNext`, `hasPrev` (newer format)
- Some older endpoints might use different field names

**Solution**: Standardize all endpoints to use same pagination format.

---

## IDENTIFIED ARCHITECTURE ISSUES

### Issue #1: Earnings Data Split Across Two Tables

**Problem**: 
- `earnings_estimates` - Should have forward estimates (eps_estimate, revenue_estimate) - EMPTY
- `earnings_history` - Has actual reported earnings - POPULATED

**Why it's confusing**:
- Frontend doesn't know which table to query for earnings forecasts
- API might not have endpoint for earnings_estimates
- User thinks all earnings data is missing

**Solution**: 
- Option A: Deprecate earnings_estimates, use earnings_history for everything
- Option B: Populate earnings_estimates from alternative source
- Option C: Create hybrid endpoint that returns both actual and estimates

### Issue #2: Positioning Data in Three Tables

**Problem**:
- `institutional_positioning` - Individual institution records (41% coverage)
- `positioning_metrics` - Aggregate positioning metrics (institutional %, insider %, short %)
- `key_metrics` - Duplicate positioning data (from yfinance)

**Why it's confusing**:
- Three overlapping sources of positioning data
- Not clear which one is authoritative
- Queries may return stale or conflicting data

**Solution**:
- Clarify which table is primary source
- Remove duplicates
- Create single endpoint that returns all positioning data in consistent format

### Issue #3: Financial Statement Data in Two Formats

**Problem**:
- `annual_*` / `quarterly_*` tables - Direct from yfinance
- `ttm_*` tables - Trailing 12-month aggregates

**Why it's confusing**:
- Frontend might not know to query ttm_* for latest data
- Could be out of sync with annual/quarterly

**Solution**:
- Document which to use when
- Ensure TTM is always up-to-date and synced with quarterly

### Issue #4: ETF Data Structure Unclear

**Problem**:
- ETF loaders exist but have errors
- No clear ETF endpoints in API
- No documentation on ETF data structure

**Why it matters**:
- ETF analysis partially broken
- Users don't know what's supported

**Solution**:
- Document ETF data model
- Fix or disable broken loaders
- Create clear ETF endpoints

---

## END-TO-END CHECKLIST

### Loader → Table
- [x] All loaders have target tables documented
- [x] Table schemas exist for all loaders
- [ ] All loaders actually create data (some fail silently)

### Table → API Endpoint
- [x] All tables have corresponding API endpoints
- [ ] All endpoints query correct tables
- [ ] All endpoints return data in consistent format

### API → Frontend
- [x] Frontend API client handles responses
- [ ] Frontend correctly parses all response formats
- [ ] Frontend handles pagination correctly
- [ ] Frontend handles missing data gracefully

---

## RECOMMENDATIONS

### Critical (Do First)
1. Fix earnings estimates - choose data source or disable in UI
2. Fix options chains - debug yfinance API or disable
3. Fix ETF data - debug or disable broken loaders

### High Priority (Architecture)
1. Standardize API response format (items vs data, pagination fields)
2. Consolidate positioning data to single source
3. Document which financial statement tables to use when
4. Clarify ETF data model

### Medium Priority (Coverage)
1. Supplement analyst sentiment with alternative source (→ 100%)
2. Supplement analyst upgrades with alternative source (→ 100%)
3. Supplement institutional positioning from SEC filings (→ 100%)

### Nice to Have
1. Add real-time streaming endpoints for price updates
2. Add historical data API for backtesting
3. Add portfolio optimization endpoints

---

## NEXT STEPS

1. **Update Task #1**: Mark as ready for fixes
2. **Create Detailed Fix Plan**: Address critical issues first
3. **Update API Response Format**: Ensure consistency
4. **Test End-to-End**: Run sample queries through entire pipeline
5. **Update Frontend**: Handle all edge cases and missing data


# ENDPOINT ARCHITECTURE AUDIT - What Needs to be Right

## ENDPOINT RESPONSE SCHEMAS - What Frontend Actually Needs

### Market Endpoints - VERIFY DATA COMPLETENESS

#### `/api/market/overview` 
**Frontend Needs:** Breadth data, indices, sentiment, movers all in ONE call
**Current:** Returning basic data
**CHECK:** Are we returning:
- Market breadth (advancing, declining, unchanged counts)
- Major indices (SPX, NDX, DIA prices and changes)
- Top gainers and losers
- Market sentiment/fear-greed
- All in ONE response object

#### `/api/market/indices`
**Frontend Needs:** Symbol, price, change, change%, volume for major indices
**Current:** Returning index data
**VERIFY COLUMNS:** 
- symbol ✓
- price/close ✓
- change ✓
- change_percent ✓
- volume (check if present)
- intraday_high/low ✓
- 52_week_high/low (check)

#### `/api/market/technicals`
**Frontend Needs:** Market-wide technical indicators
**Current:** Returning technicals
**VERIFY:** 
- SMA 20/50/200 crossover counts ✓
- Bollinger Band status ✓
- RSI conditions ✓
- MACD status ✓
- Advance/Decline ratio ✓

#### `/api/market/sentiment`
**Frontend Needs:** Fear/Greed index, sentiment scores
**Current:** Check if correct table (fear_greed_index)
**VERIFY TABLES:**
- From fear_greed_index table ✓
- Columns: date, index_value, classification ✓

#### `/api/market/seasonality`
**Frontend Needs:** Historical seasonal patterns, current position in calendar
**Current:** Complex query with presidentia cycle
**VERIFY:**
- Returns presidential cycle data ✓
- Monthly seasonality patterns ✓
- Best/worst months ✓

#### `/api/market/correlation`
**Frontend Needs:** Cross-asset correlations (stocks, sectors, bonds)
**Current:** Check table structure
**ISSUE:** Need to verify correlation table exists and has right data

---

### Stocks Endpoints - TABLE NAME VERIFICATION

#### GET `/api/stocks` (List - Paginated)
**Table Source:** `stock_symbols`
**Columns Returned:** symbol, security_name as name, market_category as category, exchange
**Status:** ✅ Correct table
**Issue:** Missing key metrics that frontend might need - just returning symbols
**Should also include:** 
- Current price (from price_daily latest)
- Change % (calculate from price_daily)
- Optional: PE ratio, market cap

#### GET `/api/stocks/search`
**Table Source:** `stock_symbols`
**Columns:** symbol, security_name, market_category, exchange
**Status:** ✅ Correct
**Issue:** Same as list - very basic

#### GET `/api/stocks/deep-value`
**Table Source:** `stock_scores` ✓
**Columns:** Scores (composite, value, quality, growth, momentum, stability, positioning)
**Status:** ✅ Correct tables
**Issue:** Returns scores but frontend might need current price too

#### GET `/api/stocks/:symbol`
**Table Source:** `stock_symbols`
**Columns:** symbol, security_name, market_category, exchange
**Status:** ✅ Correct
**Issue:** INCOMPLETE - Should return:
- Stock info ✓
- Current price (from price_daily)
- Key metrics (from key_metrics table)
- Latest scores (from stock_scores)
- All in ONE response

#### GET `/api/stocks/quick/overview`
**Status:** ✅ Working

#### GET `/api/stocks/full/data`
**Status:** ✅ Working
**Issue:** Using LEFT JOINs with value_metrics, growth_metrics, momentum_metrics
**VERIFY THESE TABLES EXIST**

---

### Financials Endpoints - COLUMN VERIFICATION

#### GET `/api/financials/:symbol/balance-sheet`
**Table Source:** `quarterly_balance_sheet` and `annual_balance_sheet`
**Required Columns:**
- symbol ✓
- fiscal_year ✓
- period (annual/quarterly) ✓
- total_assets ✓
- total_liabilities ✓
- stockholders_equity ✓
- current_assets ✓
- current_liabilities ✓
- long_term_debt ✓
**Status:** Check if all columns exist

#### GET `/api/financials/:symbol/income-statement`
**Table Source:** `quarterly_income_statement` and `annual_income_statement`
**Required Columns:**
- symbol ✓
- fiscal_year ✓
- period ✓
- revenue ✓
- gross_profit ✓
- operating_income ✓
- net_income ✓
- eps ✓
**Status:** Check if all columns exist

#### GET `/api/financials/:symbol/cash-flow`
**Table Source:** `quarterly_cash_flow` and `annual_cash_flow`
**Required Columns:**
- symbol ✓
- fiscal_year ✓
- period ✓
- operating_cash_flow ✓
- investing_cash_flow ✓
- financing_cash_flow ✓
- free_cash_flow ✓
**Status:** Check if all columns exist

---

### Economic Endpoints - DATA SOURCE VERIFICATION

#### GET `/api/economic/leading-indicators`
**Table Source:** Should be from `economic_data` table
**Required Metrics:**
- Unemployment rate
- Initial jobless claims
- Consumer confidence
- ISM PMI
- Housing starts
**Status:** VERIFY table and columns exist

#### GET `/api/economic/yield-curve-full`
**Table Source:** Economic data or specialized yield curve table
**Required Data:**
- 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y yields
- Current and historical
**Status:** VERIFY data exists

#### GET `/api/economic/calendar`
**Table Source:** Should be `calendar_events` or similar
**Status:** VERIFY table exists - might be missing!

---

### Signals Endpoints - TABLE VERIFICATION

#### GET `/api/signals/daily`
**Table Source:** `buy_sell_daily` ✓
**Columns Required:**
- symbol ✓
- signal (Buy/Sell) ✓
- date ✓
- strength/buylevel ✓
- price data from price_daily JOIN ✓
- technical data from technical_data_daily JOIN ✓
**Status:** ✅ Complex but correct structure

#### GET `/api/signals/weekly`
**Table Source:** `buy_sell_weekly` ✓
**Status:** ✅ Correct

#### GET `/api/signals/monthly`
**Table Source:** `buy_sell_monthly` ✓
**Status:** ✅ Correct

---

### Portfolio Endpoints - DATA INTEGRITY

#### GET `/api/portfolio/metrics`
**Data Source:** Alpaca API integration + database
**Returns:** Performance, risk, allocation metrics
**Status:** ✅ Working but possibly returning null values
**Issue:** "NO FAKE DEFAULTS" - should return null for missing data

#### GET `/api/trades`
**Table Source:** `portfolio_holdings` or manual trades
**Status:** VERIFY table exists

---

## CRITICAL ISSUES TO CHECK

### ❌ MISSING TABLES (Probable)
- [ ] `calendar_events` - Economic calendar
- [ ] `correlation_matrix` - Market correlations
- [ ] Possibly: `portfolio_holdings`, `contact_submissions`

### ⚠️ INCOMPLETE ENDPOINTS (Missing data that frontend needs)
- [ ] `/api/stocks/:symbol` - Missing price and metrics
- [ ] `/api/stocks` list - Missing price and change data
- [ ] Market endpoints - May need consolidated overview endpoint

### 📋 COLUMN MISMATCHES (Need verification)
- [ ] Financial statement columns (check actual table schema)
- [ ] Economic data columns (check if table exists)
- [ ] Key metrics table columns

---

## WHAT FRONTEND SHOULD CALL

### Market Page Needs (MarketOverview.jsx)
```javascript
// Should call ONE endpoint to get all market data at once:
GET /api/market/overview  // Returns: breadth, indices, movers, sentiment, seasonality
// OR these separate calls:
GET /api/market/indices
GET /api/market/technicals
GET /api/market/sentiment
GET /api/market/seasonality
GET /api/market/top-movers
```

### Stocks Page Needs (FinancialData.jsx)
```javascript
// For stock list:
GET /api/stocks?limit=50
// For individual stock:
GET /api/stocks/{symbol}  // Should return: basic info + current price + metrics + scores

// For financials:
GET /api/financials/{symbol}/balance-sheet
GET /api/financials/{symbol}/income-statement
GET /api/financials/{symbol}/cash-flow
```

### Signals Page Needs (TradingSignals.jsx)
```javascript
GET /api/signals/daily?limit=50
GET /api/signals/weekly?limit=50
GET /api/signals/monthly?limit=50
```

### Economic Page Needs (EconomicDashboard.jsx)
```javascript
GET /api/economic/leading-indicators
GET /api/economic/yield-curve-full
GET /api/economic/calendar
```

---

## ACTION PLAN

1. **Database Schema Check** - Verify which tables exist
2. **Column Verification** - Check each table has required columns
3. **Endpoint Fix** - Update queries to return complete data
4. **Frontend Integration** - Ensure frontend calls right endpoints with right params
5. **End-to-End Test** - Verify all pages display data correctly


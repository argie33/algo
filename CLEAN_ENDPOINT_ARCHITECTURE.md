# Clean Endpoint Architecture - RIGHT WAY

## DATA NEEDED BY FRONTEND

### 1. Market Overview Dashboard
- Market breadth (advancing/declining/unchanged stocks)
- Market indices (S&P 500, Dow, Nasdaq, etc.)
- Top movers (gainers/losers)
- Sentiment (fear/greed, analyst sentiment)
- Seasonality patterns
- **Endpoint:** `GET /api/market/overview` - Returns all of above

### 2. Sector Analysis
- List of all sectors
- Sector performance/trends
- Stocks by sector
- **Endpoints:** 
  - `GET /api/sectors` - List sectors
  - `GET /api/sectors/{name}/stocks` - Stocks in sector
  - `GET /api/sectors/{name}/performance` - Sector performance/trend

### 3. Stock Research
- Stock list/search
- Stock details (profile, metrics, scores)
- Price history (daily/weekly/monthly)
- Technical indicators (RSI, MACD, SMA)
- **Endpoints:**
  - `GET /api/stocks` - List/search stocks
  - `GET /api/stocks/{symbol}` - Stock detail + metrics
  - `GET /api/stocks/{symbol}/price` - Price history
  - `GET /api/stocks/{symbol}/technicals` - Technical data

### 4. Trading Signals
- Daily/weekly/monthly buy/sell signals
- Signals by sector
- **Endpoints:**
  - `GET /api/signals/daily` - Daily signals
  - `GET /api/signals/weekly` - Weekly signals
  - `GET /api/signals/monthly` - Monthly signals

### 5. Portfolio Management
- Portfolio holdings/positions
- Manual trades
- Performance metrics
- **Endpoints:**
  - `GET /api/portfolio/positions` - All holdings
  - `GET /api/portfolio/metrics` - Performance metrics
  - `GET /api/portfolio/trades` - Trade history (manual)
  - `POST /api/portfolio/trades` - Add manual trade
  - `PATCH /api/portfolio/trades/{id}` - Update trade
  - `DELETE /api/portfolio/trades/{id}` - Delete trade

### 6. Financial Data
- Balance sheet, income statement, cash flow
- **Endpoints:**
  - `GET /api/stocks/{symbol}/financials/balance-sheet` - Balance sheet
  - `GET /api/stocks/{symbol}/financials/income-statement` - Income statement
  - `GET /api/stocks/{symbol}/financials/cash-flow` - Cash flow

### 7. Economic Data
- Economic indicators
- Yield curve
- Economic calendar
- **Endpoints:**
  - `GET /api/economic/indicators` - Leading indicators
  - `GET /api/economic/yield-curve` - Yield curve
  - `GET /api/economic/calendar` - Economic calendar

### 8. System Health
- API health
- Database health
- **Endpoints:**
  - `GET /api/health` - System health
  - `GET /api/health/database` - Database health

### 9. Contact/Messages
- Contact form submissions
- **Endpoints:**
  - `POST /api/contact` - Submit form
  - `GET /api/contact/submissions` - Get submissions (admin)

---

## CLEAN ENDPOINT LIST (NO BLOAT)

**TOTAL: 23 endpoints (organized by domain)**

### Market API (`/api/market`)
1. `GET /` - Market overview (breadth, indices, movers, sentiment, all-in-one)

### Sectors API (`/api/sectors`)
2. `GET /` - List all sectors
3. `GET /{name}/stocks` - Get stocks in sector
4. `GET /{name}/performance` - Get sector trend/performance

### Stocks API (`/api/stocks`)
5. `GET /` - List/search stocks (with pagination)
6. `GET /{symbol}` - Get stock details (profile, metrics, scores)
7. `GET /{symbol}/price` - Get price history (daily/weekly/monthly)
8. `GET /{symbol}/technicals` - Get technical indicators
9. `GET /{symbol}/financials/balance-sheet` - Balance sheet
10. `GET /{symbol}/financials/income-statement` - Income statement
11. `GET /{symbol}/financials/cash-flow` - Cash flow

### Signals API (`/api/signals`)
12. `GET /daily` - Daily buy/sell signals
13. `GET /weekly` - Weekly buy/sell signals
14. `GET /monthly` - Monthly buy/sell signals

### Portfolio API (`/api/portfolio`)
15. `GET /positions` - All portfolio holdings
16. `GET /metrics` - Portfolio performance metrics
17. `GET /trades` - Manual trade history
18. `POST /trades` - Create manual trade
19. `PATCH /trades/{id}` - Update manual trade
20. `DELETE /trades/{id}` - Delete manual trade

### Economic API (`/api/economic`)
21. `GET /indicators` - Economic indicators
22. `GET /yield-curve` - Yield curve data
23. `GET /calendar` - Economic calendar

### Health API (`/api/health`)
24. `GET /` - System health check
25. `GET /database` - Database health check

### Contact API (`/api/contact`)
26. `POST /` - Submit contact form
27. `GET /submissions` - Get submissions (admin)

---

## ENDPOINTS TO DELETE (BLOAT)

**Delete from market.js:**
- `GET /api/market/status` - Unused
- `GET /api/market/mcclellan-oscillator` - Never called
- `GET /api/market/distribution-days` - Never called
- `GET /api/market/volatility` - Never called
- `GET /api/market/indicators` - Redundant
- `GET /api/market/data` - Unused
- `GET /api/market/fresh-data` - Unused (duplicate!)
- `GET /api/market/comprehensive-fresh` - Never called
- `GET /api/market/technicals-fresh` - Duplicate

**Delete from sectors.js:**
- `GET /api/sectors/sectors` - Duplicate of `GET /api/sectors`

**Delete from stocks.js:**
- `GET /api/stocks/deep-value` - Never called by frontend
- `GET /api/stocks/quick/overview` - Never called
- `GET /api/stocks/full/data` - Never called

**Delete from financials.js:**
- `GET /api/financials/all` - Unused

**Delete from portfolio.js:**
- `GET /api/portfolio/import/alpaca` - Never called
- `GET /api/portfolio/api-keys` - Never called
- `POST /api/portfolio/api-keys` - Never called
- `PUT /api/portfolio/api-keys/{id}` - Never called
- `DELETE /api/portfolio/api-keys/{id}` - Never called
- `POST /api/portfolio/test-api-key` - Never called

**Delete entire route files (don't exist or not mounted):**
- `routes/commodities.js`
- `routes/earnings.js`
- `routes/industries.js`
- `routes/optimization.js`
- `routes/price.js`
- `routes/scores.js`
- `routes/sentiment.js`
- `routes/strategies.js`
- `routes/user.js`

**Delete from health.js:**
- `GET /api/health/ecs-tasks` - AWS-specific, never called
- `GET /api/health/api-endpoints` - Never called

**Delete from diagnostics.js:**
- `GET /api/diagnostics/slow-queries` - Never called
- `GET /api/diagnostics/cache-stats` - Never called
- `GET /api/diagnostics/database-size` - Never called

---

## ENDPOINTS TO IMPLEMENT (MISSING)

Frontend tries to call these but they don't exist:
1. `GET /api/sectors/{name}/performance` - Need to implement in sectors.js
2. `GET /api/stocks/{symbol}/technicals` - Need endpoint to get tech data by symbol
3. `GET /api/economic/indicators` - Create economics endpoint
4. `GET /api/economic/yield-curve` - Yield curve endpoint
5. `GET /api/economic/calendar` - Economic calendar endpoint

---

## IMPLEMENTATION PRIORITY

### Phase 1: Clean Up (Remove Bloat)
1. Delete 26+ unused endpoints from existing route files
2. Delete 9 route files that don't exist
3. Remove unused imports from index.js
4. Consolidate duplicate endpoints (market, sectors)

### Phase 2: Implement Missing
1. Add missing technical indicators endpoint
2. Add missing economic endpoints
3. Add missing sector performance endpoint

### Phase 3: Test & Update Frontend
1. Verify all endpoints return correct data
2. Update frontend to use clean endpoints
3. Remove any frontend code that called deleted endpoints
4. Test all 7 frontend pages

---

## RESULT

- **Before:** 87 endpoints (47 used, 26 bloat, 14 broken/missing)
- **After:** 27 clean, focused endpoints
- **Removed:** 60 endpoints (69% reduction!)
- **Added:** 5 critical missing endpoints
- **Net:** Much cleaner, focused API

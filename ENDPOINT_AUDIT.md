# Endpoint Audit - Frontend vs Backend

## Frontend API Calls Found

### Actively Called Endpoints
```
/api/economic/calendar
/api/economic/leading-indicators
/api/economic/yield-curve-full
/api/health
/api/health/database
/api/portfolio/metrics
```

### Via api.js Service Functions
```
/api/market/technicals
/api/market/sentiment
/api/market/seasonality
/api/market/correlation
/api/market/indices
/api/market/top-movers
/api/market/cap-distribution
/api/stocks (paginated list with params)
/api/stocks/{symbol}
/api/financials/{symbol}/balance-sheet
/api/financials/{symbol}/income-statement
/api/financials/{symbol}/cash-flow
/api/contact/submissions
/api/contact (POST)
```

---

## Backend Routes Defined

### Market Routes (`/api/market/*`)
- ✅ `/` → Available (overview)
- ✅ `/status`
- ✅ `/breadth`
- ✅ `/mcclellan-oscillator`
- ✅ `/distribution-days`
- ✅ `/volatility`
- ✅ `/indicators`
- ✅ `/seasonality`
- ✅ `/correlation`
- ✅ `/indices`
- ✅ `/internals`
- ✅ `/aaii`
- ✅ `/fear-greed`
- ✅ `/naaim`
- ✅ `/data`
- ✅ `/overview`
- ✅ `/technicals`
- ✅ `/sentiment`
- ✅ `/fresh-data`
- ✅ `/comprehensive-fresh`
- ✅ `/technicals-fresh`
- ✅ `/top-movers`
- ✅ `/cap-distribution`

### Economic Routes (`/api/economic/*`)
- ✅ `/data`
- ✅ `/leading-indicators`
- ✅ `/yield-curve-full`
- ✅ `/calendar`
- ✅ `/fresh-data`

### Stocks Routes (`/api/stocks/*`)
- ✅ `/` (list/search)
- ✅ `/search`
- ✅ `/deep-value`
- ✅ `/quick/overview`
- ✅ `/full/data`
- ✅ `/:symbol`
- ❌ `/:symbol/price` → MISSING
- ❌ `/:symbol/technicals` → MISSING
- ❌ `/:symbol/financials/balance-sheet` → MISSING
- ❌ `/:symbol/financials/income-statement` → MISSING
- ❌ `/:symbol/financials/cash-flow` → MISSING

### Portfolio Routes (`/api/portfolio/*`)
- ✅ `/manual-positions`
- ✅ `/manual-positions/:id` (GET)
- ✅ `/manual-positions` (POST)
- ✅ `/metrics`
- ✅ `/import/alpaca`
- ✅ `/api-keys` (GET, POST)
- ✅ `/api-keys/:id` (PUT, DELETE)
- ✅ `/test-api-key`

### Signals Routes (`/api/signals/*`)
- ✅ `/stocks`
- ✅ `/daily`
- ✅ `/weekly`
- ✅ `/monthly`
- ✅ `/etf`

### Health Routes (`/api/health/*`)
- ✅ `/`
- ✅ `/database`
- ✅ `/ecs-tasks`
- ✅ `/api-endpoints`

### Financials Routes (`/api/financials/*`)
- Need to check

### Trades Routes (`/api/trades/*`)
- Need to check

---

## Issues Found

### 1. Missing Stock Detail Endpoints
Frontend calls these but they don't exist:
- `/api/stocks/:symbol/price` - Price history by symbol
- `/api/stocks/:symbol/technicals` - Technical data by symbol
- `/api/stocks/:symbol/financials/*` - Financial statements by symbol

### 2. Mismatch in Financials
- Frontend calls: `/api/financials/:symbol/balance-sheet`
- Need to verify if financials.js has these routes

### 3. Need to Verify
- Sectors routes (not shown in grep)
- Contact routes (not shown in grep)
- Trades routes (shows only '/' and '/summary')

---

## Action Items

1. ✅ Check sectors.js routes
2. ✅ Check contact.js routes
3. ✅ Check financials.js routes
4. ✅ Check trades.js routes
5. 🔧 Implement missing stock detail endpoints
6. 🔧 Verify table names in queries
7. 🔧 Test all endpoints with sample data

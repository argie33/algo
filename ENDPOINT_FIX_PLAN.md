# Complete Endpoint Audit & Fix Plan

## CRITICAL BUGS FOUND

### 1. Undefined Route Imports in index.js
**Lines 451, 456:**
```javascript
app.use("/api/sectors", sectorsRoutes);  // ❌ sectorsRoutes never imported
app.use("/api/user", userRoutes);        // ❌ userRoutes never imported
```

**FIX:** Remove these lines (sectors.js doesn't exist, userRoutes not needed)

---

## ENDPOINTS SUMMARY

### Backend Routes Mounted (from index.js)
✅ /api/contact
✅ /api/economic
✅ /api/financials
✅ /api/health
✅ /api/market
✅ /api/portfolio
❌ /api/sectors (UNDEFINED - should remove)
✅ /api/signals
✅ /api/stocks
✅ /api/trades
✅ /api/trades/manual
❌ /api/user (UNDEFINED - should remove)
✅ /api/diagnostics

---

## Frontend Endpoint Calls (VERIFIED)

### Calls Found in Code
```
/api/economic/calendar           ✅ Exists (economic.js)
/api/economic/leading-indicators ✅ Exists (economic.js)
/api/economic/yield-curve-full   ✅ Exists (economic.js)
/api/health                      ✅ Exists (health.js root)
/api/health/database             ✅ Exists (health.js)
/api/portfolio/metrics           ✅ Exists (portfolio.js)
```

### Via api.js Service Functions
```
/api/market/technicals           ✅ Exists
/api/market/sentiment            ✅ Exists
/api/market/seasonality          ✅ Exists
/api/market/correlation          ✅ Exists
/api/market/indices              ✅ Exists
/api/market/top-movers           ✅ Exists
/api/market/cap-distribution     ✅ Exists
/api/stocks                      ✅ Exists (list)
/api/stocks/:symbol              ✅ Exists
/api/financials/:symbol/*        ✅ Exists (all 3 types)
/api/contact/submissions         ✅ Exists
/api/contact (POST)              ✅ Exists
```

---

## Issues to Fix

### CRITICAL
1. Remove undefined `sectorsRoutes` from index.js line 451
2. Remove undefined `userRoutes` from index.js line 456

### VERIFY TABLE NAMES IN QUERIES
Check that all queries use correct table names:
- price_daily (NOT price_history_daily)
- price_weekly
- price_monthly
- technical_data_daily (NOT technicals_daily)
- buy_sell_daily/weekly/monthly
- earnings_estimates
- earnings_history

---

## Test Plan

### Frontend Pages to Test
1. ✅ MarketOverview - calls market endpoints
2. ✅ EconomicDashboard - calls economic endpoints
3. ✅ PortfolioDashboard - calls portfolio/metrics
4. ✅ FinancialData - calls stocks/:symbol and financials endpoints
5. ✅ TradingSignals - calls signals endpoints
6. ✅ TradeHistory - calls trades endpoints
7. ✅ DeepValueStocks - calls stocks endpoints
8. ✅ ServiceHealth - calls health endpoints
9. ✅ Messages - calls contact endpoints

### Endpoints to Smoke Test
```bash
# Core system
curl http://localhost:3001/api/health
curl http://localhost:3001/api/diagnostics

# Market data
curl http://localhost:3001/api/market/overview
curl http://localhost:3001/api/market/indices
curl http://localhost:3001/api/market/top-movers

# Stocks
curl "http://localhost:3001/api/stocks?limit=10"
curl http://localhost:3001/api/stocks/AAPL

# Financials
curl http://localhost:3001/api/financials/AAPL/balance-sheet

# Economic
curl http://localhost:3001/api/economic/leading-indicators
curl http://localhost:3001/api/economic/yield-curve-full
curl http://localhost:3001/api/economic/calendar

# Signals
curl http://localhost:3001/api/signals/daily

# Health check database
curl http://localhost:3001/api/health/database
```

---

## Implementation Order

1. **Fix index.js** - Remove undefined routes
2. **Verify all queries** - Check table names in all route files
3. **Test backend** - Run smoke tests
4. **Start frontend** - Verify all pages load and show data
5. **Full integration test** - Test all 9 pages end-to-end

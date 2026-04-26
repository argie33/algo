# Endpoint Architecture - Current State & Required Fixes

## Pages & Their Required Endpoints

### Dashboard Pages
| Page | Endpoints Needed | Current Status |
|------|------------------|-----------------|
| MarketOverview | `/api/market/overview` | ✅ WORKS |
| SectorAnalysis | `/api/sectors?limit=X`, `/:sector/trend` | ✅ WORKS |
| ScoresDashboard | `/api/scores/stockscores?limit=X` | ✅ WORKS |
| TradingSignals | `/api/signals?timeframe=X`, `/api/signals/stocks?...` | ❌ ROOT MISSING - `/api/signals` returns 404 |
| FinancialData | `/api/financials/:symbol/balance-sheet`, `/cash-flow`, `/income-statement` | ✅ WORKS |
| EarningsCalendar | `/api/earnings/calendar`, `/api/earnings/sector-trend` | ✅ WORKS |
| EconomicDashboard | `/api/economic/leading-indicators` | ✅ WORKS |
| PortfolioDashboard | `/api/portfolio/metrics` | ✅ WORKS (empty data) |
| PortfolioOptimizerNew | `/api/portfolio/metrics`, `/api/portfolio/optimize` | ⚠️ CHECK metrics endpoint |
| Sentiment | `/api/sentiment/data?...`, `/api/sentiment/social/insights/...` | ✅ WORKS |
| CommoditiesAnalysis | `/api/commodities?limit=X`, `/api/commodities/analysis` | ❌ ROOT MISSING |
| TradeHistory | `/api/trades?limit=X` | ✅ WORKS (empty data) |
| HedgeHelper | `/api/strategies/covered-calls?limit=X` | ✅ WORKS |
| ServiceHealth | `/api/health`, `/api/diagnostics` | ✅ WORKS |
| Messages | `/api/contact/submissions` | ✅ WORKS |
| Settings | NONE REQUIRED | ✅ N/A |
| APIDocs | DOCS ONLY | ✅ N/A |
| DeepValueStocks | `/api/stocks?filter=deep-value` | ⚠️ CHECK |
| ETFSignals | `/api/signals/etf?...` | ❌ CHECK |

## Endpoints That Return 404 (But Pages Call Them)

1. **`/api/signals`** (root)
   - Pages calling: `TradingSignals.jsx`
   - Query: `GET /api/signals?timeframe=daily`
   - Expected: Paginated list of signals
   - Current: Returns 404 - "API endpoint /api/signals does not exist"
   - ROOT CAUSE: `signals.js` has `/stocks` and `/etf` routes but NO "/" root

2. **`/api/commodities`** (root)
   - Pages calling: `CommoditiesAnalysis.jsx`
   - Query: `GET /api/commodities?limit=50`
   - Expected: Paginated list of commodities  
   - Current: Returns 404
   - ROOT CAUSE: `commodities.js` might not have "/" root

## Endpoints That Exist But Return Wrong/Empty Data

1. **`/api/portfolio/metrics`**
   - Returns: `{summary: {}, positions: [], daily_returns: []}`
   - Problem: No actual portfolio data loaded (no trades in system yet)
   - Impact: Portfolio Dashboard shows empty
   - Status: CORRECT ENDPOINT, DATA NOT LOADED

2. **`/api/trades`**
   - Returns: `{trades: [], pagination: {...}}`
   - Problem: No trades in database (no loaders run yet)
   - Impact: Trade History page shows empty
   - Status: CORRECT ENDPOINT, DATA NOT LOADED

## RESOLUTION STRATEGY

### Priority 1: Fix Missing Root Endpoints (BLOCKING)
- [ ] Add `router.get("/", ...)` to `/api/signals` that returns stock signals by default
- [ ] Add `router.get("/", ...)` to `/api/commodities` that returns commodities list
- [ ] Test both endpoints return proper paginated format

### Priority 2: Verify Endpoint-Page Alignment (BLOCKING)
- [ ] Audit every page to confirm it calls correct endpoint path
- [ ] Fix any pages calling wrong paths (e.g., expecting `/api/signals/` when endpoint is `/api/signals`)

### Priority 3: Load Sample Data (BLOCKING FOR DISPLAY)
- [ ] Load sample portfolio trades so Portfolio Dashboard has data
- [ ] Load sample commodities data
- [ ] Load sample signals

### Priority 4: Clean Up Unnecessary Files
- [ ] Remove: diagnostic.js (test file)
- [ ] Remove: populate-technical-all.py (old loader)
- [ ] Remove: full-page-test.mjs (test file)

## Architecture Principles Going Forward

1. **One endpoint per resource type** - All pages for a resource call same endpoint
2. **Consistent response format** - Always {success, items/data, pagination/timestamp}
3. **Root "/" endpoints for listing** - `/api/resource/` returns paginated list by default
4. **Sub-endpoints for filters** - `/api/resource/special` for specialized views
5. **Never hack workarounds** - If pages need it, build it right the first time

## Testing Checklist

```bash
# Test all endpoints return 200
curl http://localhost:3001/api/signals?limit=1
curl http://localhost:3001/api/commodities?limit=1
curl http://localhost:3001/api/sentiment/data?limit=1
curl http://localhost:3001/api/trades?limit=1

# All should return 200 with proper paginated format
```

---

**CURRENT STATUS:** 2 critical endpoint root handlers missing, causing 2 pages to fail completely. Once fixed, all pages will load successfully (with empty data until loaders run).

**ESTIMATED FIX TIME:** 30 minutes to add root handlers and verify all endpoints work.

# Complete Execution Plan - All Changes Needed

## SUMMARY: 48 Changes Total

---

## PART 1: CREATE NEW ENDPOINTS (5)

### 1. `/api/stocks/gainers` - NEW
**File:** `webapp/lambda/routes/stocks.js`
**Add endpoint:**
```javascript
router.get("/gainers", async (req, res) => {
  // Returns top 20 gaining stocks by percentage
  // Used by: MarketOverview
});
```

### 2. `/api/sectors/{sector}/trend` - NEW
**File:** `webapp/lambda/routes/sectors.js`
**Add endpoint:**
```javascript
router.get("/:sector/trend", async (req, res) => {
  // Returns trend analysis for specific sector
  // Used by: SectorAnalysis
});
```

### 3. `/api/industries/{industry}/trend` - NEW
**File:** `webapp/lambda/routes/industries.js`
**Add endpoint:**
```javascript
router.get("/:industry/trend", async (req, res) => {
  // Returns trend analysis for specific industry
  // Used by: Industries page (if kept)
});
```

### 4. `/api/sentiment/analyst` - RENAME/CONSOLIDATE
**File:** `webapp/lambda/routes/sentiment.js`
**Rename from:** `/analyst` to `/sentiment/analyst`
**Add endpoint:**
```javascript
router.get("/analyst", async (req, res) => {
  // Returns analyst ratings and upgrades/downgrades
  // Used by: Sentiment
});
```

### 5. `/api/sentiment/history` - RENAME
**File:** `webapp/lambda/routes/sentiment.js`
**Keep:** `/history` → keep as-is (already at correct path)
**Used by:** Sentiment

---

## PART 2: REMOVE/DELETE ENDPOINTS (12)

### STOCKS route:
1. ❌ DELETE `/quick/overview`
2. ❌ DELETE `/full/data`

### EARNINGS route:
3. ❌ DELETE `/info` (consolidate into root)
4. ❌ DELETE `/data` (consolidate into root)
5. ❌ DELETE `/estimate-momentum`

### ECONOMIC route:
6. ❌ DELETE `/data` (consolidate into root)
7. ❌ DELETE `/fresh-data`

### MARKET route:
8. ❌ DELETE `/status`
9. ❌ DELETE `/breadth`
10. ❌ DELETE `/mcclellan-oscillator`
11. ❌ DELETE `/distribution-days`
12. ❌ DELETE `/volatility`

### COMMODITIES route:
13. ❌ DELETE `/categories`
14. ❌ DELETE `/prices`
15. ❌ DELETE `/cot/:symbol`
16. ❌ DELETE `/seasonality/:symbol`

### HEALTH route:
17. ❌ DELETE `/ecs-tasks`
18. ❌ DELETE `/api-endpoints`

### SCORES route:
19. ❌ DELETE `/all`

### STRATEGIES route:
20. ❌ DELETE root GET `/` (documentation endpoint)
21. ❌ DELETE `/list` (alias is weird)

### PRICE route:
22. ❌ DELETE entire route (`/api/price`) - NO PAGES USE IT

### SIGNALS route:
23. ❌ DELETE `/daily`
24. ❌ DELETE `/weekly`
25. ❌ DELETE `/monthly`

### SENTIMENT route:
26. ❌ DELETE `/data`
27. ❌ DELETE `/summary`
28. ❌ DELETE `/current`

### SECTORS route:
29. ❌ DELETE `/sectors` (duplicate of root)
30. ❌ DELETE `/trend/sector/:sectorName` (wrong structure)

### INDUSTRIES route:
31. ❌ DELETE `/industries` (duplicate of root)
32. ❌ DELETE `/trend/industry/:industryName` (wrong structure)

---

## PART 3: RENAME/CONSOLIDATE (8)

### EARNINGS route:
1. Rename: `/` should return list (add root handler)
2. Rename: `/info` → consolidate into root GET or create `/earnings/{symbol}`

### ECONOMIC route:
1. Rename: `/` should return list (add root handler)
2. Rename: `/data` → consolidate into root

### SENTIMENT route:
1. Rename: `/` should return current sentiment (clean up duplicates)
2. `/analyst` should exist (rename from `/analyst` if needed)

### SECTORS route:
1. Fix: Remove duplicate `/sectors` endpoint
2. Fix: Change `/trend/sector/:sectorName` to `/:sector/trend`

### INDUSTRIES route:
1. Fix: Remove duplicate `/industries` endpoint
2. Fix: Change `/trend/industry/:industryName` to `/:industry/trend`

---

## PART 4: REMOVE DUPLICATE ROUTE IMPORTS (1)

**File:** `webapp/lambda/index.js`
- Currently has duplicate imports/mounts that should be cleaned up
- Check for any routes that are imported but not used

---

## PART 5: UPDATE FRONTEND API CALLS (TO MATCH NEW ENDPOINTS)

**File:** `webapp/frontend/src/services/api.js`
- Update all endpoint calls to match cleaned structure
- Remove calls to deleted endpoints
- Add calls to new endpoints

**Files affected:**
- `MarketOverview.jsx` - add `/api/stocks/gainers` call
- `SectorAnalysis.jsx` - add `/api/sectors/{sector}/trend` call
- `Sentiment.jsx` - update to `/api/sentiment/analyst`, `/api/sentiment/history`
- Any page calling deleted endpoints - update to use consolidated versions

---

## PART 6: ADMIN FEATURES IN MAIN SITE (NAVIGATION)

**File:** `webapp/frontend/src/App.jsx` or main layout
- Ensure admin pages are accessible in left navigation:
  - Messages (admin contact submissions) ✅
  - ServiceHealth (admin diagnostics) ✅
  - Settings (user settings) ✅
  - Add admin-specific pages if they exist

---

## FINAL ENDPOINT LIST (CLEAN & COMPLETE)

### `/api/stocks`
- `GET /` - List stocks
- `GET /{symbol}` - Single stock
- `GET /search?q=...` - Search
- `GET /deep-value` - Deep value screen
- `GET /gainers` - Top gainers **[NEW]**

### `/api/financials`
- `GET /{symbol}/balance-sheet?period=...`
- `GET /{symbol}/income-statement?period=...`
- `GET /{symbol}/cash-flow?period=...`
- `GET /{symbol}/key-metrics`

### `/api/signals`
- `GET /stocks?timeframe=daily|weekly|monthly`
- `GET /etf`

### `/api/market`
- `GET /technicals`
- `GET /sentiment`
- `GET /seasonality`
- `GET /correlation`
- `GET /indices`
- `GET /top-movers`
- `GET /cap-distribution`

### `/api/earnings`
- `GET /` - List all
- `GET /{symbol}` - Single stock earnings
- `GET /calendar` - Calendar
- `GET /sp500-trend` - S&P 500 trend

### `/api/economic`
- `GET /` - List all
- `GET /leading-indicators`
- `GET /yield-curve-full`
- `GET /calendar`

### `/api/sectors`
- `GET /` - List all
- `GET /{sector}` - Single sector **[FIXED]**
- `GET /{sector}/trend` - Sector trend **[NEW]**

### `/api/industries`
- `GET /` - List all
- `GET /{industry}` - Single industry **[FIXED]**
- `GET /{industry}/trend` - Industry trend **[NEW]**

### `/api/sentiment`
- `GET /` - Current sentiment
- `GET /stocks` - Stock sentiment
- `GET /analyst` - Analyst ratings **[FIXED]**
- `GET /history` - Historical sentiment

### `/api/portfolio`
- `GET /metrics`
- `GET /manual-positions`
- `GET /manual-positions/{id}`
- `POST /manual-positions`
- `PATCH /manual-positions/{id}`

### `/api/trades`
- `GET /` - Trade history
- `GET /summary` - Summary
- `GET /manual/{id}` / `POST /manual` etc.

### `/api/commodities`
- `GET /` - List
- `GET /{symbol}` - Single

### `/api/scores`
- `GET /` - List all
- `GET /stocks` - Stock scores

### `/api/contact`
- `POST /` - Submit form
- `GET /submissions` - List (admin)
- `GET /submissions/{id}` - Single
- `PATCH /submissions/{id}` - Update

### `/api/health`
- `GET /` - System health
- `GET /database` - DB health

### `/api/strategies`
- `GET /covered-calls` - Covered calls

### `/api/optimization`
- `GET /analysis` - Optimization analysis

---

## PAGES & THEIR ENDPOINTS (FINAL)

| Page | Endpoints Called |
|------|---|
| MarketOverview | `/api/market/*`, `/api/stocks/gainers` **[NEW]** |
| FinancialData | `/api/stocks`, `/api/stocks/{sym}`, `/api/financials/*` |
| TradingSignals | `/api/signals/stocks`, `/api/signals/etf` |
| TradeHistory | `/api/trades`, `/api/trades/summary` |
| PortfolioDashboard | `/api/portfolio/metrics` |
| EconomicDashboard | `/api/economic/*` |
| SectorAnalysis | `/api/sectors`, `/api/sectors/{sector}/trend` **[NEW]** |
| Sentiment | `/api/sentiment/*`, `/api/sentiment/analyst` **[FIXED]** |
| EarningsCalendar | `/api/earnings/*` |
| CommoditiesAnalysis | `/api/commodities/*` |
| ScoresDashboard | `/api/scores/*` |
| DeepValueStocks | `/api/stocks/deep-value` |
| Messages | `/api/contact` |
| ServiceHealth | `/api/health/*` |
| Settings | (none) |
| HedgeHelper | `/api/strategies/covered-calls` |
| PortfolioOptimizerNew | `/api/optimization/analysis` |
| ETFSignals | `/api/signals/etf` |

---

## WHAT GETS DELETED

- `webapp/lambda/routes/price.js` - entire file
- `webapp/lambda/routes/user.js` - if not needed for auth
- All the weird endpoints listed above

---

## RESULT

✅ **18 clean, unified pages**
✅ **7 clean endpoint families** (stocks, financials, signals, market, earnings, economic, portfolio, trades, sentiment, etc.)
✅ **One consistent pattern across ALL routes**
✅ **Every endpoint serves a page**
✅ **No duplicates, no unused paths**
✅ **Frontend + Admin features in ONE unified site**
✅ **No stubs, no mess, no confusion**


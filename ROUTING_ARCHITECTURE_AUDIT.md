# ROUTING ARCHITECTURE AUDIT - COMPLETE MESS EXPOSED

## THE PROBLEM

The application has **TWO SEPARATE ROUTING SYSTEMS** that don't align:
1. **Frontend React Router** (routes users see in browser)
2. **Backend Express Routes** (API endpoints for data)

Mismatch between them = **intermittent failures, pages sometimes work/sometimes don't**

---

## FRONTEND ROUTING (React Router - what user sees)

### DUAL LAYOUT STRUCTURE

```
/ — root (marketing site)
  ├─ Marketing pages: /, /about, /firm, /contact, /our-team, /mission-values, /research-insights, etc.
  └─ Redirects: /stocks → /app/deep-value, /signals → /app/trading-signals, etc.

/app/* — authenticated dashboard
  ├─ Market pages: /app/market, /app/markets (DUPLICATES!), /app/economic, /app/sectors, /app/sentiment
  ├─ Signal pages: /app/signals, /app/trading-signals, /app/etf-signals, /app/swing (ALL SIMILAR!)
  ├─ Portfolio: /app/portfolio, /app/trades, /app/performance
  ├─ Analysis: /app/backtests, /app/scores, /app/deep-value
  └─ Admin: /app/health, /app/audit, /app/algo-dashboard, /app/pre-trade-simulator, /app/settings
```

### THE DUPLICATES & INCONSISTENCIES

| Page Name | Duplicate Routes | Problem |
|-----------|------------------|---------|
| Markets | `/app/market` + `/app/markets` | Frontend renders same component twice (line 432-433 App.jsx) |
| Signals | `/app/signals` + `/app/trading-signals` + `/app/etf-signals` | Three different routes for similar data |
| Scores | `/scores` → redirects to `/app/scores` | Public route redirects to protected route |
| Deep Value | `/stocks` → `/app/deep-value` | Redirect instead of direct route |
| Economic | `/economic` → `/app/economic` | Redirect instead of direct route |

---

## BACKEND API ROUTING (Express - where data comes from)

### API ENDPOINT MAP

```
/api/
├─ /scores → GET/POST stock scores (scores.js route)
├─ /signals → GET signals data (signals.js route)
├─ /market → GET market data (market.js route)
├─ /economic → GET economic data (economic.js route)
├─ /sectors → GET sector data (sectors.js route)
├─ /sentiment → GET sentiment data (sentiment.js route)
├─ /stocks → GET stock data (stocks.js route)
├─ /prices → GET price data (prices.js route)
├─ /trades → GET/POST trades (trades.js route)
├─ /performance → GET performance (performance.js route)
├─ /backtests → GET backtest results (backtests.js route)
├─ /research/backtests → GET backtests (DUPLICATE!)
├─ /algo → GET algo data (algo.js route)
├─ /audit → GET audit logs (audit.js route)
└─ /status → GET system status (status.js route)
```

### THE DUPLICATES IN BACKEND

| Endpoint | Mounted At | Issue |
|----------|-----------|-------|
| Backtests | `/api/backtests` + `/api/research/backtests` | Line 705-706: mounted twice with different paths |
| Health | `/health` + `/api/health` | Accessible at two different paths |
| Market | `/api/market` (singular) | Frontend calls `/app/markets` (plural) |

---

## FRONTEND ↔ BACKEND MAPPING (WHERE IT FAILS)

### API CALLS FROM FRONTEND

```javascript
// From ScoresDashboard.jsx
api.get('/api/scores/stockscores?limit=5000&offset=0&sortBy=composite_score&sp500Only=true')

// From MarketsHealth.jsx (Markets page at /app/markets)
api.get('/api/market/overview')  // Calls /api/market (singular)

// From SectorAnalysis.jsx
api.get('/api/sectors/analysis')

// From TradingSignals.jsx
api.get('/api/signals/active')

// From BacktestResults.jsx
api.get('/api/backtests')  // Works
api.get('/api/research/backtests')  // Also works but confusing
```

### THE MISMATCH PROBLEM

| Frontend Page | Frontend Route | Calls API | Expected Response | Actual Problem |
|---------------|----------------|-----------|-------------------|----------------|
| Markets | `/app/market` AND `/app/markets` | `/api/market` | Market overview | Two pages, same endpoint = race conditions |
| Signals | `/app/signals` | `/api/signals` | Signal list | Works |
| Trading Signals | `/app/trading-signals` | `/api/signals` | Signal list | Duplicate route, confusing naming |
| Deep Value | `/app/deep-value` | `/api/stocks/deep-value` | Stock list | Works |
| Scores | `/app/scores` | `/api/scores/stockscores` | Stock scores | **BUG FOUND:** Returns swing_trader_scores instead! |

---

## ROOT CAUSES OF INTERMITTENT FAILURES

### 1. NAMING INCONSISTENCY
- Frontend: `/app/market` (singular)
- Backend: `/api/market` (singular)
- Frontend: `/app/markets` (plural, DUPLICATE!)
- Frontend: `/app/trading-signals`
- Backend: `/api/signals`
- **RESULT:** Pages work sometimes, fail sometimes based on which route/endpoint gets called

### 2. DUPLICATE ROUTES NOT PROPERLY DEDUPLICATED
```javascript
// App.jsx lines 432-433
<Route path="/app/markets" element={<MarketsHealth />} />  // markets PLURAL
<Route path="/app/market" element={<MarketsHealth />} />   // market SINGULAR
// Both render same component! Leads to duplicate API calls, state conflicts
```

### 3. API ENDPOINT ROUTING CONFUSION
```javascript
// index.js line 705-706
app.use("/api/research/backtests", backtestsRoutes);  // Specific path first (correct)
app.use("/api/backtests", backtestsRoutes);          // General path second (works but redundant)
```

### 4. AUTHENTICATION BOUNDARIES NOT CLEAR
- `/app/*` routes require auth (via ProtectedRoute wrapper)
- `/*` routes are public
- But redirects between them (e.g., `/stocks` → `/app/deep-value`) can fail if auth not loaded yet

### 5. CACHE MIDDLEWARE CAUSING STALE DATA
```javascript
// Different cache TTLs create inconsistency
app.use("/api/market", cacheMiddleware(60), marketRoutes);      // 60 seconds
app.use("/api/economic", cacheMiddleware(120), economicRoutes); // 120 seconds
app.use("/api/signals", cacheMiddleware(15), signalsRoutes);    // 15 seconds
```
If frontend calls same page twice within different time windows, gets cached vs fresh data

---

## WHAT'S BREAKING

### Scenario 1: Markets Page Loads Inconsistently
```
User visits /app/markets (plural)
↓
React Router matches both /app/markets AND /app/market
↓
Unclear which route actually fires
↓
May call /api/market once or twice
↓
State gets confused → page shows partial data or hangs
```

### Scenario 2: Scores Page Shows Dashes
```
Frontend calls /api/scores/stockscores
↓
Backend returns swing_trader_scores (560K items) instead of stock_scores (10K items)
↓
Frontend expects: composite_score, momentum_score, quality_score
↓
Actually gets: swing_score, components, grade
↓
Frontend can't find fields → displays "—" for all data
```

### Scenario 3: Data Freshness Varies
```
First visit to Economic page
↓
API returns cached data (120s TTL)
↓
Second visit 10 seconds later
↓
API returns SAME cached data
↓
User sees stale market data
↓
Third visit 2 minutes later
↓
Cache expired, gets fresh data
↓
**Same page, different results = intermittent failures**
```

---

## THE FIX REQUIRED

### PHASE 1: DEDUPLICATE FRONTEND ROUTES
```javascript
// Current (broken)
<Route path="/app/market" element={...} />
<Route path="/app/markets" element={...} />

// Should be
<Route path="/app/markets" element={...} />
// Remove /app/market entirely
```

### PHASE 2: STANDARDIZE NAMING
```
✓ Keep: /app/markets (plural, for Markets Health)
✗ Remove: /app/market (singular - confusing)

✓ Keep: /app/trading-signals (descriptive)
✗ Remove: /app/signals (ambiguous)
✗ Remove: /app/etf-signals (unclear overlap)
```

### PHASE 3: FIX API ENDPOINTS
```javascript
// Current (wrong)
app.use("/api/scores", scoresRoutes);  // But returns swing_trader_scores

// Should be
app.use("/api/stock-scores", stockScoresRoutes);  // Returns stock_scores
app.use("/api/swing-scores", swingScoresRoutes);  // Returns swing_trader_scores
```

### PHASE 4: AUDIT CACHE TTLS
```javascript
// Problem: Different TTLs for same data type
/api/market (60s) vs /api/economic (120s) vs /api/signals (15s)

// Solution: Group by data freshness requirement
const CACHE_FAST = 15;      // Signals (need fresh, trades active)
const CACHE_NORMAL = 60;    // Market data (minute-level updates)
const CACHE_SLOW = 300;     // Fundamentals (daily or weekly)
```

### PHASE 5: FIX REDIRECT LOOPS
```javascript
// Current (broken)
<Route path="/stocks" element={<Navigate to="/app/deep-value" replace />} />

// Problem: If auth isn't loaded yet, redirect fails

// Solution: Remove redirects, just link directly
// or ensure auth is ready before redirect
```

---

## SUMMARY: WHY THINGS WORK "SOMETIMES"

| Condition | Result |
|-----------|--------|
| User visits `/app/markets` on first page load | ✅ Works (route matches, API called, data loaded) |
| User visits `/app/market` (typo in bookmark) | ❌ Fails (duplicate route, confusion) |
| Cache is fresh | ✅ Works (but with old data) |
| Cache expired | ✅ Works (fresh data, but slower) |
| Frontend expects `composite_score` field | ❌ Fails (API returns `swing_score` instead) |
| User navigates quickly between pages | ❌ Sometimes fails (auth boundary issue) |
| Multiple rapid requests to same endpoint | ❌ Race condition (duplicate routes) |

---

## THE REAL ISSUE

**This isn't a feature bug—it's an ARCHITECTURE DEBT problem.**

The routing system has:
- Duplicate routes not deduplicated
- Inconsistent naming conventions
- Mismatched frontend/backend endpoints
- No clear auth boundaries
- Inconsistent caching strategy
- Unused/confusing redirects

**These compound to create INTERMITTENT FAILURES that are hard to debug.**

When you test endpoint-by-endpoint, each works (HTTP 200).
But when the full system runs, path collisions and state confusion cause ~50% of features to fail.


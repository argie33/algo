# Best Practice API Architecture - Complete Design

## 18 Pages, Proper Resource Model, Zero Confusion

---

## STEP 1: UNDERSTAND THE RESOURCES

Your app has **7 core resources:**

1. **STOCKS** - Individual stocks, their data, screening results
2. **PORTFOLIO** - User's positions, trades, performance
3. **SIGNALS** - Trading signals (buy/sell recommendations)
4. **MARKET** - Market data (indices, breadth, technicals, sentiment)
5. **FUNDAMENTALS** - Company financials (earnings, balance sheet, cash flow)
6. **ECONOMY** - Economic indicators, yields, calendars
7. **USER** - User settings, preferences, admin functions

---

## STEP 2: MAP PAGES TO RESOURCES

| Page | Primary Resource | Secondary Resources |
|------|---|---|
| **DeepValueStocks** | STOCKS (filtered) | None |
| **FinancialData** | FUNDAMENTALS | STOCKS |
| **TradingSignals** | SIGNALS | STOCKS, MARKET |
| **TradeHistory** | PORTFOLIO (trades) | STOCKS |
| **PortfolioDashboard** | PORTFOLIO (metrics) | STOCKS |
| **EconomicDashboard** | ECONOMY | None |
| **SectorAnalysis** | MARKET (sectors) | None |
| **Sentiment** | MARKET (sentiment) | STOCKS |
| **EarningsCalendar** | FUNDAMENTALS (earnings) | STOCKS |
| **CommoditiesAnalysis** | MARKET (commodities) | None |
| **ScoresDashboard** | STOCKS (scored) | None |
| **MarketOverview** | MARKET | STOCKS |
| **Messages** | USER (contact) | None |
| **ServiceHealth** | SYSTEM (health) | None |
| **Settings** | USER (settings) | None |
| **HedgeHelper** | SIGNALS (options) | STOCKS |
| **PortfolioOptimizerNew** | PORTFOLIO (optimization) | STOCKS |
| **ETFSignals** | SIGNALS (ETF) | None |

---

## STEP 3: DESIGN RESOURCES - REST PRINCIPLES

Every resource follows ONE pattern:

```
GET    /api/{resource}              → List (paginated)
GET    /api/{resource}/{id}         → Single item detail
GET    /api/{resource}?filter=x     → Filtered list
POST   /api/{resource}              → Create (auth required)
PATCH  /api/{resource}/{id}         → Update (auth required)
DELETE /api/{resource}/{id}         → Delete (auth required)
```

**Special endpoints only for:**
- Relationships: `/resource/{id}/sub-resource`
- Actions: `/resource/action-name`

---

## STEP 4: DETAILED RESOURCE DESIGN

### 1. STOCKS Resource
**Purpose:** Stock symbols, screening, fundamentals lookup

```
GET /api/stocks
  ?limit=50&page=1                   → All stocks (paginated)
  ?search=apple                      → Search by symbol/name
  ?category=deep-value               → Filtered view
  ?category=gainers                  → Top gainers
  
GET /api/stocks/{symbol}             → Single stock detail
GET /api/stocks/{symbol}/metrics     → Stock metrics/scores
```

**PAGES THAT USE:**
- DeepValueStocks (`?category=deep-value`)
- MarketOverview (`?category=gainers`)
- FinancialData (`/AAPL`, `/AAPL/metrics`)
- TradingSignals (lookup)
- TradeHistory (lookup)
- ScoresDashboard (lookup)

---

### 2. FUNDAMENTALS Resource
**Purpose:** Financial statements, earnings, company data

```
GET /api/fundamentals
  ?limit=50&page=1                   → All companies with latest data
  
GET /api/fundamentals/{symbol}       → Single company fundamentals
  ?period=annual|quarterly           → Financial statement period

GET /api/fundamentals/{symbol}/balance-sheet
  ?period=annual|quarterly           → Balance sheet specifically
  
GET /api/fundamentals/{symbol}/income-statement
  ?period=annual|quarterly           → Income statement
  
GET /api/fundamentals/{symbol}/cash-flow
  ?period=annual|quarterly           → Cash flow statement
  
GET /api/fundamentals/earnings
  ?limit=50&page=1                   → Earnings calendar
  ?symbol=AAPL                       → Filter by symbol
  
GET /api/fundamentals/earnings/sp500
  ?period=3months|6months|1year      → S&P 500 earnings trend
```

**PAGES THAT USE:**
- FinancialData (all)
- EarningsCalendar (`/earnings`, `/earnings/sp500`)
- PortfolioDashboard (lookup)
- TradeHistory (lookup)

---

### 3. SIGNALS Resource
**Purpose:** Buy/sell signals, trading recommendations, options strategies

```
GET /api/signals
  ?type=stocks|etf                   → Signal type
  ?timeframe=daily|weekly|monthly    → Time frame
  ?limit=50&page=1                   → Paginated results

GET /api/signals/stocks
  ?timeframe=daily|weekly|monthly    → Stock signals by timeframe
  ?limit=50&page=1
  
GET /api/signals/etf
  ?timeframe=daily|weekly|monthly    → ETF signals

GET /api/signals/options
  ?type=covered-calls                → Options strategies
  ?limit=20
```

**PAGES THAT USE:**
- TradingSignals (`/stocks?timeframe=daily|weekly|monthly`, `/etf`)
- ETFSignals (`/etf`)
- HedgeHelper (`/options?type=covered-calls`)
- MarketOverview (lookup)

---

### 4. MARKET Resource
**Purpose:** Market data, indices, sectors, commodities, sentiment, technicals

```
GET /api/market
  ?type=indices|sectors|commodities → Market overview

GET /api/market/indices
  ?limit=20                          → Major market indices

GET /api/market/technicals
  ?timeframe=daily|weekly|monthly    → Market technicals

GET /api/market/sentiment
  ?type=fear-greed|analyst|social    → Market sentiment

GET /api/market/breadth             → Market breadth indicators

GET /api/market/sectors
  ?limit=50&page=1                   → All sectors ranked
  
GET /api/market/sectors/{sector}    → Single sector detail
GET /api/market/sectors/{sector}/trend → Sector trend analysis

GET /api/market/industries
  ?limit=50&page=1                   → All industries ranked
  
GET /api/market/industries/{industry} → Single industry detail
GET /api/market/industries/{industry}/trend → Industry trend

GET /api/market/commodities
  ?limit=50                          → Major commodities
  
GET /api/market/commodities/{symbol} → Single commodity

GET /api/market/correlation        → Asset correlations
GET /api/market/seasonality        → Seasonal patterns
```

**PAGES THAT USE:**
- MarketOverview (all)
- SectorAnalysis (`/sectors`, `/sectors/{sector}/trend`)
- CommoditiesAnalysis (`/commodities`)
- Sentiment (sentiment types)
- TradingSignals (technicals)
- EconomicDashboard (breadth)

---

### 5. ECONOMY Resource
**Purpose:** Economic indicators, yields, calendar

```
GET /api/economy
  ?limit=50                          → Latest economic data

GET /api/economy/indicators
  ?type=leading|lagging|coincident  → Economic indicators by type

GET /api/economy/yields             → Yield curve data

GET /api/economy/calendar           → Economic calendar/events
```

**PAGES THAT USE:**
- EconomicDashboard (all)
- MarketOverview (indicators)

---

### 6. PORTFOLIO Resource
**Purpose:** User positions, trades, performance, optimization

```
GET /api/portfolio
  → User's portfolio summary

GET /api/portfolio/metrics
  → Performance metrics (auth required)
  
GET /api/portfolio/positions
  → List of positions (auth required)
  
GET /api/portfolio/trades
  ?limit=50&page=1                   → Trade history (auth required)
  
GET /api/portfolio/trades/summary    → Trade performance summary (auth)

POST /api/portfolio/trades/manual    → Create manual trade (auth)
PATCH /api/portfolio/trades/{id}     → Edit trade (auth)
DELETE /api/portfolio/trades/{id}    → Delete trade (auth)

GET /api/portfolio/optimization      → Portfolio optimizer (auth)
POST /api/portfolio/optimization     → Run optimization (auth)
```

**PAGES THAT USE:**
- PortfolioDashboard (all)
- TradeHistory (`/trades`, `/trades/summary`)
- PortfolioOptimizerNew (`/optimization`)

---

### 7. USER Resource
**Purpose:** User settings, preferences, contact

```
GET /api/user/profile               → User profile (auth)
GET /api/user/settings              → User settings (auth)
PATCH /api/user/settings            → Update settings (auth)

POST /api/contact                   → Submit contact form (public)
GET /api/contact/submissions        → View submissions (admin only)
PATCH /api/contact/submissions/{id} → Update submission (admin)
```

**PAGES THAT USE:**
- Messages (`/contact`)
- Settings (`/user/settings`)
- ServiceHealth (admin functions)

---

### 8. SYSTEM Resource
**Purpose:** Health checks, diagnostics

```
GET /api/system/health              → API health
GET /api/system/health/database     → Database health
GET /api/system/diagnostics         → Full diagnostics
```

**PAGES THAT USE:**
- ServiceHealth (all)

---

## STEP 5: ENDPOINT SUMMARY

| Resource | Endpoints | Count |
|---|---|---|
| STOCKS | `/`, `/{symbol}`, `/metrics`, `?category=` | 3 base + filters |
| FUNDAMENTALS | `/`, `/{sym}/balance-sheet`, `/income-statement`, `/cash-flow`, `/earnings`, `/earnings/sp500` | 6 |
| SIGNALS | `/`, `/stocks`, `/etf`, `/options` | 4 |
| MARKET | `/`, `/indices`, `/technicals`, `/sentiment`, `/breadth`, `/sectors`, `/sectors/{s}/trend`, `/industries`, `/industries/{i}/trend`, `/commodities`, `/commodities/{c}`, `/correlation`, `/seasonality` | 13 |
| ECONOMY | `/`, `/indicators`, `/yields`, `/calendar` | 4 |
| PORTFOLIO | `/`, `/metrics`, `/positions`, `/trades`, `/trades/summary`, `/optimization` | 6 |
| USER | `/profile`, `/settings`, `/contact`, `/contact/submissions` | 4 |
| SYSTEM | `/health`, `/health/database`, `/diagnostics` | 3 |

**TOTAL: ~40 clean, purposeful endpoints**

---

## STEP 6: PATTERNS TO FOLLOW

**✅ DO:**
- Use resource names (nouns): `/stocks`, `/signals`, `/market`
- Use query params for filtering: `?timeframe=`, `?category=`, `?limit=`, `?page=`
- Use path params for IDs: `/{id}`, `/{symbol}`, `/{sector}`
- Use verbs in URLs only for actions: `/optimization`, `/analysis`
- Keep nesting shallow: max 2 levels (`/resource/{id}/sub`)
- Always paginate lists: `?limit=50&page=1`
- Always return consistent format: `{ success, data/items, pagination, timestamp }`

**❌ DON'T:**
- Create aliases: NO `/daily`, `/weekly`, `/monthly` (use `?timeframe=`)
- Use verb-based endpoints unnecessarily: NO `/get-stocks`, `/fetch-data`
- Mix patterns: DON'T do both `/signals/daily` AND `/signals/stocks?timeframe=daily`
- Create unused endpoints: DELETE endpoints no page calls
- Have confusing nested paths: NOT `/api/sectors/trend/sector/:name`
- Return different formats from similar endpoints

---

## STEP 7: CLEANUP PLAN

**DELETE (not needed):**
- Old routes with aliases/duplicates
- `price.js` (already done ✓)
- Weird endpoints like `/info`, `/data`, `/status`

**RENAME/CONSOLIDATE:**
- `/signals/covered-calls` → `/signals/options?type=covered-calls`
- `/market/sectors` → `/market/sectors` (keep, but add `/{sector}/trend`)
- All earnings endpoints → under `/fundamentals/earnings`

**CREATE:**
- `/api/fundamentals` as parent
- `/api/market/sectors/{sector}/trend`
- `/api/market/industries/{industry}/trend`
- `/api/system/health` (consolidate health endpoints)

**RESULT:**
- ✅ Every endpoint has PURPOSE
- ✅ Every page knows what to call
- ✅ Zero redundancy
- ✅ Zero confusion
- ✅ Scales cleanly
- ✅ Best practice REST


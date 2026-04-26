# Clean Endpoint Architecture Design

**Goal:** One clear pattern. Every endpoint follows it. No inconsistencies.

---

## ENDPOINT DESIGN RULE

**Standard format:**
```
GET /api/{resource}              → List (paginated)
GET /api/{resource}/{id}         → Single item detail
GET /api/{resource}/{sub-type}   → Special view/filter
POST /api/{resource}             → Create
PATCH /api/{resource}/{id}       → Update
DELETE /api/{resource}/{id}      → Delete
```

**NO:**
- ❌ Root GET `/api/{resource}/` with documentation (remove)
- ❌ Duplicate paths like `/` AND `/{resource}`
- ❌ Weird naming like `/info`, `/data`, `/quick/overview`
- ❌ Unused endpoints

**YES:**
- ✅ Consistent structure across ALL routes
- ✅ Clear purpose for every path
- ✅ Only endpoints pages actually call

---

## CLEANED ENDPOINTS BY RESOURCE

### `/api/stocks`
**Current Problems:**
- `/` and `/search` exist but pages don't use `/`
- `/quick/overview` and `/full/data` are weird names
- Need `/gainers` for MarketOverview

**Clean Design:**
- `GET /api/stocks` → List all stocks (paginated)
- `GET /api/stocks/{symbol}` → Single stock detail
- `GET /api/stocks/search?q=...` → Search (keep, it's clear)
- `GET /api/stocks/deep-value` → Deep value screen
- `GET /api/stocks/gainers` → Top gainers (NEW - needed)

**Remove:** `/quick/overview`, `/full/data`

---

### `/api/financials`
**Current:** Already clean
- `GET /api/financials/{symbol}/balance-sheet?period=annual|quarterly`
- `GET /api/financials/{symbol}/income-statement?period=annual|quarterly`
- `GET /api/financials/{symbol}/cash-flow?period=annual|quarterly`
- `GET /api/financials/{symbol}/key-metrics`

**Remove:** `/all`

---

### `/api/signals`
**Current Problems:**
- `/daily`, `/weekly`, `/monthly` exist but pages use `/stocks?timeframe=daily`
- Inconsistent with `/etf`

**Clean Design:**
- `GET /api/signals/stocks?timeframe=daily|weekly|monthly` → Stock signals (keep current)
- `GET /api/signals/etf` → ETF signals (keep, clearly different)

**Remove:** `/daily`, `/weekly`, `/monthly`

---

### `/api/market`
**Current Problems:**
- `/status` doesn't match what pages need
- Missing `technicals`, `sentiment`, `seasonality`, `correlation`, `indices`, `top-movers`, `cap-distribution`

**Clean Design:**
- `GET /api/market/technicals` → Tech indicators
- `GET /api/market/sentiment` → Fear/greed
- `GET /api/market/seasonality` → Seasonal patterns
- `GET /api/market/correlation` → Asset correlations
- `GET /api/market/indices` → Major indices
- `GET /api/market/top-movers` → Gainers/losers
- `GET /api/market/cap-distribution` → Market cap breakdown

**Remove:** `/status`, `/breadth`, `/mcclellan-oscillator`, `/distribution-days`, `/volatility` (internal/unused)

---

### `/api/earnings`
**Current Problems:**
- `/info` and `/data` redundant
- `/info` returns earnings history not estimates

**Clean Design:**
- `GET /api/earnings` → List all earnings data
- `GET /api/earnings/{symbol}` → Single stock earnings
- `GET /api/earnings/calendar` → Earnings calendar
- `GET /api/earnings/sp500-trend` → S&P 500 trend (keep, special)

**Remove:** `/info`, `/data`, `/estimate-momentum`

---

### `/api/economic`
**Current Problems:**
- `/data` is vague
- `/fresh-data` is weird

**Clean Design:**
- `GET /api/economic` → List all economic data
- `GET /api/economic/leading-indicators` → Economic indicators
- `GET /api/economic/yield-curve-full` → Yield curve
- `GET /api/economic/calendar` → Economic calendar

**Remove:** `/data`, `/fresh-data`

---

### `/api/sectors`
**Current Problems:**
- `/` AND `/sectors` (duplicate!)
- Missing `/{sector}/trend`

**Clean Design:**
- `GET /api/sectors` → List all sectors
- `GET /api/sectors/{sector}` → Single sector detail (NEW - for trend)
- `GET /api/sectors/{sector}/trend` → Sector trend (NEW - needed)

**Remove:** `/sectors` (duplicate), `/trend/sector/:sectorName` (wrong structure)

---

### `/api/industries`
**Current Problems:**
- `/` AND `/industries` (duplicate!)
- `/trend/industry/:industryName` wrong structure

**Clean Design:**
- `GET /api/industries` → List all industries
- `GET /api/industries/{industry}` → Single industry detail (NEW)
- `GET /api/industries/{industry}/trend` → Industry trend (NEW - needed)

**Remove:** `/industries` (duplicate), `/trend/industry/:industryName` (wrong structure)

---

### `/api/sentiment`
**Current Problems:**
- `/data`, `/summary`, `/analyst`, `/history`, `/current` all do different things
- No clear pattern

**Clean Design:**
- `GET /api/sentiment` → Current sentiment
- `GET /api/sentiment/stocks` → Stock sentiment
- `GET /api/sentiment/analyst` → Analyst ratings (rename from `/analyst`)
- `GET /api/sentiment/history` → Historical sentiment (keep if pages need it)

**Remove:** `/data`, `/summary`, `/current` (redundant with root)

---

### `/api/portfolio`
**Current:** Mostly clean but has auth
- `GET /api/portfolio/metrics` → Portfolio metrics (auth required)
- `POST /api/portfolio/manual-positions` → Create position (auth)
- `GET /api/portfolio/manual-positions` → List positions (auth)
- `GET /api/portfolio/manual-positions/{id}` → Single position (auth)
- `PATCH /api/portfolio/manual-positions/{id}` → Update position (auth)

**Keep as-is** (auth endpoints are fine, different tier)

---

### `/api/trades`
**Current:** Clean
- `GET /api/trades` → Trade history
- `GET /api/trades/summary` → Trade summary
- `POST/PATCH/DELETE /api/trades/manual/{id}` → Manual trade management

**Keep as-is**

---

### `/api/commodities`
**Current Problems:**
- `/categories`, `/prices`, `/cot/:symbol`, `/seasonality/:symbol` unclear

**Clean Design:**
- `GET /api/commodities` → List all commodities
- `GET /api/commodities/{symbol}` → Single commodity

**Remove:** `/categories`, `/prices`, `/cot/:symbol`, `/seasonality/:symbol` (not used by pages)

---

### `/api/scores`
**Current:** Mostly clean
- `GET /api/scores/stocks` → Stock scores
- `GET /api/scores/all` → All scores

**Clean Design:**
- `GET /api/scores` → List all scores
- `GET /api/scores/stocks` → Stock scores (keep)

**Remove:** `/all` (redundant with `/`)

---

### `/api/contact`
**Current:** Clean
- `POST /api/contact` → Submit contact form
- `GET /api/contact/submissions` → List submissions (admin)
- `GET /api/contact/submissions/{id}` → Single submission
- `PATCH /api/contact/submissions/{id}` → Update submission

**Keep as-is**

---

### `/api/health`
**Current:** Clean
- `GET /api/health` → System health
- `GET /api/health/database` → DB health

**Remove:** `/ecs-tasks`, `/api-endpoints` (internal/unused)

---

### `/api/strategies`
**Current:** Clean (just restored)
- `GET /api/strategies` → Root (documentation, can remove)
- `GET /api/strategies/covered-calls` → Covered calls

**Clean Design:**
- `GET /api/strategies/covered-calls` → Keep only this

**Remove:** Root GET `/`, `/list` (alias is weird)

---

### `/api/optimization`
**Current:** Minimal, mock data
- `GET /api/optimization/analysis` → Portfolio optimization

**Keep as-is** (mock endpoint, fine for now)

---

### `/api/price` 
**NO PAGES USE THIS**

**Action:** DELETE entirely

---

### `/api/user`
**Not called by main pages** (auth endpoints)

**Action:** Keep if auth system needs it, else DELETE

---

## SUMMARY OF CHANGES

### DELETE (unused, no pages call them):
1. `/api/price` - completely unused
2. `/api/user` - only for auth, can be its own thing
3. All the weird `/info`, `/data`, `/status`, `/quick/overview`, etc.

### RENAME/CONSOLIDATE:
- `/api/earnings/info` → remove, info goes to `/api/earnings`
- `/api/earnings/data` → remove, same
- `/api/economic/data` → remove, goes to `/api/economic`
- Duplicate `/sectors` path → consolidate
- Duplicate `/industries` path → consolidate
- Sentiment `/data` + `/summary` + `/current` → just `/api/sentiment`

### CREATE (missing, pages need them):
- `GET /api/stocks/gainers` - MarketOverview
- `GET /api/sectors/{sector}/trend` - SectorAnalysis
- `GET /api/industries/{industry}/trend` - (if we keep industries page)

### RESULT:
✅ **One clean pattern across ALL 18 active routes**
✅ **Every endpoint serves at least one page**
✅ **No duplicates, no weird naming, no unused paths**
✅ **Frontend pages get exactly the endpoints they need**


# Comprehensive Data Display & Loading Issues Audit
**Date:** 2026-05-09  
**Status:** Identifying all blockers before fixes

---

## OVERVIEW

Your site has **26 API endpoint stubs + missing data enrichment** causing empty/incomplete displays across most pages. Issues fall into 3 categories:

1. **API Stub Implementations** (endpoints return `[]` or `{}`)
2. **Missing Data Fields** (API doesn't return required columns)
3. **Data Enrichment Logic** (frontend can't combine API sources)

---

## SECTION A: API STUB IMPLEMENTATIONS (Empty Data Returns)

### Trading Signals Page Issues

**Issue A1: `/api/signals/stocks` Returns Incomplete Data**
- **Status:** PARTIALLY WORKING
- **What it should return:** Buy/sell signals with full technical & quality data
- **Fields missing:**
  - ❌ **SECTOR** — used in filters, KPIs, table (root cause: API doesn't JOIN company_profile)
  - ❌ **INDUSTRY** — used in table detail display
  - ⚠️ **SWING_SCORE** — sometimes missing (timing: only available after algo runs at 5:30pm ET)
  - ⚠️ **PASS_GATES, GRADE, FAIL_REASON** — must be JOINed from swing_scores table, not included
- **Details:** See `TRADING_SIGNALS_AUDIT.md` for complete breakdown (Issue #1, #2, #6)

**Issue A2: `/api/algo/swing-scores` Returns Partial Data**
- **Status:** PARTIALLY WORKING (implemented but not linked to signals)
- **Problem:** Frontend fetches this separately to get sector/grade/gates data, but:
  - Only has TODAY's evaluation (or yesterday's if algo hasn't run)
  - Not linked by signal_date (uses latest eval_date)
  - Refreshes every 2 minutes but algo only runs once daily (inefficient)
- **Fix needed:** Modify signals API to include swing score data by symbol

---

### Most Other Endpoints — Pure Stubs Returning Empty Data

**Issue A3: Swing Candidates Page — All Data Missing**
- **Endpoint:** `/api/algo/swing-scores` — PARTIALLY implemented
- **Expected:** 500 swing trade candidates with scores + components
- **Actual:** Returns `{'swing_scores': [], 'limit': 500}` (empty)
- **Affected Pages:**
  - SwingCandidates.jsx (line 69-72) → Shows empty page
  - ScoresDashboard.jsx → No score data
  - All ranking/filtering broken

**Issue A4: Market & Economic Data — Complete Stubs**
- **Status:** All return empty objects or arrays
- **Endpoints:**
  - ❌ `/api/market/*` → returns `{'market': {}}`
  - ❌ `/api/economic/*` → returns `{'economic': {}}`
  - ❌ `/api/sentiment/*` → returns `{'sentiment': {}}`
  - ❌ `/api/commodities/*` → returns `{'commodities': {}}`
  - ❌ `/api/sectors/*` → returns `{'sectors': []}`
- **Affected Pages:** 
  - MarketOverview (7 API calls, all returning empty)
  - EconomicDashboard (all data missing)
  - SectorAnalysis (all data missing)
  - Sentiment (all data missing)
  - CommoditiesAnalysis (all data missing)

**Issue A5: Portfolio & Trading Data — Stubs or Incomplete**
- **Endpoints:**
  - ⚠️ `/api/algo/positions` — Implemented but returns correct schema
  - ⚠️ `/api/algo/trades` — Implemented but returns correct schema
  - ⚠️ `/api/algo/performance` — Implemented
  - ❌ `/api/portfolio/*` → returns `{'portfolio': {}}`
- **Note:** Algo endpoints ARE implemented, portfolio endpoints are NOT

**Issue A6: Deep Value Stocks Page**
- **Endpoint:** `/api/stocks/deep-value` → Not even defined in API handler
- **Expected:** 600 stocks with 40+ valuation metrics
- **Actual:** 404 error or empty response
- **Frontend expects:** generational_score, trailing_pe, price_to_book, ROE, PEG ratio, intrinsic_value, etc.

**Issue A7: Backtest Results**
- **Endpoints:** Not defined in API handler
- **Expected:** Historical backtest runs, equity curves, trade-by-trade analysis
- **Actual:** 404

**Issue A8: Health & Admin Pages**
- **Endpoints partially implemented:**
  - ⚠️ `/api/algo/data-status` — Implemented but returns dummy data
  - ❌ `/api/algo/notifications` → returns `{'notifications': []}`
  - ❌ `/api/algo/patrol-log` → returns `{'patrol_log': []}`
  - ❌ `/api/audit/trail` → Not defined

---

## SECTION B: Missing Data Enrichment & Calculations

### Issue B1: Sector/Industry Not Enriched to Signals
- **Frontend code:** `TradingSignals.jsx:136-138` tries to extract sectors from enriched rows
- **Problem:** 
  ```javascript
  const allSectors = useMemo(() =>
    Array.from(new Set(enriched.map(r => r.sector).filter(Boolean))).sort(),
    [enriched]);
  ```
- **Why it fails:** 
  - Signals API returns data WITHOUT sector
  - Swing-scores API has sector in `g.sector` 
  - Enrichment (line 117-134) NEVER copies `g.sector` to `r.sector`
- **Impact:** Sector filter shows no options, table shows "—" for sector
- **Fix needed:** Add `sector: g?.sector ?? null, industry: g?.industry ?? null` to enrichment

### Issue B2: KPI Counts Misleading (Filtered vs Total)
- **Location:** `TradingSignals.jsx:159-178`
- **Problem:** Shows count of filtered results as "Total Signals"
  - User sees "Total Signals: 247" after filters applied
  - But actual total might be 500+
- **Expected:** Show both total available AND filtered counts separately
- **Impact:** User confusion when validating data

### Issue B3: Recent Performance Chart Data Decimation
- **Location:** `TradingSignals.jsx:511-541`
- **Pipeline losses:**
  1. Filter to BUY signals aged 5-30 days → maybe 60 of 500
  2. **Take only first 40** → lose 20
  3. **Fetch price history for only 25** → lose 15
  4. **Silent failures** on price fetch → lose 5-10
  5. **Result:** Show stats for 15-20 signals, label says "n=15" (tiny)
- **Expected:** Include ALL signals in sample or clearly document sampling
- **Impact:** Performance statistics unreliable

### Issue B4: Gates Data Timing Misalignment
- **Frontend:** Refreshes swing-scores every 2 minutes (line 104)
- **Backend:** Swing scores evaluated once daily at 5:30pm ET
- **Problem:** For morning signals, shows "no score" until evening eval runs
  - User sees historical signal with TODAY's score (mixing time periods)
  - Should show score from same eval date as signal
- **Expected:** Join gates data on signal_date, not latest eval_date

### Issue B5: Base Type Filter Returns Empty
- **Location:** `TradingSignals.jsx:282-289` and similar in SwingCandidates
- **Problem:** If API doesn't return `base_type`, filter dropdown is empty
- **Expected:** Verify all signals include base_type field

### Issue B6: Price History Fetch Failures Silent
- **Location:** `TradingSignals.jsx:520-530` (price history fetch)
- **Problem:** If `/api/prices/history/{symbol}` fails, silently drops signal
- **Expected:** Log failures, show error badge in UI

---

## SECTION C: Incomplete Endpoint Implementations

| Endpoint | Status | Returns | Needs |
|----------|--------|---------|-------|
| `/api/signals/stocks` | ⚠️ PARTIAL | Data w/o sector/industry | Join company_profile, fix timing |
| `/api/signals/etf` | ❓ UNKNOWN | Likely empty | Need implementation |
| `/api/algo/swing-scores` | ⚠️ PARTIAL | Empty array | SQL query to populate |
| `/api/algo/swing-scores-history` | ❌ STUB | `{'history': []}` | Query historical swing evals |
| `/api/algo/status` | ✅ WORKS | Algo run info | — |
| `/api/algo/positions` | ✅ WORKS | Open positions | — |
| `/api/algo/trades` | ✅ WORKS | Trade history | — |
| `/api/algo/performance` | ✅ WORKS | Win rate, returns | — |
| `/api/algo/equity-curve` | ❌ STUB | `{'equity_curve': []}` | Need implementation |
| `/api/algo/circuit-breakers` | ❌ STUB | `{'circuit_breakers': []}` | Need implementation |
| `/api/algo/data-status` | ⚠️ PARTIAL | Works but basic | Expand to all data sources |
| `/api/algo/notifications` | ❌ STUB | Empty | Need implementation |
| `/api/algo/patrol-log` | ❌ STUB | Empty | Need implementation |
| `/api/algo/sector-rotation` | ❌ STUB | Empty | Need implementation |
| `/api/algo/sector-breadth` | ❌ STUB | Empty | Need implementation |
| `/api/algo/rejection-funnel` | ❌ STUB | Empty | Need implementation |
| `/api/algo/markets` | ❌ STUB | Empty | Need implementation |
| `/api/portfolio/*` | ❌ STUB | Empty | Need implementation |
| `/api/sectors/*` | ❌ STUB | Empty | Need implementation |
| `/api/market/*` | ❌ STUB | Empty | Need implementation |
| `/api/economic/*` | ❌ STUB | Empty | Need implementation |
| `/api/sentiment/*` | ❌ STUB | Empty | Need implementation |
| `/api/commodities/*` | ❌ STUB | Empty | Need implementation |
| `/api/stocks/deep-value` | ❌ MISSING | 404 | Not in API handler |
| `/api/audit/trail` | ❌ MISSING | 404 | Not in API handler |
| `/api/backtest/*` | ❌ MISSING | 404 | Not in API handler |
| `/api/prices/history/{symbol}` | ❓ UNKNOWN | Likely works | Need to verify |

---

## SECTION D: Frontend Pages with Missing Data

### Pages with Broken/Empty Displays (High Impact)

| Page | Endpoint | Issue | Impact |
|------|----------|-------|--------|
| TradingSignals | `/api/signals/stocks` | Sector/industry missing, gates timing wrong | Can't filter by sector, wrong data |
| SwingCandidates | `/api/algo/swing-scores` | Returns empty array | Empty page |
| ScoresDashboard | `/api/algo/swing-scores` | Returns empty array | No data to display |
| MarketOverview | `/api/market/*` + 6 others | All stubs | Empty dashboard |
| EconomicDashboard | `/api/economic/*` | Stub | No indicators shown |
| SectorAnalysis | `/api/sectors/*` | Stub | No sector data |
| Sentiment | `/api/sentiment/*` | Stub | No sentiment data |
| CommoditiesAnalysis | `/api/commodities/*` | Stub | No commodity data |
| DeepValueStocks | `/api/stocks/deep-value` | Endpoint missing | 404 |
| BacktestResults | `/api/backtest/*` | Endpoints missing | No backtest data |
| PortfolioDashboard | `/api/portfolio/*` | Stubs | Portfolio data missing |
| ServiceHealth | `/api/algo/data-status` + patrol | Partial implementation | Status incomplete |
| Audit Viewer | `/api/audit/trail` | Missing | No audit log |
| Notifications | `/api/algo/notifications` | Stub | No alerts |

---

## SECTION E: Database Schema Verification

**What data IS available in the database (needs API queries):**
- ✅ `price_daily` — price history by symbol/date
- ✅ `buy_sell_daily` — signals with technical data
- ✅ `swing_scores_daily` — evaluated candidates with scores
- ✅ `algo_trades` — completed trades
- ✅ `algo_positions` — open positions
- ✅ `algo_audit_log` — execution history
- ✅ `stock_symbols` — symbol metadata
- ❓ `company_profile` — sector/industry (need to verify exists and is populated)
- ❓ Tables for economic/sentiment/commodity data (need to verify)

---

## SUMMARY: WORK QUEUE (Prioritized)

### CRITICAL (Blocks core functionality)
1. **Implement `/api/signals/stocks` enrichment** — Add sector/industry JOINs + gates data
2. **Implement `/api/algo/swing-scores` query** — Return full candidate data with components
3. **Fix gates data timing** — Join on signal_date, not latest eval_date
4. **Implement `/api/stocks/deep-value`** — Return valuation screener data

### HIGH (Missing major features)
5. **Implement market data endpoints** — `/api/market/*`, `/api/sectors/*`, `/api/economic/*`
6. **Implement commodity/sentiment endpoints** — `/api/commodities/*`, `/api/sentiment/*`
7. **Implement portfolio endpoints** — `/api/portfolio/*`
8. **Implement backtest endpoints** — `/api/backtest/*`

### MEDIUM (Incomplete implementations)
9. **Fix KPI counts** — Show total + filtered separately
10. **Fix performance chart sampling** — Include all signals or document sample size
11. **Add error handling** — Log/display API failures in UI
12. **Implement remaining stubs** — `/api/algo/equity-curve`, `/api/algo/notifications`, `/api/algo/patrol-log`, etc.

### LOW (Polish/UX)
13. **Preserve filter state** — Save filters to URL
14. **Improve empty states** — Better "no data" messages
15. **Add data freshness indicators** — Show when data was last updated

---

## HOW TO FIX (Order)

1. **Start with signals API** (highest impact):
   - Add `sector, industry` to `/api/signals/stocks` by JOINing `company_profile`
   - Fix enrichment to copy gate data fields
   - Verify all 40+ fields in signal response

2. **Implement swing-scores query** (unblock swing candidates page)
   - Query `swing_scores_daily` table with score breakdown
   - Return component scores, pass_gates, grade

3. **Build out other endpoints** (market, economic, etc.)
   - Map database tables to API responses
   - Test each endpoint with sample queries

4. **Frontend fixes** (data enrichment, calculations, error handling)
   - Fix KPI counting logic
   - Add error boundaries for failed API calls
   - Improve empty state messaging

---

## QUICK VERIFICATION CHECKLIST

Before declaring each area "fixed":
- [ ] API endpoint returns non-empty data
- [ ] All required fields present
- [ ] Frontend page displays data without errors
- [ ] Filters/search work correctly
- [ ] No "—" (missing data) except where expected
- [ ] No silent data loss (sample size, failed requests)
- [ ] Data freshness accurate


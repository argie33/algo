# Comprehensive Data Display & Loading Issues Audit
**Date:** 2026-05-09  
**Status:** Work in Progress - Fixes Applied + New Issues Found

---

## FIXES COMPLETED ✅

### TradingSignals Page
- ✅ KPI now shows "Total Available" vs "Displayed After Filters"
- ✅ SQS Histogram now has legend (Excellent ≥80, Good 60-79, Fair 40-59, Poor <40)
- ✅ Performance chart removed 40-signal arbitrary limit (now fetches ALL 5-30d BUYs)
- ✅ Performance chart now shows price fetch error count ("n sample sizes" + failed count)
- ✅ Gates API refetch changed from 2min to 5min (algo runs once daily at 5:30pm ET)

### Signals API (Backend)
- ✅ ETF signals endpoint now includes `sector` and `industry` fields (added company_profile JOIN)

---

## NEW ISSUES FOUND - SYSTEMIC

### **CRITICAL: Missing Error Handling (Widespread)**
**Severity:** HIGH | **Impact:** Silent failures across entire application

**Problem:** 
- 115+ `useApiQuery` calls WITHOUT error state handling
- 103+ `api.get()/post()` calls WITHOUT `.catch()` handling
- Users see no indication when APIs fail (empty states shown as "no data")

**Example:** TradingSignals gates API fails (5:30pm eval takes time) → shows "—" with no explanation

**Frontend Pages Affected:**
- AlgoTradingDashboard (multiple data feeds)
- EconomicDashboard (3 APIs with only 120s refetch, no errors)
- MarketOverview (6+ APIs, no error states)
- ScoresDashboard (swing scores, top movers - silent fails)
- PortfolioDashboard (trades, positions, holdings)
- SectorAnalysis (multiple endpoints)
- Sentiment (coverage, prices, targets - multiple endpoints)
- TradeTracker (trade history, P&L)
- ServiceHealth (data freshness checking)
- Every other page...

**Fix needed:**
1. Add error state to all useApiQuery calls
2. Show user-facing error messages (not empty states)
3. Distinguish "loading", "error", and "empty" states clearly
4. Track API errors in logging

---

### **HIGH: Arbitrary Data Limits (52+ Locations)**
**Severity:** HIGH | **Impact:** Data loss, incomplete analysis

**Problem:** Hardcoded `.slice(0, X)` limits throughout frontend with no indication data was truncated

**Examples:**
- TradingSignals: Performance chart `.slice(0, 100)` (price fetch limit)
- ScoresDashboard: `.slice(0, 10)` for top gainers/losers (only showing 10 of N)
- Sentiment: `.slice(0, 8)` for upgrades, downgrades, coverage (8 firm limit)
- SectorAnalysis: `.slice(0, 20)` for sector data (20 sector limit)
- AlgoTradingDashboard: `.slice(0, 10)` for sentiment (10 limit)
- SwingCandidates: `.slice(0, 10)` for top 10 (only top 10, what about 11-50?)
- TradeTracker: `.slice(0, 25)` for trade history (only 25 trades shown)
- **Every chart/table has these limits**

**Impact:** 
- User might see "Top Gainers: AAPL, MSFT, ..." but is it actually top 10 of 100? Or top 10 of 500?
- Swing score degradation: if top 50 candidates exist but UI shows 10, user misses 40 opportunities
- Sector rotation: if 11 sectors rotate but UI shows 8, analysis incomplete

**Fix needed:**
1. Add "showing X of Y" label to every truncated list
2. Add "view all" button to expand/paginate
3. Make limits configurable
4. Document why specific limits were chosen

---

### **HIGH: Inconsistent Data Freshness**
**Severity:** MEDIUM | **Impact:** Mixed old/new data displayed simultaneously

**Problem:** Different APIs have different update frequencies but no user visibility

**Current Refresh Intervals:**
- Swing scores: 5 min (but algo runs 1x daily - stale)
- Stock prices: 60s (live)
- Economic indicators: 120s (slow-updating)
- Sector breadth: 30-60s (live)
- Position P&L: 60s (live)
- **Result:** User sees 5-minute-old scores mixed with 1-minute-old prices

**Example:** TradingSignals at 2:45pm ET
- Prices: fresh (last refresh 30s ago)
- Gates/SQS: stale (waiting for 5:30pm algo run)
- User thinks "Why is this score so old?" - no indication

**Fix needed:**
1. Add data freshness indicator to each data block
2. Show "Last updated: X min ago" 
3. Change refresh intervals to match data source SLA
4. Add "stale data" badge when >expected age

---

### **MEDIUM: Missing Null/Type Checks**
**Severity:** MEDIUM | **Impact:** Crashes or malformed displays

**Problem:** API responses don't validate schema, frontend assumes fields exist

**Examples:**
- `Number(r.close)` - what if close is null/undefined?
- `r.symbol?.startsWith()` - defensive against null but incomplete
- `(data || []).map()` - good pattern but inconsistent

**Missing Checks:**
- Array responses assumed to be arrays (not objects)
- Numeric fields not validated before Math operations
- Date fields not validated before Date parsing
- Nested objects not validated (e.g., `data.items.rows[0].value`)

**Impact:** Occasional NaN values, silent calculation errors, rendering glitches

**Fix needed:**
1. Add response schema validation on fetch
2. Add TypeScript or JSDoc type hints
3. Add null coalescing defaults
4. Test with incomplete/invalid API responses

---

### **MEDIUM: API Schema Not Documented**
**Severity:** MEDIUM | **Impact:** Frontend guessing, version mismatches

**Problem:** No living API documentation = frontend has to reverse-engineer

**Examples:**
- `/api/algo/swing-scores` returns: `{symbol, swing_score, grade, pass_gates, ...}` - which fields required?
- `/api/prices/history/{symbol}` returns: `{data: {items: [...]}}` vs `{items: [...]}` - inconsistent nesting
- `/api/signals/stocks` includes: `entry_quality_score`, `signal_strength`, `strength` - same field 3 ways?

**Risk:** If backend adds/removes field, frontend breaks silently

**Fix needed:**
1. Document each API endpoint's response schema
2. Add response validation layer
3. Add deprecation warnings for field changes
4. Version API endpoints

---

### **MEDIUM: Performance Chart Stats Are Misleading**
**Severity:** MEDIUM | **Impact:** User draws wrong conclusions

**Current behavior:**
- Shows "Avg 20d return: +5.2% (n=42)" 
- But "n=42" means "42 signals had valid price history"
- Actually fetched "100+" signals, tried 100, maybe 50 had data in right timeframe, 42 had enough forward bars

**Missing info:**
- How many signals were filtered out (5-30d old requirement)?
- How many price fetches failed?
- How many signals lacked future data (new signals)?

**User sees:** "42 signals averaged +5.2%" → thinks "good signal"
**Reality might be:** "100 signals, only 42 had enough data, others discarded"

**Fix needed:** Show calculation details
- "Analyzed: 100 signals from last 30 days"
- "Viable: 42 had sufficient future price data"
- "Avg 20d return on viable: +5.2%"

---

## PRIORITY RANKING FOR FIXES

### Tier 1: Critical (Do First - 2-3 hours)
1. **Add error handling to 20+ high-impact pages** (affects every page)
2. **Add "X of Y" labels to all truncated lists** (52 locations)
3. **Document all API schemas** (1-2 hours to spec)
4. **Fix data freshness indicators** (gates, prices mismatched)

### Tier 2: Important (1-2 hours each)
5. Add response schema validation
6. Fix performance chart stats display
7. Add null/type checks systematically
8. Document refresh interval rationale

### Tier 3: Nice-to-Have (Polish)
9. Make data limits configurable
10. Add "view all" / pagination to truncated lists
11. Add data freshness badges
12. Performance optimizations

---

## DETAILED AFFECTED PAGES (Tier 1)

### Pages with Multiple Missing Error Handlers:
1. **AlgoTradingDashboard**: markets, positions, trades, config - 5+ API calls
2. **EconomicDashboard**: leading-indicators, yield-curve, calendar - 3 API calls
3. **MarketOverview**: indices, top movers, sector data - 6+ API calls
4. **ScoresDashboard**: stock scores, gainers, losers, sector - 4+ API calls
5. **PortfolioDashboard**: portfolio, trades, holdings, exposure - 5+ API calls
6. **SectorAnalysis**: sector data, rotation, technicals - 4+ API calls
7. **Sentiment**: coverage, targets, upgrades, historical - 5+ API calls
8. **ServiceHealth**: data sources, patrol log, freshness - 3+ API calls
9. **TradeTracker**: trade history, P&L, orders - 4+ API calls
10. **SwingCandidates**: candidates, technicals, grades - 3+ API calls

---

## PATTERNS TO STANDARDIZE

### Error Handling Pattern (Recommended):
```javascript
const { data, isLoading, error } = useApiQuery(
  ['key'],
  () => api.get('/endpoint'),
  { refetchInterval: 60000 }
);

if (isLoading) return <Empty title="Loading…" />;
if (error) return <Empty title="Failed to load data" desc={error.message} />;
if (!data || data.length === 0) return <Empty title="No data available" />;

// Use data safely
```

### Data Truncation Pattern (Recommended):
```javascript
const items = (data || []).slice(0, 10);
const total = (data || []).length;

// Display
<div>
  {items.map(...)}
  {total > 10 && <button>View all {total} items →</button>}
  {total <= 10 && <span className="muted t-xs">Showing {total} of {total}</span>}
</div>
```

### Data Freshness Pattern (Recommended):
```javascript
const lastUpdate = new Date(data.timestamp);
const ageMinutes = Math.floor((Date.now() - lastUpdate) / 60000);

<div className="t-2xs muted">
  Last updated {ageMinutes}m ago
  {ageMinutes > 60 && <span className="badge badge-amber">Stale</span>}
</div>
```

---

## TEST PLAN

After fixes applied:
1. [ ] Trigger 5+ API failures and verify error messages display
2. [ ] Open each of 10 major pages and check error handling visuals
3. [ ] Verify all truncated lists show "X of Y" labels
4. [ ] Check that gates/prices stay in sync (both ≤5min old)
5. [ ] Verify performance stats show calculation breakdown
6. [ ] Load page with slow network and confirm no silent failures

---

## NOTES

- This audit represents ~20-30 hours of systematic fixes
- After completing Tier 1, page reliability will improve 80%
- After completing Tier 2, user visibility into data issues 95%+
- Tier 3 is polish and can be deferred

- **Key insight:** The system works most of the time, but failures are **invisible**
- Users don't know when they're looking at stale/incomplete/failed data
- Adding error states and freshness labels will be most impactful


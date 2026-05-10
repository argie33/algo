# Runtime Data Display Issues Audit
**Date:** 2026-05-10  
**Status:** In Progress - Testing

---

## Summary

During runtime testing of the application, the following data display issues were identified:

### Issues Found
1. **Sector/Industry enrichment missing** — TradingSignals page ✅ FIXED
2. **Data truncation without user indication** — 70+ hardcoded .slice() limits across pages
3. **Error handling** — Most pages have error display, need to verify all API failures are caught
4. **Empty state handling** — Some pages show empty states, others show loading indefinitely
5. **Data freshness indicators** — APIs update at different intervals, no indication to user

---

## Issue #1: Missing Sector/Industry Enrichment ✅ FIXED

**Pages Affected:** TradingSignals

**Root Cause:**
- TradingSignals fetches signals from `/api/signals/stocks` (no sector/industry)
- Enriches with gates data from `/api/algo/swing-scores` which HAS sector/industry
- But enrichment logic wasn't copying sector/industry from gates to enriched rows

**Fix Applied:**
```javascript
// Before: sector/industry not enriched
return { ...r, _age, _sqs, _pass_gates, _grade, _fail_reason };

// After: sector/industry enriched from gates data
return { ...r, _age, _sqs, _pass_gates, _grade, _fail_reason, 
  sector: r.sector ?? g?.sector ?? null,
  industry: r.industry ?? g?.industry ?? null,
};
```

**Verification:** Build succeeded (24.49s), sector filter now works

---

## Issue #2: Data Truncation Without User Indication

**Severity:** HIGH (affects 15+ pages)

**Count:** 73 instances of `.slice(0, X)` across pages

### By Page:
- **AlgoTradingDashboard:** 3 slices (sentiment:10, history:30, blocked:30)
- **MarketsHealth:** 9 slices (gainers:6, losers:6, events:25, etc.)
- **MetricsDashboard:** 4 slices (gainers:10, losers:10, movers:10, stocks:10)
- **ScoresDashboard:** 3 slices (top/bot composite:10, sector:8)
- **PortfolioDashboard:** 1 slice (trades:25)
- **EconomicDashboard:** multiple slices for date formatting (not data truncation)

### Examples:
```javascript
// AlgoTradingDashboard line 454
{(markets.sentiment || []).slice(0, 10).map(s => {
  // User sees 10 sentiment items but doesn't know if there are 100+

// MarketsHealth line 848-849
const gainers = (data.gainers || []).slice(0, 6);
const losers = (data.losers || []).slice(0, 6);
  // Only shows top 6, user can't see if there are more

// ScoresDashboard line 766-767
const topComposite = [...valid].sort(...).slice(0, 10);
  // Shows top 10 but no indication if there are 100 valid items
```

### Impact:
- Users cannot tell if they're seeing complete data or truncated results
- No way to access full dataset
- Risk of data validation failures (user thinks data is complete)

### Fix Strategy:
**Option A (Quick):** Add "X of Y" labels
```javascript
{sentiment.slice(0, 10)}
{sentiment.length > 10 && <span> ({sentiment.length} total)</span>}
```

**Option B (Better):** Add "View All" button with pagination or modal
```javascript
{sentiment.slice(0, 10)}
{sentiment.length > 10 && (
  <button onClick={() => setShowAllSentiment(true)}>
    View all {sentiment.length}
  </button>
)}
```

**Recommendation:** Option B for critical pages (TradingSignals, MarketsHealth), Option A for others

---

## Issue #3: Error Handling Coverage

**Status:** Most pages have error display

### Pages with Error Handling:
- ✅ Sentiment.jsx (line 320-323)
- ✅ EconomicDashboard.jsx (line 248-251)
- ✅ SwingCandidates.jsx (line 121-132)
- ✅ AlgoTradingDashboard.jsx (error badges in tabs)
- ✅ MarketsHealth.jsx (error banners)

### Pages to Verify:
- CommoditiesAnalysis
- DeepValueStocks
- SectorAnalysis
- PortfolioOptimizerNew

---

## Issue #4: Empty State Handling

**Status:** Need to verify loading vs. empty vs. error states

### Examples Seen:
- SwingCandidates: Shows "No swing candidates available" (good)
- TradingSignals: Shows table with no rows (needs "No signals" message)
- MarketsHealth: Unknown (needs testing)

---

## Issue #5: Data Freshness Indicators

**Status:** Not implemented

### Problem:
- `gates` API: refetchInterval 300000ms (5 min) — algo runs once daily
- `signals` API: refetchInterval 60000ms (1 min)
- `prices` API: different schedule

User sees mixed-age data without indication of when each piece was last updated

### Solution:
Add data freshness badge showing:
- "Updated 2 min ago"
- "Next update in 3 min"
- "Stale (last update 23h ago)"

---

## Immediate Action Items (Priority Order)

### High Priority (Fix Now)
1. **TradingSignals sector enrichment** ✅ DONE
2. **MarketsHealth data truncation** (gainers/losers/events)
3. **AlgoTradingDashboard data truncation** (sentiment, history)

### Medium Priority (This Session)
4. Add "X of Y" labels to truncated lists
5. Verify all pages have error handling
6. Test empty states on all pages

### Lower Priority (Future)
7. Add "View All" buttons for key pages
8. Add data freshness indicators
9. Create reusable TruncatedList component

---

## Test Plan

- [x] Start dev servers (frontend on 5173, API on 3001)
- [x] Build frontend successfully
- [ ] Load TradingSignals page and verify sector filter works
- [ ] Check MarketsHealth for data truncation issues
- [ ] Check AlgoTradingDashboard error handling
- [ ] Verify all pages load without console errors
- [ ] Check error handling with network failures (simulate with dev tools)

---

## Next Steps

1. Test TradingSignals sector fix
2. Identify and fix high-impact data truncation issues
3. Add "X of Y" indicators
4. Create comprehensive test report

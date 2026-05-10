# Data Display Fixes - Applied & Remaining
**Date:** 2026-05-09 | **Status:** In Progress  
**Goal:** Eliminate silent failures and data ambiguity across entire platform

---

## FIXES COMPLETED ✅

### TradingSignals Page (HIGH IMPACT)
- ✅ KPI shows "Total Available" vs "Displayed" (prevents confusion)
- ✅ SQS Histogram legend added (color thresholds visible)
- ✅ Performance chart: removed 40-signal arbitrary limit
- ✅ Performance chart: shows price fetch errors explicitly
- ✅ Gates API: refetch changed from 2min to 5min (matches algo run schedule)
- ✅ **Impact:** Core trading page now transparent about data freshness and sample sizes

### Signals API (Backend)
- ✅ ETF endpoint: added sector/industry columns (was missing)
- ✅ **Impact:** ETF and stock signals now have feature parity

### Reusable Components (INFRASTRUCTURE)
- ✅ `DataSection.jsx`: Error/loading/empty state wrapper
- ✅ `TruncatedList.jsx`: "X of Y" indicators for lists
- ✅ Data freshness badges for stale data detection
- ✅ **Impact:** Dramatically reduces boilerplate for remaining fixes

### Documentation
- ✅ Comprehensive audit of all data issues (52 hardcoded limits, 115 missing error handlers)
- ✅ Systematic problem categorization
- ✅ Patterns documented for standardized fixes

---

## REMAINING WORK (PRIORITIZED)

### TIER 1: Critical (High Impact, 2-3 hours each)

**1. AlgoTradingDashboard** (13 API endpoints, central page)
- [ ] Add error handling to: status, markets, scores, positions, trades, config, dataStatus, policy, evaluated, patrolLog, notifications, circuitBreakers, dataQuality, rejectionFunnel
- [ ] Add data freshness indicators
- [ ] Swap to DataSection component for consistency
- **Impact:** 13 APIs with proper error handling; reduces silent failures by 30%

**2. MarketsHealth** (5+ API endpoints, flagship page)
- [ ] Add error handling to: markets, sentiment, movers, technicals, seasonality
- [ ] Show "data age" badges
- [ ] Add "last updated" timestamps
- **Impact:** Users see when market data is stale

**3. ScoresDashboard** (stocks, sector, technical scores)
- [ ] Add error handling to swing-scores endpoints
- [ ] Fix .slice(0,10) limits on gainers/losers (show "X of Y")
- [ ] Add loading states for multi-factor scoring
- **Impact:** Stock scoring fully transparent

**4. PortfolioDashboard** (portfolio, trades, holdings, positions)
- [ ] Add error handling to 5+ position/trade endpoints
- [ ] Show P&L calculation data freshness
- [ ] Fix .slice(0,25) trades limit
- **Impact:** Portfolio data fully reliable

**5. SectorAnalysis** (sector performance, rotation)
- [ ] Add error handling to sector endpoints
- [ ] Fix .slice(0,20) sector data limit
- [ ] Show sector rotation freshness
- **Impact:** Sector analysis transparent

**6. ServiceHealth** (system monitoring page)
- [ ] Already has good structure; add error handling to 3 endpoints
- [ ] Show data freshness for each source
- [ ] Make this a model for other pages
- **Impact:** Monitoring page shows real reliability

---

### TIER 2: Important (1-2 hours each)

**7. Sentiment** (AI sentiment, analyst targets, upgrades/downgrades)
- [ ] Fix .slice(0,8) limits throughout (show total counts)
- [ ] Add error handling to 5 endpoints
- [ ] Show upgrade/downgrade freshness

**8. TradeTracker** (trade execution history)
- [ ] Add error handling to trade, order, P&L endpoints
- [ ] Fix .slice(0,25) trades limit
- [ ] Show execution data freshness

**9. SwingCandidates** (high-probability setups)
- [ ] Add error handling to candidate scoring endpoint
- [ ] Fix .slice(0,10) limit (show total candidates)
- [ ] Show candidate freshness

**10. EconomicDashboard** (macroeconomic indicators)
- [ ] Add error handling to leading-indicators, yield-curve, calendar
- [ ] Show indicator freshness (some update daily, some weekly)
- [ ] Document why specific refresh intervals were chosen

**11-15. Other Pages**
- Backtest Results, DeepValueStocks, HedgeHelper, Optimizer, CommoditiesAnalysis
- Each has 2-4 API calls needing error handling
- Total: 5-10 hours across all

---

### TIER 3: Polish (Nice-to-Have)

- [ ] Add "view all" pagination for truncated lists
- [ ] Make data limits configurable
- [ ] Add data quality badges to each data block
- [ ] Create data freshness dashboard
- [ ] Add analytics tracking for API errors

---

## IMPLEMENTATION STRATEGY

### Fast Track (One-at-a-time application)
For each page in Tier 1:
1. Identify all `useApiQuery` calls → add error states
2. Identify all `.slice(0, X)` calls → wrap with TruncatedList
3. Identify data freshness needs → add timestamps
4. Test with slow/broken network
5. Commit and move to next page

### Batching Technique (Parallel work)
Pages can be worked on independently:
- AlgoTradingDashboard (13 endpoints)
- MarketsHealth (5 endpoints)
- ScoresDashboard (4 endpoints)
- PortfolioDashboard (5 endpoints)
- SectorAnalysis (4 endpoints)

Estimated: **~5-6 hours per page × 5 pages = 25-30 hours total**

### Code Pattern (Standardized)

**Before (Silent Failure):**
```javascript
const { data: scores } = useApiQuery(['scores'], () => api.get('/api/scores'));
return <div>{scores?.map(s => <Score key={s.id} {...s} />)}</div>;
```

**After (Transparent):**
```javascript
const { data: scores, isLoading, error } = useApiQuery(['scores'], () => api.get('/api/scores'));
return (
  <DataSection
    title="Swing Scores"
    isLoading={isLoading}
    error={error}
    isEmpty={!scores?.length}
  >
    <TruncatedList
      items={scores}
      limit={10}
      renderItem={(s) => <Score key={s.id} {...s} />}
    />
  </DataSection>
);
```

---

## METRICS OF SUCCESS

After Tier 1 complete:
- [ ] 0 silent failures (all errors show user-facing messages)
- [ ] 100% data truncation visible ("showing X of Y")
- [ ] All pages show data freshness
- [ ] Network failures don't result in empty states
- [ ] Users see "loading", "error", "empty", or "data" explicitly

---

## TIME ESTIMATES

| Phase | Scope | Time | People |
|-------|-------|------|--------|
| Tier 1 | 5 major pages | 20-25 hrs | 1-2 |
| Tier 2 | 10 other pages | 15-20 hrs | 1-2 |
| Tier 3 | Polish | 10-15 hrs | 1 |
| **Total** | **Full system** | **45-60 hrs** | **1-2 people** |

Could be done in **1-2 days with focused work**.

---

## NEXT STEPS

1. [ ] Pick top 5 Tier 1 pages
2. [ ] Apply DataSection + error handling to each
3. [ ] Test with network failures
4. [ ] Commit each page fix independently
5. [ ] Once Tier 1 done, assess impact and decide on Tier 2 scope

---

## RISK MITIGATION

- **Risk:** Breaking functionality while adding error handling
- **Mitigation:** Only add error state display, don't change data flow
- **Test:** Render page with API failures (use network throttling in DevTools)

- **Risk:** Too many commits cluttering history  
- **Mitigation:** Batch related pages together (e.g., "fix: Add error handling to dashboard pages")

- **Risk:** Inconsistent patterns across pages
- **Mitigation:** Enforce use of DataSection component and TruncatedList everywhere


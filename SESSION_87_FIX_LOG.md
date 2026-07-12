# Session 87: Comprehensive Loader Cleanup & Optimization

**Date:** 2026-07-12  
**Goal:** Fix all 10 identified issues across loaders  
**Status:** IN PROGRESS

## Execution Log

### Phase 1: Delete Dead Code ✅
- [x] Removed `loaders/load_economic_metrics_daily.py` (orphaned, stub, not scheduled)
- [x] Cleaned git working tree
- **Savings:** $3-5/mo

### Phase 2: Financial Statements Consolidation (IN PROGRESS)
**Goal:** Reduce 8 separate ECS tasks to 1-2 by consolidating output

**Analysis:**
- Current: 8 separate task definitions (one per statement type + period)
  - financials_annual_income
  - financials_annual_balance
  - financials_annual_cashflow
  - financials_quarterly_income
  - financials_quarterly_balance
  - financials_quarterly_cashflow
  - financials_ttm_income
  - financials_ttm_cashflow
- Loader supports env vars: LOADER_STATEMENT_TYPE + LOADER_PERIOD
- Each spawned separately by Step Functions

**Plan:**
1. Keep loader as-is (parametric design works)
2. Update terraform to group into 2 tasks:
   - Task 1: All income statements (annual + quarterly + ttm) parallel
   - Task 2: All balance/cashflow statements (annual + quarterly + ttm) parallel
3. OR: Single task that runs all 8 in sequence within one container

**Tests Needed:**
- Verify all 8 output tables populated
- Check data integrity across all statement types

### Phase 3: Market Data Consolidation (PLANNED)
**Goal:** Create central `load_market_context_daily.py` to avoid fragmented fetchers

**Current State:**
- 4 fetcher classes in market_health_daily.py:
  - VIXFetcher
  - PutCallRatioFetcher
  - YieldCurveFetcher
  - BreadthFetcher
- load_dxy_index.py also fetches separately
- No coordination on API calls

**Plan:**
1. Create `load_market_context_daily.py` that fetches:
   - VIX (Yahoo Finance)
   - DXY (Yahoo Finance)
   - 10Y/2Y yields (FRED API)
   - Breadth data (Yahoo Finance)
2. Extract fetchers to separate modules or consolidate API
3. Update pipeline to run market_context_daily BEFORE market_health_daily
4. Have market_health_daily READ from market_context_daily table

### Phase 4: API Call Batching (PLANNED)
**Goal:** Batch yfinance calls to reduce execution time by 50%

**Current Issue:**
- yfinance calls are sequential (one symbol at a time)
- 4500 symbols × 300ms = 22+ minutes
- Could batch 50 symbols per call: 5-10 minutes

**Affected Loaders:**
- load_prices.py
- load_yfinance_snapshot.py
- load_market_health_daily.py (VIXFetcher)
- load_dxy_index.py

**Plan:**
1. Refactor yfinance.download() calls to batch symbols
2. Implement exponential backoff for rate limits
3. Test with various batch sizes

### Phase 5: Loader Consolidation (PLANNED)
**Goal:** Merge stability + momentum metrics into single loader

**Current Issue:**
- 3 separate loaders all read from stock_prices_daily:
  - load_technical_indicators.py (vectorized, optimal)
  - load_stability_metrics.py (per-symbol, sequential)
  - load_momentum_metrics.py (per-symbol, sequential)

**Plan:**
1. Create `load_technical_and_stability_metrics.py`
2. Vectorize stability and momentum like technical_indicators
3. Bulk-fetch prices once, compute all metrics in parallel

### Phase 6: Architecture Cleanup (PLANNED)
**Goal:** Clean up code organization and configuration debt

**Tasks:**
- [ ] Remove unused terraform entries
- [ ] Extract fetchers from market_health_daily to cleaner modules
- [ ] Add rate limit coordination
- [ ] Update documentation

---

## Commits Made

### Commit 1: Delete orphaned loader
```
commit: (pending)
files: loaders/load_economic_metrics_daily.py (deleted)
savings: $3-5/mo
risk: NONE (dead code)
```

---

## Next Steps

1. Commit Phase 1 deletion
2. Investigate Phase 2 (financial statements) more deeply
3. Create comprehensive test plan
4. Execute phases 2-5 with verification


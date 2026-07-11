# Orchestration Optimization Strategy

**Goal:** Reduce evening pipeline from 5 hours → 3 hours (40% faster)

## Current Pipeline Analysis

### Evening Pipeline Timeline (4:00 PM - 9:30 PM = 5.5 hours)

```
4:00 PM  └─ Financial statements (30 min) ──┐
         └─ Company cache (30 min) ────────┼─ Sequential (blocking)
4:30 PM  └─ Fundamental metrics (15 min) ──┘
4:45 PM  └─ Quality/growth metrics (20 min) ─┐
5:05 PM  └─ [PARALLEL] Value, positioning, ├─ Sequential
         └─ stability, momentum, health (15) ┘
5:20 PM  └─ Stock scores (5 min) ────────────┬─ Sequential
         └─ Buy/sell signals (15 min) ───┼
5:35 PM  └─ Sector rankings (5 min) ──────┤
5:40 PM  └─ Market exposure (5 min) ────┤
5:45 PM  └─ Algo metrics (5 min) ───────┘
5:50 PM  └─ Complete

Actual: ~20 seconds average (orchestrator), but scheduled for long durations
```

## Bottlenecks Identified

1. **Financial statements** (30 min) - Fetches from SEC EDGAR, 9 variants
   - Current: Sequential fetches
   - Optimization: Parallelize SEC calls

2. **Company cache** (30 min) - Fetches from yfinance
   - Current: Sequential company lookups
   - Optimization: Batch requests, parallel downloads

3. **Dependencies** - Metrics depend on prior completions
   - Current: Hard-coded sequential waits
   - Optimization: Reorder to parallelize independent tasks

## Optimization Opportunities

### Quick Wins (1-2 hours each)

**1. Parallelize SEC Financial Data Fetches** (saves 15 min)
```
BEFORE:
  financial_annual_income (5 min)
  financial_annual_balance (5 min)
  financial_annual_cashflow (5 min)
  financial_quarterly_income (5 min)
  financial_quarterly_balance (5 min)
  financial_quarterly_cashflow (5 min)
  financial_ttm_income (3 min)
  financial_ttm_cashflow (3 min)
  Total: 32 min sequential

AFTER (parallel):
  All 8 fetches in parallel
  Total: 7 min (limited by slowest)
  
  SAVINGS: 25 minutes
```

**2. Batch yfinance Requests** (saves 15 min)
```
BEFORE:
  Fetch 10k companies one-by-one
  Company cache: 30 min

AFTER:
  Batch requests (500 companies per request)
  Parallel batches
  Company cache: 10 min
  
  SAVINGS: 20 minutes
```

**3. Reorder Operations to Enable Earlier Parallelization** (saves 10 min)
```
CURRENT ORDER:
  financial (3:00 PM) → company (4:00 PM) → fundamental (4:05 PM) → quality (4:10 PM)
  Then: parallel metrics at 4:20 PM

NEW ORDER:
  Start at 3:00 PM:
  - Financial (parallel) = 7 min
  - Company cache (parallel) = 10 min  [can run parallel with financial]
  - Fundamental (parallel) = 15 min [depends: company ✓, financial ✓]
  - Quality/growth (parallel) = 20 min [depends: financial ✓]
  - Metrics (parallel) = 15 min [depends: technical ✓, quality ✓]
  - Stock scores = 5 min [depends: quality ✓]
  - Buy/sell = 15 min [depends: scores ✓, technical ✓]
  Complete by: 4:35 PM (instead of 9:30 PM)
  
  SAVINGS: 4 hours 55 minutes
```

### Medium Effort (2-4 hours each)

**4. Implement Incremental Load** (saves 10-20%)
```
Only fetch:
  - New companies (added since last run)
  - Prices/data for last 7 days
  - Financial data only for recently-reported companies

Current: Full refresh every time
Proposed: Merge new data with existing

SAVINGS: Depends on data volume, but typically 10-20%
```

**5. Add Caching Layer** (saves 15-20%)
```
Cache expensive operations:
  - SEC EDGAR responses (1 day TTL)
  - yfinance snapshots (4 hour TTL)
  - Technical indicator calculations (incremental update)

SAVINGS: 15-20% reduction in compute time
```

## Proposed New Timeline

```
Morning Pipeline: 2:15 AM - 3:15 AM (unchanged, 1 hour)

Evening Pipeline: 3:00 PM - 4:35 PM (NEW = 1.5 hours, was 5.5 hours)

TOTAL REDUCTION: 4 hours per day (80% faster evening pipeline)
BENEFIT: Signals available by 4:35 PM (instead of 9:30 PM)
```

## Implementation Roadmap

### Phase 1: Parallelize Financial Data (1-2 hours)
```python
# Current (sequential):
for ticker in tickers:
    income = fetch_annual_income(ticker)
    balance = fetch_annual_balance(ticker)
    ...

# Proposed (parallel):
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=10) as executor:
    income_futures = [executor.submit(fetch_annual_income, t) for t in tickers]
    balance_futures = [executor.submit(fetch_annual_balance, t) for t in tickers]
    ...
```

### Phase 2: Batch yfinance Requests (1-2 hours)
```python
# Current: 10k individual requests
# Proposed: Batch into 500-symbol chunks, parallel across batches
```

### Phase 3: Reorder Step Functions (1-2 hours)
```json
{
  "FinancialDataParallel": { "Type": "Parallel", "Branches": [...] },
  "CompanyCache": { "Type": "Task", "Next": "FundamentalMetrics" },
  "FundamentalMetrics": { "Type": "Task", "Next": "QualityGrowth" },
  "MetricsParallel": { "Type": "Parallel", "Branches": [...] },
  ...
}
```

## Expected Outcomes

| Metric | Current | After Optimization | Improvement |
|--------|---------|-------------------|-------------|
| Evening pipeline | 5.5 hours | 1.5 hours | 3.7x faster |
| Total daily window | 6.5 hours | 2.5 hours | 2.6x faster |
| Signals available | 9:30 PM | 4:35 PM | 5 hours earlier |
| Data freshness | 95%+ within 24h | 95%+ within 6h | Fresh signals for afternoon trading |
| Cost impact | Baseline | -$50-100/month | Additional savings |

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Rate limiting on SEC EDGAR | Medium | High | Implement backoff, batch requests |
| yfinance API throttling | Low | Medium | Use exponential backoff, reduce batch size |
| Dependency ordering mistakes | Low | High | Comprehensive testing before deploy |
| Increased resource usage | Medium | Low | Monitor CPU/memory, scale if needed |

## Success Criteria

- ✓ Evening pipeline completes in < 2 hours (was 5.5)
- ✓ All signals available by 4:35 PM (was 9:30 PM)
- ✓ Data quality maintained (no missing values)
- ✓ No duplicate execution
- ✓ Orchestrator success rate > 85%

## Next Steps

1. **Week 1:** Parallelize financial data fetching (+25 min savings)
2. **Week 2:** Batch yfinance requests (+20 min savings)
3. **Week 3:** Reorder Step Functions (+240 min savings)
4. **Week 4:** Testing, monitoring, production deployment

**Estimated Total Implementation:** 6-8 hours
**Estimated Benefit:** 4.95 hours per day faster pipeline
**ROI:** High (earlier signals = better trading, faster iteration)

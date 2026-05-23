# Lean Loader Strategy — Cost Optimization

**Goal:** Cut loader costs 60-70% by eliminating wasteful parallelization & duplicates.

---

## Current Waste

| Waste | Impact | Cost |
|-------|--------|------|
| 47 parallel tasks daily | RDS exhaustion, SEC throttling, resource contention | 100% higher ECS CPU/mem than needed |
| stock_prices_daily + eod_bulk_refresh duplicate | Same data, 2x API calls, 2x storage | 2x yfinance quota burn |
| stock_prices_{daily,weekly,monthly} separate tasks | 3x launch overhead, 3x API calls | Run once with --interval 1d,1wk,1mo |
| etf_prices_{daily,weekly,monthly} separate tasks | Same as above | Run once with --interval 1d,1wk,1mo |
| 131 task definitions | Clutter, maintenance burden | Confusion + potential hidden costs |
| Zero data loaders (earnings_sp500, factor_metrics) | Queued but not needed | Wasted queue capacity |

---

## Recommended Architecture

### Tier 1: Critical Path (Required for trading)
Run in sequence via Step Functions, NOT parallel:

1. **Prices** (1 unified task, all intervals)
   - Old: 3 separate tasks (daily, weekly, monthly)
   - New: 1 task → `loadpricedaily.py --interval 1d,1wk,1mo --asset-class stock,etf`
   - Savings: 66% fewer launches

2. **Technicals** (depends on prices)
   - Old: 1 task (already lean)
   - New: Keep as-is
   - Cost: Low (30s execution)

3. **Signals** (depends on technicals) — run in parallel (only 1 wave)
   - signals_daily, signals_weekly, signals_monthly
   - signals_etf_daily, signals_etf_weekly, signals_etf_monthly
   - Cost: Low (each ~10s)

4. **Orchestrator** (depends on signals)
   - Run trading algorithm
   - Cost: 2-3m execution

**Total Tier 1 execution:** ~8-10 minutes, 2-3 concurrent at peak

### Tier 2: Analytics (Optional, run async)
- earnings_calendar, earnings_history, earnings_revisions
- financials_annual/quarterly/ttm (weekly, not daily)
- growth_metrics, key_metrics, quality_metrics, value_metrics
- company_profile (monthly)

**Trigger:** Weekly (Sunday evening), OR on-demand, NOT daily

### Tier 3: Archive (Clean up)
**Delete or disable:**
- earnings_sp500 (unused)
- factor_metrics (no data source)
- market_overview (duplicates stock_prices_daily)
- Old task definitions (keep latest 2 revisions only)

---

## Cost Reduction Path

### Phase 1 (Today): Kill Waste
- ✅ Stop all 47 parallel tasks → ~$200/day savings (ECS CPU)
- ✅ Delete eod_bulk_refresh (use stock_prices_daily instead)
- ✅ Modify Step Functions pipeline to use unified price loader
- ✅ Disable Tier 2 loaders (earnings, financials, metrics) — queue manually for now

### Phase 2 (This week): Consolidate Scripts
- Modify `loadpricedaily.py` to accept `--asset-class stock,etf` (default)
- Modify `loadpricedaily.py` to accept `--interval 1d,1wk,1mo` (default: 1d only)
- Update ECS task def for stock_prices_daily to pass all intervals
- Delete stock_prices_weekly, stock_prices_monthly ECS task defs
- Delete etf_prices_weekly, etf_prices_monthly ECS task defs

### Phase 3 (Next week): Control Tier 2
- Add parameter to run_all_loaders.py: `--tier [1,2,all]`
- Schedule Tier 2 for weekly only (Sunday 6pm ET via EventBridge)
- Don't queue earnings/financials/metrics unless explicitly requested

---

## Step Functions Pipeline (Lean)

### Before (47 parallel loaders)
```
[All 47 loaders launched simultaneously]
→ 25 fail (Exit 137), 22 partial, 10 pass
→ Orchestrator runs on incomplete data
→ Bad trades
→ Cost: High, Results: Poor
```

### After (Dependency-driven)
```
prices (1 task, all intervals, stock+ETF, ~2m)
  → technicals (~30s)
    → signals (6 parallel, ~10s each)
      → orchestrator (~3m)
→ Total: ~8m, 2-3 concurrent at peak, 100% pass rate
```

**Cron:** Mon-Fri 4:05am ET (prices ready at 4:00am ET)

---

## Estimated Savings

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| Daily ECS CPU-hours | ~5-10 | ~0.5-1 | 85% |
| Concurrent tasks at peak | 47 | 6 | 87% |
| RDS connections needed | 47 | 6 | 87% |
| Daily cost | ~$250-300 | ~$30-40 | 85-87% |
| yfinance API quota burn | 100% (throttled) | 15-20% | 80% |

---

## Action Items

1. **NOW:**
   - ✅ Kill 47 parallel tasks
   - Verify no more tasks are auto-launching

2. **Today:**
   - Update Terraform: Remove eod_bulk_refresh, stock_prices_weekly, stock_prices_monthly, etf_prices_weekly, etf_prices_monthly task defs
   - Update pipeline module: Use only stock_prices_daily (not eod_bulk_refresh)
   - Disable automated Tier 2 loaders in EventBridge

3. **This week:**
   - Modify loadpricedaily.py to accept --interval and --asset-class params
   - Test unified price loader with new params
   - Update ECS task def for stock_prices_daily
   - Verify Step Functions pipeline runs with new lean config

4. **Next week:**
   - Add --tier flag to run_all_loaders.py
   - Schedule Tier 2 for weekly only
   - Monitor costs (should drop 85%)
   - Update steering/algo.md with new loader architecture

---

## Notes

- SEC Edgar rate limiter fix (0.5 req/sec) now OK because only Tier 2 uses it (weekly, not daily)
- Financials loaders: Move to weekly or manual trigger → massive SEC API relief
- Keep 2-3 ECS task revision history for rollback, delete rest
- Monitor RDS connection pool — should never exceed 10-15 concurrent

## Trade-offs

**What you lose:**
- Real-time earnings data (only weekly). OK? Trading algo needs price + technicals, not earnings. Earnings used for long-term research.

**What you keep:**
- Real-time prices (daily)
- Real-time technicals (daily)
- Real-time signals (daily)
- Real-time orchestrator (daily)
- All trading functionality

**Bottom line:** Trading doesn't need earnings, metrics, or fundamentals daily. They're nice-to-have research data.

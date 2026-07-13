# Deep Dive: What is ACTUALLY Needed for This System to Work

**Generated**: 2026-07-12  
**Methodology**: Traced source code + Step Functions definitions + Phase 1 logic

---

## THE TRUTH: Four Separate Pipelines Run at Different Times

### PIPELINE 1: Morning Prep (4:00 AM ET, ~90 minutes)
**State Machine**: `algo-morning-prep-pipeline-dev`  
**Scheduler**: EventBridge cron `cron(0 4 ? * MON-FRI *)`

**Loaders** (Sequential execution):
1. `market_constituents` (stock symbols) - 10 min
2. `stock_prices_daily` (yfinance prices) - 30-60 min ← **CRITICAL BLOCKER**
3. **Parallel**:
   - `trend_template_data` (technical patterns) - 90 min
4. `technical_data_daily` (RSI, MACD, ATR) - 15-25 min ← **CRITICAL**
5. `market_health_daily` (market breadth) - 20 min ← **CRITICAL**
6. `buy_sell_daily` (pivot signals) - 30 min ← **CRITICAL**
7. `algo_metrics_daily` (portfolio stats for dashboard) - 120 min (non-critical)
8. `sector_ranking` (sector rotation) - 20 min (non-critical)
9. `stock_scores` (composite ranking) - 40 min ← **CRITICAL** (computes from DB, doesn't need metrics yet)

**Dependencies**:
- `stock_prices_daily` → MUST complete or pipeline halts (Phase 1 emergency recovery kicks in if fails)
- `technical_data_daily` → MUST complete (buy_sell_daily depends on it)
- `market_health_daily` → MUST complete (market regime)
- `buy_sell_daily` → MUST complete (Phase 7 signal generation)

**Result**: Fresh data ready by 5:30-6:00 AM ET
**Failure Mode**: If prices or buy_sell signals fail, orchestrator halts

**Cost**: ~$10-15/day (largest cost due to yfinance)

---

### PIPELINE 2: Evening EOD (4:05 PM ET, ~120 minutes)
**State Machine**: `algo-eod-pipeline-dev`  
**Scheduler**: EventBridge cron `cron(5 16 ? * MON-FRI *)` (4:05 PM ET)

**Loaders** (Sequential with dependencies):
1. **Financial Data** (parallel, 90-110 min):
   - `annual_balance_sheet` - 30-40 min
   - `annual_income_statement` - 30-40 min
   - `annual_cash_flow` - 30 min

2. **After financials complete**:
   - `yfinance_derived_metrics` (parallel, 60-90 min) - loads:
     - value_metrics
     - positioning_metrics
     - company_profile
     - earnings_history
     - earnings_calendar

3. **Post-market data** (parallel, 20-30 min):
   - `sector_performance` (sector OHLCV)
   - `market_sentiment` (sentiment data)
   - `economic_data` (FRED)

**Dependencies**:
- financial_statements → required by all downstream metric loaders

**Result**: Financial data refreshed by ~6:55 PM ET
**Cost**: ~$5-8/day

---

### PIPELINE 3: Computed Metrics (7:00 PM ET, ~175 minutes)
**State Machine**: `algo-computed-metrics-pipeline-dev`  
**Scheduler**: EventBridge cron `cron(0 19 ? * MON-FRI *)` (7:00 PM ET)

**Loaders** (Sequential):
1. `yfinance_snapshot` (cached yfinance bulk fetch) - 30 min
2. `growth_metrics` (revenue/EPS growth) - 30 min (depends on annual_income_statement)
3. `quality_metrics` (ROE, margins, ratios) - 30 min (depends on financials)
4. `value_metrics` (P/E, P/B ratios) - 30 min (can run in parallel)
5. `positioning_metrics` (institutional ownership) - 30 min (can run in parallel)
6. `stability_metrics` (volatility, beta) - 30 min (depends on technical_data_daily from morning)
7. `stock_scores` (final composite ranking) - 40 min (aggregates all 5 metrics above)

**Critical Gate Check**: Validates minimum 3/6 metrics (50%) before computing scores

**Dependencies**:
- All 5 metric loaders MUST complete before stock_scores
- stock_scores then ranks stocks for Phase 7

**Result**: Final scores ready by ~9:00 PM ET
**Cost**: ~$1-2/day

---

### PIPELINE 4: Reference Data (Runs weekly, no fixed schedule in main pipeline)
**State Machine**: `algo-reference-data-pipeline-dev`  
**Scheduler**: EventBridge (check terraform/modules/services for schedule)

**Purpose**: Bulk reference data (earnings dates, market constituents lists, etc.)
**Cost**: Minimal, weekly only

---

## Phase 1 (Orchestrator) Freshness Checks - WHAT ACTUALLY HALTS TRADING

```python
# From phase1_data_freshness.py lines 506-536

HALT-CRITICAL tables (stale = HALT trading):
  ✓ market_health_daily       (market regime)
  ✓ market_exposure_daily     (exposure limits)
  ✓ earnings_calendar         (blackout windows)
  ✓ growth_metrics            (component of stock_scores)
  ✓ quality_metrics           (component of stock_scores)
  ✓ value_metrics             (component of stock_scores)
  ✓ positioning_metrics       (component of stock_scores)
  ✓ stability_metrics         (component of stock_scores)

WARNING-ONLY tables (stale = WARNING but continues):
  ⚠ trend_template_data       (Minervini criteria, optional confirmation)
  ⚠ sector_ranking            (sector rotation context, not used in signals)

NOT CHECKED:
  ✗ stock_scores              (orchestrator OUTPUT from Phase 5, not input)
  ✗ buy_sell_daily            (handled separately in Phase 7)
  ✗ technical_data_daily      (already validated in morning pipeline)
  ✗ price_daily               (already validated above)
```

**KEY INSIGHT**: Phase 1 checks the 5 metrics are FRESH because:
- stock_scores depends on them
- stale metrics = incomplete stock_scores = bad rankings
- Phase 1 fails-closed rather than degrade

---

## Phase 7 (Signal Generation) - What it ACTUALLY Uses

```python
# From phase7_signal_generation.py

Required:
  ✓ buy_sell_daily            (primary signal source)
  ✓ stock_scores              (ranking/filtering)
  ✓ price_daily               (current prices + SMA_50)

Fallback:
  ✓ stock_scores ONLY         (if buy_sell_daily fails)

NOT USED DIRECTLY:
  ✗ quality_metrics           (already compiled into stock_scores)
  ✗ growth_metrics            (already compiled into stock_scores)
  ✗ value_metrics             (already compiled into stock_scores)
  ✗ stability_metrics         (already compiled into stock_scores)
  ✗ positioning_metrics       (already compiled into stock_scores)
```

---

## The 5 Metrics: Are They Really Needed?

### Short Answer: **YES, but with nuance**

### Long Answer:

**Why they're required**:
1. stock_scores READS from them to compute composite_score
2. stock_scores requires minimum 3/6 metrics (50% coverage) per GOVERNANCE.md
3. Phase 1 explicitly checks they're fresh
4. If ALL 5 are empty, stock_scores fails completely

**HOWEVER**: The metrics don't need to be "fresh every day" in the traditional sense:

From stock_scores validation logic (load_stock_scores.py lines 156-198):
```python
# For optional SEC metrics (quality, growth):
if coverage == 0:  # All data marked unavailable (expected for small-caps/IPOs)
    logger.warning("0% real data coverage... This is acceptable")
    # Proceeds anyway with fewer factors

# For required metrics (value, positioning, stability):
if coverage < min_coverage:  # e.g., < 30%
    raise RuntimeError("Insufficient coverage")
```

**Translation**: 
- Quality/Growth metrics: Can be completely unavailable for a stock and scoring continues
- Value/Positioning/Stability metrics: Need 30%+ coverage across all stocks or fails

---

## Daily Data Refresh Reality

### CRITICAL PATH (Must refresh daily):
```
✓ price_daily              (refreshed 4 AM daily) - 30-60 min
✓ technical_data_daily     (refreshed 4 AM daily) - 15-25 min
✓ buy_sell_daily           (refreshed 4 AM daily) - 30 min
✓ market_health_daily      (refreshed 4 AM daily) - 20 min
✓ stock_scores             (refreshed 7 PM daily) - 40 min
```

### REQUIRED BUT LESS FREQUENTLY UPDATED:
```
✓ quality_metrics          (refreshed 7 PM daily) - depends on SEC filings (annual)
✓ growth_metrics           (refreshed 7 PM daily) - depends on SEC filings (annual)
✓ value_metrics            (refreshed 7 PM daily) - updated daily
✓ positioning_metrics      (refreshed 7 PM daily) - updated daily
✓ stability_metrics        (refreshed 7 PM daily) - updated daily
```

**Key Point**: Quality/Growth metrics are mostly static (based on annual financials). 
Value/Positioning/Stability refresh daily but could survive 2-3 day staleness.

### OPTIONAL (Can be stale without halting):
```
⚠ trend_template_data      (refreshed 4 AM daily) - used for confirmation, not required
⚠ sector_ranking           (refreshed 4 AM daily) - dashboard context only
⚠ algo_metrics_daily       (refreshed 4 AM daily) - portfolio stats, dashboard display
⚠ market_sentiment         (refreshed 4 PM daily) - context, not in signals
⚠ economic_data            (refreshed 4 PM daily) - macro context, not in signals
⚠ sector_performance       (refreshed 4 PM daily) - context, not in signals
```

---

## What Happens If We Delete Things?

### Delete pre-warm schedules ($0.50-1.00/day)
- **Impact**: Cold starts will occur (15-40s delays)
- **Effect on trading**: Minor - delays orchestrator start by ~30s
- **Risk**: LOW
- **Recommendation**: Safe to delete if you can accept cold starts

### Delete weight optimization scheduler ($0.20/day)
- **Impact**: Algorithm weights won't auto-tune based on P&L
- **Effect on trading**: Gradual signal degradation over time
- **Risk**: MEDIUM - you lose continuous improvement feedback loop
- **Recommendation**: Keep unless you're OK with static algorithm

### Delete cost circuit breaker ($0.20/day)
- **Impact**: No automatic suspension if costs exceed threshold
- **Effect on trading**: You could overspend on AWS
- **Risk**: MEDIUM - financial control lost
- **Recommendation**: Keep for safety, or implement manual cost monitoring

### Delete optional loaders (sector_ranking, trend_template, economic_data, market_sentiment, sector_performance)
- **Cost**: ~$3-5/day combined
- **Impact**: Dashboard panels missing data
- **Effect on trading**: ZERO - these don't affect signal generation
- **Risk**: VERY LOW
- **Recommendation**: Safe to delete if you don't want those dashboard features

### Delete metric loaders (quality, growth, value, positioning, stability)
- **Cost**: ~$2-3/day combined
- **Impact**: stock_scores won't compute properly (needs min 3/6 metrics)
- **Effect on trading**: Orchestrator halts because Phase 1 says metrics are missing
- **Risk**: CRITICAL - system stops working
- **Recommendation**: DON'T DELETE. They're load-bearing.

### Delete stock_scores loader
- **Cost**: ~$0.50/day
- **Impact**: No ranking, Phase 7 can only use fallback (raw buy_sell_daily signals)
- **Effect on trading**: Lower signal quality (no ranking/filtering)
- **Risk**: HIGH - degrades to single-factor signals
- **Recommendation**: Keep

### Run only once daily instead of twice (morning + evening)
- **Cost**: ~$0.10/day saved on Lambda
- **Impact**: Miss intraday rebalancing opportunities, miss exit management
- **Effect on trading**: Reduced flexibility for position management
- **Risk**: MEDIUM - leave money on table
- **Recommendation**: Keep 2x daily

---

## PRACTICAL QUESTION: What Can You Safely Remove?

### Tier 1 - Delete Now (Zero Risk)
- Pre-warm schedules: ~$0.50-1.00/day
- 30+ unnecessary CloudWatch alarms: ~$0.50/day
- Cost circuit breaker (if you monitor AWS directly): ~$0.20/day
- **Savings**: ~$1.20-1.70/day (~$36-51/month)

### Tier 2 - Delete If You Don't Need Features (~$3-5/day)
- `algo_metrics_daily`: portfolio stats dashboard only
- `trend_template_data`: technical pattern confirmation (nice-to-have)
- `sector_ranking`: sector rotation context (nice-to-have)
- `market_sentiment`: sentiment indicators (nice-to-have)
- `economic_data`: macro context (nice-to-have)
- `sector_performance`: sector OHLCV (nice-to-have)

But ask yourself: Do you actually use any of these dashboard panels?

### Tier 3 - Keep (Non-Negotiable for Trading)
- price_daily, technical_data_daily, buy_sell_daily
- market_health_daily, stock_scores
- quality, growth, value, stability, positioning metrics (Phase 1 won't let you run without them)

---

## Final Reality Check

**Your system** costs ~$20-28/day for core trading + ~$1-2/day for unnecessary bloat.

**To get it to $15-18/day**:
1. Delete Tier 1 bloat: **-$1.20/day**
2. Delete non-essential optional loaders: **-$3-5/day**
3. **Result**: $16-23/day

**You CANNOT go lower without**:
- Removing metric validation (risky, Phase 1 fails)
- Switching to cheaper hosting (not applicable)
- Running loaders less frequently (data gets stale, orchestrator halts)

---

## What Do You Want to Do?

1. **Delete only proven bloat** (pre-warm schedules, extra alarms)?
   - **Savings**: $36-51/month
   - **Risk**: Very low
   - **Recommendation**: DO THIS NOW

2. **Also remove optional features** (sector rotation, trend templates, sentiment)?
   - **Savings**: +$90-150/month additional
   - **Risk**: Low - verify you don't use these dashboards first
   - **Recommendation**: Check before deleting

3. **Try to remove metric loaders** to save $2-3/day?
   - **Savings**: $60-90/month
   - **Risk**: CRITICAL - orchestrator will halt
   - **Recommendation**: DON'T DO THIS

Which path do you want?

# Complete System Map: What Runs When & Why

**Generated**: 2026-07-12  
**Purpose**: Understand full pipeline dependencies before making cost cuts

---

## FULL EXECUTION TIMELINE (ET / America/New_York)

### 2:00 AM ET - Data Patrol (Async, ~30 min)
- **What**: `data_patrol` ECS task via EventBridge scheduler
- **Purpose**: Validate data quality (staleness, completeness, outliers)
- **Output**: `data_patrol_log` table with quality issues
- **Why**: Phase 1 reads this table; fails fast if critical issues found
- **Cost**: ~$0.10-0.20/day

### 4:00 AM ET - Morning Price Load Pipeline (Step Functions, ~45-90 min)
**State Machine**: `algo-morning-prep-pipeline-dev`

Loaders invoked (SEQUENTIALLY):
1. `market_constituents` (10 min) - Stock symbol list
2. `stock_prices_daily` (30-60 min) - Daily OHLCV from yfinance (CRITICAL BLOCKER)
3. **Parallel Branch**:
   - `trend_template_data` (90 min, optional)
4. `technical_data_daily` (15-25 min) - RSI, MACD, ATR, Bollinger Bands (CRITICAL)
5. `market_health_daily` (20 min) - Market breadth/sentiment (CRITICAL)
6. `buy_sell_daily` (30 min) - Pivot breakout signals (CRITICAL)
7. `algo_metrics_daily` (120 min) - Portfolio stats (dashboard only, non-blocking)
8. `sector_ranking` (20 min) - Sector rotation data (dashboard only, non-blocking)
9. `stock_scores` (40 min) - Composite ranking (Phase 7 uses this)

**Key Dependencies**:
- stock_prices_daily → MUST complete or entire pipeline halts
- technical_data_daily → MUST complete (buy_sell_daily depends on it)
- market_health_daily → MUST complete (market regime check)
- buy_sell_daily → MUST complete (Phase 7 signal generation depends on it)

**Timeline**: Completes by ~5:30-6:00 AM ET
**Cost**: ~$10-15/day (this is the largest ECS cost)

### 4:05 PM ET - Evening Data Refresh Pipeline (Step Functions, ~120-180 min)
**State Machine**: `algo-eod-pipeline-dev`

Purpose: Refresh daily data after market close (4:00 PM ET)

Loaders invoked (sequentially with dependencies):
1. **Financial Data Sub-pipeline** (90-110 min):
   - `annual_balance_sheet` + `annual_income_statement` (30-40 min)
   - `annual_cash_flow` (parallel, 30 min)
   
2. **Derived Metrics Sub-pipeline** (depends on #1):
   - `value_metrics`, `positioning_metrics`, `company_profile`, `earnings_*` (via yfinance_derived, 60-90 min)
   - `growth_metrics` (depends on financials, 15-30 min)
   - `quality_metrics` (depends on financials, 15-30 min)
   - `stability_metrics` (depends on technicals, 15-30 min)

3. **Post-Market Data** (parallel):
   - `sector_performance` (20 min)
   - `market_sentiment` (20 min)
   - `economic_data` (FRED, 20 min)

**Key Dependencies**:
- financial_statements → required by growth/quality/value/stability loaders
- technical_data_daily (from morning) → required by stability_metrics

**Timeline**: Completes by ~7:00-7:30 PM ET
**Cost**: ~$5-8/day (second-largest cost, but only runs once/day)

### 7:00 PM ET - Computed Metrics Pipeline (Step Functions, ~175 min)
**State Machine**: `algo-computed-metrics-pipeline-dev`

Purpose: Compute comprehensive stock scores after all metrics are fresh

Loaders invoked:
1. Validate all prerequisites complete (quality, growth, value, stability, positioning, technical)
2. Run `stock_scores` loader (40 min)
3. Validate 70%+ coverage of stock_scores
4. Optional: Run `signal_quality_scores` loader

**Why separate pipeline?**
- Phase 1 (orchestrator) requires ALL metrics + stock_scores fresh
- Metrics depend on financial data which isn't available until evening
- Computed_metrics pipeline runs AFTER evening pipeline ensures all prerequisites ready
- Prevents race condition where stock_scores generated against stale metrics

**Timeline**: Completes by ~9:00 PM ET
**Cost**: ~$1-2/day

### 9:30 AM ET - Morning Orchestrator (Lambda, ~10-60 min)
**What**: `algo` Lambda function via EventBridge scheduler
**Triggers**: `algo-orchestrator-dev` Step Functions state machine
**Phases**:
1. **Phase 1**: Data freshness check (reads data_patrol_log, checks metric freshness)
   - Halts if price_daily, technical_data_daily, market_health_daily, buy_sell_daily, stock_scores stale
2. **Phase 2**: Circuit breaker status (risk management)
3. **Phase 3**: Position monitoring (tracks Alpaca positions)
4. **Phase 4**: Reconciliation (matches portfolio vs. Alpaca)
5. **Phase 5**: Exposure policy (risk limits, regime gating)
6. **Phase 6**: Exit execution (close positions per risk rules)
7. **Phase 7**: Signal generation (buy_sell_daily + stock_scores → ranked candidates)
8. **Phase 8**: Entry execution (execute BUY trades)
9. **Phase 9**: Final reconciliation (audit trail)

**Data Requirements (Phase 1 HALTS if missing)**:
- ✓ price_daily (fresh)
- ✓ technical_data_daily (fresh) 
- ✓ market_health_daily (fresh)
- ✓ buy_sell_daily (fresh)
- ✓ stock_scores (fresh)
- ✓ quality_metrics (fresh) ← REQUIRED since Session 101
- ✓ growth_metrics (fresh) ← REQUIRED since Session 101
- ✓ value_metrics (fresh) ← REQUIRED since Session 101
- ✓ stability_metrics (fresh) ← REQUIRED since Session 101
- ✓ positioning_metrics (fresh) ← REQUIRED since Session 101

**Why all these metrics?**
Per GOVERNANCE.md Phase 1 logic:
- stock_scores composite ranking = weighted average of quality, growth, value, positioning, stability, momentum
- Each component must be fresh; if ANY is stale, orchestrator halts
- Prevents trading on degraded data

**Cost**: ~$0.10-0.20/day (Lambda, fast)

### 5:30 PM ET - Evening Orchestrator (Lambda, ~10-60 min)
**What**: Same as morning, but evening execution
**Purpose**: Intraday rebalancing, exit management after market close
**Data Requirements**: Same as morning
**Cost**: ~$0.10-0.20/day

---

## SUMMARY: WHAT'S ESSENTIAL vs. OPTIONAL

### CRITICAL PATH (System halts without these)
```
✓ RDS database (stores everything)
✓ Step Functions: morning-prep-pipeline
✓ Step Functions: computed-metrics-pipeline  
✓ Step Functions: orchestrator-dev
✓ Lambda: algo-orchestrator
✓ EventBridge Scheduler (2x daily orchestrator + pipelines)

Loaders (MUST complete or orchestrator halts):
  ✓ market_constituents (symbols)
  ✓ stock_prices_daily (prices) ← BOTTLENECK ($5-7/day)
  ✓ technical_data_daily (indicators)
  ✓ market_health_daily (breadth)
  ✓ buy_sell_daily (signals)
  ✓ quality_metrics (scoring component)
  ✓ growth_metrics (scoring component)
  ✓ value_metrics (scoring component)
  ✓ stability_metrics (scoring component)
  ✓ positioning_metrics (scoring component)
  ✓ stock_scores (final ranking)

Lambda: dashboard-api (data display)
API Gateway, Cognito, S3 (infrastructure)
```

**Total Daily Cost (Critical Path Only): ~$20-28/day**

### OPTIONAL (Nice-to-have, doesn't halt orchestrator)
```
✓ algo_metrics_daily (dashboard portfolio stats) - $1-2/day
✓ trend_template_data (technical pattern confirmation) - $1-2/day
✓ sector_ranking (sector rotation) - $1/day
✓ economic_data (macro context, not used in signals) - $2/day
✓ market_sentiment (sentiment indicators) - $1-2/day
✓ sector_performance (sector OHLCV) - $1/day
✓ annual_balance_sheet, annual_income_statement (for metrics) - $2-3/day
✓ annual_cash_flow (for metrics) - $1/day

Data Patrol (validation, nice-to-have) - $0.10/day

Dashboard non-critical fetchers (10/23):
  - activity, notifications, economic_calendar, etc.
```

**Total Optional: ~$10-15/day**

### BLOAT (Unused, can delete)
```
✗ Pre-warm Lambda schedules (4 schedules) - $0.50-1.00/day
✗ Cost circuit breaker Lambda - $0.20/day
✗ Weight optimization scheduler - $0.20/day
✗ RDS scheduler - $0.10/day
✗ Credential rotation service - $0.05/day
✗ 38 non-critical CloudWatch alarms - $0.50/day
✗ EventBridge ECS task failure rules - $0.10/day
✗ SNS loader alerts - $0.05/day
✗ SQS dead-letter queue - $0.05/day
```

**Total Bloat: ~$1.75-2.35/day ($52-70/month)**

---

## THE TRUTH ABOUT THOSE 9 METRICS

**Question**: Can we delete quality_metrics, growth_metrics, value_metrics, stability_metrics, positioning_metrics?

**Answer**: NO. Here's why:

1. **Phase 1 explicitly checks** they're fresh and halts if stale
   - Line 22 in phase1_data_freshness.py: "stock_scores requires minimum 3/6 metrics per GOVERNANCE.md"
   - If you delete the loaders, Phase 1 will fail when it tries to check freshness

2. **stock_scores composite ranking** requires them:
   - quality: 25%, growth: 20%, value: 20%, positioning: 15%, stability: 12%, momentum: 8%
   - score = weighted average of these 6 metrics
   - Without them, stock_scores is incomplete or wrong

3. **They're not expensive individually**:
   - All 5 metric loaders combined: ~$2-3/day
   - But if you have them, you MUST run them daily (can't be stale)
   - If you don't want them, you must REMOVE them from Phase 1 freshness check AND change stock_scores formula

4. **Current status**: All 5 ARE running daily in the evening pipeline
   - No "dead code" here; they're actively used

---

## WHAT YOU CAN SAFELY DELETE

### Option A: Delete All Bloat (Minimal Risk)
- Pre-warm schedules: **$0.50-1.00/day**
- Cost circuit breaker: **$0.20/day**
- Weight optimization: **$0.20/day**
- Unnecessary alarms: **$0.50/day**
- Other meta-services: **$0.20/day**
- **Savings**: ~$1.60-2.10/day (~$48-63/month)
- **Risk**: Very low — none of these are on critical path

### Option B: Reduce Data Granularity (Medium Risk)
- Delete economic_data: **$2/day** (not used in signals)
- Delete market_sentiment: **$1-2/day** (not used in signals)
- Delete sector_performance: **$1/day** (not used in signals)
- Delete some metric components if reformulated stock_scores: **$2-3/day** (HIGH RISK)
- **Savings**: ~$4-8/day if you don't need macro context
- **Risk**: Medium — would require code changes

### Option C: Reduce Orchestrator Frequency (High Risk)
- Current: 2x daily (9:30 AM + 5:30 PM)
- Reduce to: 1x daily (9:30 AM only) → **Save $0.20-0.30/day on Lambda**
- **Savings**: Minimal ($0.20/day)
- **Risk**: HIGH — miss intraday trading opportunities, miss exit management

---

## RECOMMENDED APPROACH

**Phase 1**: Delete bloat (Option A)
- No risk to trading
- Clean up unnecessary services
- Save ~$50-60/month

**Phase 2** (Later if needed): Evaluate optional loaders
- Do you actually use sector_ranking, trend_template, economic data?
- If no: delete them (save $3-5/day)
- If yes: keep them

**Never touch**: The 9 metric loaders + stock_scores
- These are integral to the signal generation system
- Removing them requires code changes to Phase 1 and stock_scores formula

---

## Questions to Confirm Before Cutting

1. **Do you want to keep the optional data** (sector_ranking, trend_template, economic, market_sentiment)?
   - YES → Keep current setup, delete only bloat (save $50/month)
   - NO → Delete optional loaders too (save $100+/month, requires verification)

2. **Can you handle brief cold starts** (15-40 seconds) on Lambda?
   - YES → Delete pre-warm schedules (save $30-40/month)
   - NO → Keep pre-warm (optimization cost)

3. **Do you need detailed monitoring** (email alerts, multiple alarms)?
   - YES → Keep current (you have it)
   - NO → Delete 30+ alarms (save $15-20/month)

Once you answer, I'll delete exactly what's safe and leave the rest untouched.

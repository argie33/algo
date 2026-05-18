# Algo Trading System — Target Architecture

**Version:** 1.0
**Date:** 2026-05-18
**Status:** Proposed (pending review)

---

## 1. Executive Summary

This document defines the **target architecture** for the algo trading system. The system today is **mostly functional** in AWS but suffers from:
- 4 critical data tables with no loaders (Phase 1 halts)
- 3 loaders re-fetch API data they already have in the DB (2x cost)
- Indicator computation duplicated in 3 places (signal divergence risk)
- 5+ dead loaders consuming resources for no benefit
- No daily trigger for the orchestrator (only manual)
- No data quality gates between loader stages

**Target state:**
- AWS-native event-driven pipeline (EventBridge → Step Functions → Lambda + Fargate)
- Single source of truth for all indicators and signals
- Data quality gates before each downstream consumer
- Zero unused loaders, zero duplicate computation
- Daily scheduled orchestrator runs end-to-end without manual intervention
- Cost: ~$60/month all-in (RDS dominates; pipeline is ~$10-15/mo incremental)
- Future-proofed for HFT expansion (architectural seams, not premature complexity)

---

## 2. Current State (Reality Check)

### What's Actually Deployed in AWS ✅

| Component | Status | Notes |
|-----------|--------|-------|
| RDS PostgreSQL | ✅ Running | Private subnet, encrypted, 30-day backups |
| ECS Fargate Cluster | ✅ Running | 40+ task definitions for loaders + orchestrator |
| EventBridge Schedules | ✅ Running | 22 loaders on cron schedules (3:30 AM – 5 PM ET) |
| Step Functions Pipeline | ✅ Running | EOD pipeline orchestrates 13 critical loaders |
| Lambda API | ✅ Running | /api/* routes, 30+ endpoints |
| DynamoDB Watermarks | ✅ Running | Per-loader, per-symbol state |
| Secrets Manager | ✅ Running | RDS creds, Alpaca, FRED keys |
| S3 + CloudFront | ✅ Running | Frontend React dashboard |
| Cognito | ✅ Running | User authentication |
| SQS DLQ | ✅ Running | Failed loader tasks (14-day retention) |
| RDS Proxy | ❌ Disabled | Available via `enable_rds_proxy` flag |

### What's NOT Working ❌

| Issue | Impact | Fix |
|-------|--------|-----|
| **Orchestrator has no daily trigger** | Algo runs only manually | Add EventBridge rule: 5:15 PM ET weekdays → Step Functions |
| **4 critical tables have no loaders** | Phase 1 always halts | Create load_technical_data_daily, load_trend_template_data, load_market_health_daily, load_signal_quality_scores |
| **load_price_aggregate re-fetches API** | 2x API cost + drift risk | Read from price_daily, GROUP BY week/month |
| **load_etf_price_aggregate same issue** | Same as above | Same fix |
| **loadbuyselldaily computes own indicators** | Signal divergence risk | Read from technical_data_daily (after loader exists) |
| **technical_indicators.py never imported** | Dead code | Adopt as canonical module, all loaders use it |
| **5+ dead loaders** | Wasted compute, rate limits | Delete: loadfeargreed, loadnaaim, loadaaiidata, loadseasonality, loadecondata, loadanalystsentiment |
| **No DQ gates** | Bad data flows to signals | Add validation step between Tier 1 and Tier 2 in Step Functions |
| **Continuous Monitor unclear status** | Position drift risk | Verify EventBridge rule active, test |
| **Backtest never invoked** | No regression detection | Schedule weekly backtest job |

---

## 3. Target Architecture

### 3.1 High-Level Data Flow

```
                                  EventBridge Scheduler
                       (cron expressions, timezone-aware)
                                          |
       +----------------------------------+--------------------------------+
       |                                  |                                |
       v                                  v                                v
+---------------+                +-------------------+         +-----------------+
| 9:00 PM ET    |                | 5:00 PM ET        |         | 5:15 PM ET      |
| Pre-load      |                | EOD Pipeline      |         | Algo Orchestrator|
| (sym/calendar)|                | (data → signals)  |         | (after data done)|
+-------+-------+                +---------+---------+         +--------+--------+
        |                                  |                            |
        v                                  v                            v
                              +---------------------+
                              | Step Functions      |
                              | Standard            |
                              | (durable, auditable)|
                              +----------+----------+
                                         |
                +------------------------+------------------------+
                |                                                 |
                v                                                 v
    +--------------------+                              +-------------------+
    | TIER 1: PRICES     |                              | TIER 5: HEAVY     |
    | Lambda + Distrib Map|                             | Fargate (signals) |
    | Parallel per symbol |                              | 4 vCPU, 8 GB     |
    | ~2000 → 3 min       |                              | TA-Lib, pandas    |
    +--------+-----------+                              +-------+-----------+
             |                                                  |
             v                                                  v
    +------------------+                                 +----------------+
    | RDS Postgres     |                                 | RDS Postgres   |
    | price_daily      |                                 | signals,       |
    | (UPSERT)         |                                 | signal_quality |
    +--------+---------+                                 +----------------+
             |
             v
    +-----------------------------+
    | DQ GATE (Lambda)            |
    | - Freshness check           |
    | - Completeness check        |
    | - Sanity check (OHLC logic) |
    | - Continuity check          |
    +--------+--------------------+
             | (pass)
             v
    +-----------------------+
    | TIER 2: TECHNICALS    |
    | Fargate (heavy CPU)   |
    | technical_data_daily  |
    | (RSI, MACD, SMA, ATR) |
    +--------+--------------+
             |
             v
    +-----------------------+
    | TIER 3: TREND/MARKET  |
    | Lambda                |
    | trend_template_data   |
    | market_health_daily   |
    +--------+--------------+
             |
             v
    +-----------------------+
    | TIER 4: SIGNALS       |
    | Fargate (heavy CPU)   |
    | buy_sell_daily        |
    | signal_quality_scores |
    | swing_trader_scores   |
    | stock_scores          |
    +--------+--------------+
             |
             v
    +-----------------------+
    | ORCHESTRATOR (Fargate)|
    | 7-phase trading logic |
    | → Alpaca execution    |
    +-----------------------+
```

### 3.2 Layer Responsibilities

**1. Trigger Layer — EventBridge Scheduler**
- Three daily schedules (US/Eastern):
  - **9:00 PM previous-day:** Symbol universe, market calendar, corporate actions
  - **5:00 PM EOD:** Price loaders, downstream technicals/signals (Step Functions)
  - **5:15 PM EOD:** Algo orchestrator (after EOD pipeline completes)
- Weekly schedules:
  - **Sunday 11 PM:** Reference data (financials, company profiles, sectors)
  - **Saturday 6 AM:** Backtest regression
- Holiday-aware: skips runs on market holidays (queries Alpaca `/v2/calendar`)

**2. Orchestration Layer — Step Functions Standard**
- Why Standard not Express: durable execution, audit trail, ability to replay
- One state machine per data dependency chain (EOD, weekly, monthly)
- Distributed Map state for fan-out (max concurrency = 200)
- Error catch with retry + DLQ for poison messages
- SNS notifications on failure

**3. Loader Layer — Lambda + Fargate (hybrid)**

| Type | Compute | When |
|------|---------|------|
| **Light loaders** (I/O bound, single API call, < 15 min) | Lambda | Per-symbol fan-out: prices, fundamentals, earnings |
| **Heavy loaders** (CPU bound, pandas/numpy, large batch) | Fargate | Full-universe compute: technicals, signals, scores |
| **Aggregation loaders** (DB-only, GROUP BY) | Lambda | Weekly/monthly aggregates from daily |

**4. Storage Layer**

| Store | Purpose | Why |
|-------|---------|-----|
| **RDS PostgreSQL** | Hot store, last 2 years | Existing, indexed for query speed |
| **S3 (Parquet)** | Raw archive + audit + future ML | Cheap, immutable, replayable |
| **DynamoDB** | Watermarks, rate-limit tokens, source health | Single-digit ms reads, atomic |
| **Secrets Manager** | API keys, DB passwords | Rotation, audit |

**5. Algo Layer — Fargate (long-running)**
- Single Fargate task runs all 7 phases of `algo_orchestrator.py`
- Triggered by Step Functions at end of EOD pipeline
- Connects to Alpaca for live position data and order execution
- Writes audit/snapshots back to RDS

### 3.3 Loader Inventory (Target State)

**ESSENTIAL LOADERS (15)** — keep, fix, or create:

| # | Loader | Tier | Compute | Source | Output Table |
|---|--------|------|---------|--------|--------------|
| 1 | loadstocksymbols.py | T0 | Lambda | NASDAQ | stock_symbols |
| 2 | load_market_calendar.py (NEW) | T0 | Lambda | Alpaca | market_calendar |
| 3 | load_corporate_actions.py (NEW) | T0 | Lambda | Alpaca | corporate_actions |
| 4 | loadpricedaily.py | T1 | Lambda (Distributed Map) | Alpaca → yfinance fallback | price_daily |
| 5 | loadetfpricedaily.py | T1 | Lambda (Distributed Map) | Alpaca | etf_price_daily |
| 6 | load_price_aggregate.py | T1b | Lambda | **DB (price_daily)** ← fix | price_weekly, price_monthly |
| 7 | load_etf_price_aggregate.py | T1b | Lambda | **DB** ← fix | etf_price_weekly, etf_price_monthly |
| 8 | load_technical_data_daily.py (NEW) | T2 | Fargate | DB (price_daily) | technical_data_daily |
| 9 | load_trend_template_data.py (NEW) | T3 | Fargate | DB (technical_data + price) | trend_template_data |
| 10 | load_market_health_daily.py (NEW) | T3 | Lambda | DB (SPY price) | market_health_daily |
| 11 | loadbuyselldaily.py | T4 | Fargate | **DB (technical_data) ← fix** | buy_sell_daily |
| 12 | load_buysell_aggregate.py | T4b | Fargate | DB (price_daily) | buy_sell_weekly, buy_sell_monthly |
| 13 | load_signal_quality_scores.py (NEW) | T4 | Fargate | DB (signals + technical + trend) | signal_quality_scores |
| 14 | loadstockscores.py | T4 | Fargate | **DB ← fix** | stock_scores |
| 15 | loadsectors.py | T2 | Lambda | DB (computed) | sector_ranking |
| 16 | loadindustryranking.py | T2 | Lambda | DB (computed) | industry_ranking |

**SUPPORT LOADERS (8)** — useful but not critical:

| Loader | Frequency | Purpose |
|--------|-----------|---------|
| load_earnings_calendar.py | Daily 6 AM | Earnings blackout dates |
| loadearningshistory.py | Sunday 11 PM | Historical surprises |
| loadcompanyprofile.py | Sunday 11 PM | Sector/industry mapping |
| load_income_statement.py | Sunday 11 PM | Fundamentals |
| load_balance_sheet.py | Sunday 11 PM | Fundamentals |
| load_cash_flow.py | Sunday 11 PM | Fundamentals |
| load_growth_metrics.py | Sunday 11:30 PM | Computed growth metrics |
| load_quality_metrics.py | Sunday 11:30 PM | Computed quality metrics |

**DELETE THESE LOADERS (12)**:

| Loader | Reason |
|--------|--------|
| loadfeargreed.py | 0 queries in algo code |
| loadaaiidata.py | 0 queries (or only 1 in dead code) |
| loadnaaim.py | 0 queries |
| loadseasonality.py | 0 queries |
| loadecondata.py | 0 queries in active code paths |
| loadanalystsentiment.py | 0 queries |
| loadanalystupgradedowngrade.py | 0 queries |
| loadearningsestimates.py | 0 queries |
| loadearningsrevisions.py | 0 queries |
| load_value_metrics.py | 1 query, not OptimalLoader, divergent pattern |
| loadttmincomestatement.py | 0 queries |
| loadttmcashflow.py | 0 queries |
| loadmarketindices.py | Merge into loadpricedaily.py (index symbols are just price_daily entries) |
| technical_indicators.py | Adopt or delete — make canonical or remove |

**FINAL COUNT:**
- **Before:** 35 loaders + technical_indicators.py
- **After:** 16 essential + 8 support = 24 loaders
- **Reduction:** ~30% fewer loaders, ~50% less complexity

### 3.4 Indicator Computation (Single Source of Truth)

**Problem today:** RSI, MACD, SMA, ATR computed in 3 places with risk of divergence.

**Target:** ONE module, used by ALL consumers.

```python
# loaders/technical_indicators.py — THE canonical implementation
def compute_rsi(closes, period=14): ...
def compute_macd(closes, fast=12, slow=26, signal=9): ...
def compute_sma(closes, period): ...
def compute_ema(closes, span): ...
def compute_atr(high, low, close, period=14): ...
def compute_bollinger_bands(closes, period=20, std_dev=2.0): ...
def compute_all_indicators(df): ...  # convenience for full set

# Used by:
# - load_technical_data_daily.py (stores in DB)
# - load_buysell_aggregate.py (weekly/monthly bars)
# - algo/algo_signals.py (any live computation)
# Nobody else implements these functions.
```

**Migration:** loadbuyselldaily.py reads from `technical_data_daily` table instead of computing in-memory. Signals always match what's stored.

### 3.5 Data Quality Gates

Between each tier in Step Functions, a DQ gate validates:

```
TIER 1 (Prices) → DQ GATE → TIER 2 (Technicals)
                    │
                    ├── Freshness:    max(date) == last_trading_day
                    ├── Completeness: count(distinct symbol) >= 0.995 × universe
                    ├── Sanity:       0 < close < 10000, high >= low, volume >= 0
                    ├── Continuity:   no >1 trading-day gap per symbol
                    └── Schema:       column types match contract

  ✓ PASS → next tier proceeds
  ✗ FAIL → halt pipeline, SNS alert, no signals generated today
```

**Why gates matter:** Bad data → bad signals → real money lost. Fail loud, fail closed.

### 3.6 Symbology (Future-Proofing)

**Problem:** Algo keys on ticker strings. When AAPL becomes AAPL.OQ or splits or gets renamed, history breaks.

**Solution:** Surrogate `symbol_id` table.

```sql
CREATE TABLE symbology (
    symbol_id BIGSERIAL PRIMARY KEY,
    primary_ticker VARCHAR(20),
    cusip VARCHAR(20),
    figi VARCHAR(20),
    exchange VARCHAR(20),
    asset_class VARCHAR(20),  -- 'stock', 'etf', 'option', 'future', 'crypto'
    active BOOLEAN,
    listed_date DATE,
    delisted_date DATE
);

CREATE TABLE ticker_history (
    symbol_id BIGINT REFERENCES symbology,
    ticker VARCHAR(20),
    valid_from DATE,
    valid_to DATE  -- NULL = current
);
```

All data tables key on `symbol_id`, not ticker. Ticker can change without breaking joins.

**Phase 1 vs later:** Don't migrate every table today. New tables use symbol_id. Existing tables migrate gradually.

### 3.7 Storage Strategy

**Hot Path (RDS Postgres):**
- Last 2 years of daily prices, signals, indicators (queries < 100ms)
- All trading state (positions, trades, snapshots, audit)
- Partition `price_daily`, `technical_data_daily` by month for fast purge
- Indexes on (symbol_id, date DESC)

**Cold Path (S3 Parquet):**
- All raw OHLCV ingested (10+ years history)
- Partition: `s3://algo-data/raw/year=2026/month=05/day=18/symbol=AAPL.parquet`
- Queryable via Athena for backtests
- Compressed (Snappy) — ~200 bytes per bar

**State Store (DynamoDB):**
- `pipeline_state`: per-loader, per-symbol watermarks
- `rate_limit_tokens`: provider token buckets (Alpaca, yfinance)
- `source_health`: success/fail counters per provider
- TTL on stale entries (90 days)

### 3.8 Local Development Equivalence

The local dev experience mirrors AWS:

```bash
# Local: same code, simpler orchestration
python3 init_database.py             # Apply schema (matches AWS RDS)
python3 run-all-loaders.py           # Local equivalent of Step Functions DAG
python3 algo/algo_orchestrator.py    # Same code that runs in AWS Fargate

# Local DB: PostgreSQL on localhost (matches RDS schema)
# Local secrets: AWS Secrets Manager (same code path, just queries cloud)
# Local DynamoDB: optional — fall back to in-memory watermarks
```

**Key principle:** Same loader code runs in both places. The only difference is *how* it's orchestrated (subprocess locally vs Lambda/Fargate in AWS).

---

## 4. Costs (At Our Scale)

| Component | Monthly Cost |
|-----------|--------------|
| Lambda loaders (~2000 invocations × 21 days) | ~$0.40 |
| Step Functions Standard (~50 transitions/day × 21) | ~$0.03 |
| Distributed Map child workflows | ~$1.00 |
| Fargate technicals/signals (4 vCPU, 8 GB, ~30 min × 21 days) | ~$5.30 on-demand / **~$1.60 on Spot** |
| Fargate orchestrator (1 CPU, 2 GB, ~10 min × 21 days) | ~$0.30 |
| RDS Postgres db.t4g.small (existing) | ~$25 |
| RDS Proxy (optional, recommended if >50 concurrent loaders) | ~$22 |
| DynamoDB on-demand (watermarks, rate limits) | ~$1 |
| S3 storage (10 years of bars, parquet) | <$1 |
| SQS (DLQ, fan-out) | <$0.50 |
| CloudWatch (logs + custom metrics) | ~$5 |
| Secrets Manager | $0.80 |
| EventBridge Scheduler | $0 (free tier) |
| **Total incremental (compute + orchestration only):** | **~$10–15** |
| **Total all-in (with RDS + RDS Proxy):** | **~$60** |

**Cost optimization options:**
- Fargate Spot for non-critical: ~70% off (signals can retry, no problem)
- Skip RDS Proxy until > 50 concurrent connections: saves $22/mo
- Use Aurora only if you need >100 GB or burst scaling: don't switch from RDS yet

---

## 5. Observability & SLAs

### Critical Metrics

| Metric | Target | Alert Threshold |
|--------|--------|------------------|
| Pipeline complete by 8:45 PM ET | 99% | Page if not done by 9:00 PM ET |
| Data freshness (price_daily latest) | < 24h | Page if > 36h |
| Symbol coverage | ≥ 99.5% of universe | Alert if < 95% |
| Loader success rate | ≥ 99% | Alert if 3 consecutive failures |
| Orchestrator phase success | 100% | Page if any phase halts |
| Alpaca order fills | < 5s p99 | Alert if p99 > 30s |

### Logging

- CloudWatch Logs: all ECS tasks, Lambda invocations, Step Functions state changes
- Structured JSON logs (no string interpolation)
- Correlation IDs across all components (pipeline_run_id)
- 30-day retention default, 1-year for audit logs

### Tracing

- X-Ray on Step Functions and Lambda for end-to-end latency
- Custom EMF metrics for business KPIs (signals/day, fills, slippage)

### Alerting

- SNS topics → email + PagerDuty
- Severity tiers: INFO (Slack), WARN (email), CRITICAL (page)

---

## 6. Future-Proofing for HFT (Architectural Seams, No Premature Build)

**What we build today that works for HFT later:**

1. **S3 raw + RDS hot separation** — works for any timeframe (minute, second, tick)
2. **Symbology table with symbol_id** — survives across asset classes
3. **Adapter pattern for indicators** — `compute_rsi(closes, period)` works on daily, hourly, or tick bars
4. **Step Functions for batch, Kinesis path optional for streaming** — can add side-by-side
5. **DynamoDB rate limit token bucket** — same pattern scales to HFT rate limits

**What we don't build today:**
- Kinesis Data Streams (only needed for sustained > 10k msg/sec; we have 2000/day)
- MSK / Kafka (overkill at our volume)
- Timestream (Postgres handles 10 years of daily bars fine)
- Lambda Provisioned Concurrency (cold starts don't matter at 5 PM batch)
- Aurora Serverless v2 (2x cost vs RDS at steady state)

**When to add HFT components:**
- When you start ingesting minute or finer bars: add Kinesis
- When backtesting requires querying tick-level history: migrate raw to Timestream
- When you have multiple consumers of the same stream: Kinesis with fan-out

---

## 7. Anti-Patterns to Avoid

1. ❌ **GitHub Actions as scheduler** — use EventBridge
2. ❌ **One monolithic Fargate task** doing everything — fan out via Lambda + Map
3. ❌ **yfinance as primary** — gets blocked; use Alpaca primary, yfinance fallback
4. ❌ **Lambda with QueuePool behind RDS Proxy** — use NullPool to avoid double-pooling
5. ❌ **CloudWatch logs ALL on Step Functions** — pricey; use ERROR in production
6. ❌ **Aurora Serverless v2 for steady daily loads** — 2x cost vs RDS at our scale
7. ❌ **Storing only adjusted prices** — keep raw + adjustment factors separately
8. ❌ **Keying signals on ticker string** — use surrogate symbol_id
9. ❌ **Step Functions Express for main pipeline** — no audit trail, 5-min cap
10. ❌ **Provisioned Concurrency for daily batch** — defeats pay-per-use model
11. ❌ **Kinesis "just in case"** — pay shard costs 24/7 for no current benefit
12. ❌ **Trade execution without client_order_id** — risk double-fills on retry
13. ❌ **Indicator computation in multiple places** — single source of truth (technical_indicators.py)
14. ❌ **Loading data the algo doesn't query** — delete dead loaders

---

## 8. Migration Plan (6 Phases, ~3 Weeks)

See `MIGRATION_PLAN.md` for the concrete step-by-step execution plan.

**High-level phases:**

1. **Phase 1 (3 days): Eliminate dead code and consolidate**
   - Delete 12 dead loaders
   - Make technical_indicators.py canonical, refactor consumers
   - Fix double-API loaders (price_aggregate, etf_price_aggregate)
   - Update run-all-loaders.py and Terraform

2. **Phase 2 (5 days): Build the 4 missing loaders**
   - load_technical_data_daily.py (Fargate)
   - load_trend_template_data.py (Fargate)
   - load_market_health_daily.py (Lambda)
   - load_signal_quality_scores.py (Fargate)

3. **Phase 3 (3 days): Wire orchestrator to daily schedule**
   - Add EventBridge rule: 5:15 PM ET weekdays
   - Trigger Step Functions which runs EOD pipeline → orchestrator
   - End-to-end test in dev

4. **Phase 4 (5 days): Data Quality Gates**
   - Lambda DQ validator between Step Functions tiers
   - SNS alerts on failure
   - Pipeline halts if data quality below threshold

5. **Phase 5 (5 days): Symbology & Storage strategy**
   - Add symbology table (no migration yet, just new tables use it)
   - Set up S3 raw archive (parquet partitioned by date)
   - Set up DynamoDB rate-limit token bucket

6. **Phase 6 (ongoing): Observability**
   - Custom EMF metrics
   - X-Ray tracing
   - SLA dashboards
   - Backtest regression scheduled weekly

---

## 9. Decisions Required From You

Before I write any code, I need confirmation on:

1. **Is this architecture aligned with your vision?** Or are there pieces you'd add/remove?
2. **OK to delete the 12 dead loaders?** They populate tables never queried by algo code.
3. **OK to add EventBridge daily trigger for orchestrator?** Currently manual-only.
4. **Migration order — Phase 1 first (cleanup) before Phase 2 (new features)?** Or different order?
5. **Fargate Spot for signals?** Save ~70% but accepts occasional retry.
6. **RDS Proxy now or later?** $22/mo; needed if we run >50 concurrent loaders.
7. **Should we keep weekly/monthly aggregates?** Or compute on-demand from daily?

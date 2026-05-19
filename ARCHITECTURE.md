# System Architecture

Target: Real-time algorithmic trading platform running 24/7 on AWS with 50+ market data sources feeding an orchestrator that calculates signals, filters risk, and executes trades.

## Core Design Decisions

### Orchestration Engine
- **Scheduler:** EventBridge Scheduler (not GitHub Actions) — fine-grained cron control, no polling
- **Orchestrator:** Step Functions Standard (not Express) — long-running stateful workflows, audit trail
- **Entry:** `python3 algo/algo_orchestrator.py` (live trades) or `--dry-run` (dry run)

### Compute Strategy
- **Lambda:** I/O-bound loaders < 15 min runtime (price, ETF, fundamentals, economic data)
- **Fargate:** CPU-heavy workloads (technical indicators, signal generation, market health, trend patterns)
- **RDS Proxy:** If > 50 concurrent loaders (auto-scale connection pool)

### Data Strategy
- **RDS Postgres:** Hot data (daily OHLCV, signals, positions, trades) — primary query path
- **S3 Parquet:** Raw archive (all historical prices) — backup + auditing
- **DynamoDB:** State tracking (watermarks, last-run timestamps) — fast rate-limit checks

### Data Sources (Primary/Fallback)
- **Alpaca** (primary) → yfinance (fallback for historical)
- **Fed Economic Data** (FRED) → economic indicators
- **Market Health** (SPY technicals, VIX, put/call ratios)
- **Earnings Calendar** (official sources only, not crowdsourced)

### Anti-Patterns Avoided
- ❌ GitHub Actions as scheduler (no fine-grained cron, poor error handling)
- ❌ Aurora Serverless v2 (2x cost at our scale, 5.8M daily rows)
- ❌ Kinesis (only needed > 10k msg/sec; we have ~2000/day)
- ❌ yfinance as primary (gets blocked by IP-based rate limits in AWS VPC)
- ❌ Ticker-string keys in DynamoDB (use symbol_id surrogate for consistency)

## Data Pipeline (50+ Loaders → RDS)

### Critical Path (Daily EOD)
1. **EodBulkPrices** — Load OHLCV from Alpaca/yfinance for all symbols
2. **ParallelTechnicals** — Read price_daily → compute RSI/MACD/SMA/ATR → write technical_data_daily
3. **ParallelEnrichment** — Read technical_data → compute Minervini/Weinstein patterns → trend_template_data
4. **SignalGeneration** — 6 parallel signal loaders (daily/weekly/monthly × stock/etf)
5. **AlgoMetrics** — Compute signal quality scores
6. **SwingScores** — Market-wide swing trader rank
7. **TriggerOrchestrator** — Invoke main orchestrator

### Data Schema (Key Tables)

| Table | Source | Frequency | Used By | Rows |
|-------|--------|-----------|---------|------|
| `price_daily` | Alpaca/yfinance | EOD | Technicals, trends | 5.8M |
| `technical_data_daily` | load_technical_data_daily | EOD | Filters, signals | 100K |
| `trend_template_data` | load_trend_template_data | EOD | Filters, ranking | 100K |
| `buy_sell_daily` | 6 signal loaders | EOD | Orchestrator | 100K |
| `market_health_daily` | load_market_health_daily | EOD | Circuit breaker | 500 |
| `swing_trader_scores` | load_swing_trader_scores | EOD | Ranking | 3000 |
| `stock_symbols` | load_stock_symbols | Weekly | Lookups | 3000 |
| `positions` | Orchestrator | Intraday | Monitor | Dynamic |
| `trades` | Orchestrator | Intraday | Audit | Dynamic |
| `feature_flags` | load_feature_flags | Manual | Orchestrator | ~10 |

## Loader Consolidation (40 → 24)

### Active Loaders (24 total)
**Essential (16):**
- load_price_daily (Alpaca daily + intraday)
- load_etf_price_daily (parallel)
- load_technical_data_daily (RSI/MACD/SMA/ATR)
- load_trend_template_data (Minervini/Weinstein)
- load_market_health_daily (VIX, SPY technicals, put/call)
- load_signal_quality_scores (composite SQS)
- load_swing_trader_scores (daily ranking)
- loadbuyselldaily (stock daily signals)
- loadbuyselletfdaily (ETF daily signals)
- loadbuyseluweekly (stock weekly signals)
- loadbuysellweekly_etf (ETF weekly signals)
- loadbuysellumonthly (stock monthly signals)
- loadbuyselumonthly_etf (ETF monthly signals)
- load_stock_symbols (ticker master list)
- load_feature_flags (feature switches)
- load_earnings_calendar (earnings dates)

**Support (8):**
- load_sector_rotation (sector relative strength)
- load_etf_holdings (sector exposure)
- load_option_chain (put/call implied vol)
- load_volatility_term_structure (vol curves)
- load_commodity_prices (crude, gold, DXY)
- load_macro_indicators (GDP, inflation, unemployment)
- load_credit_spreads (HY/IG spreads)
- load_crypto_price (BTC/ETH only, for diversification)

### Deleted Loaders (16)
- ❌ loadetfpricedaily (superseded by load_etf_price_daily)
- ❌ fear_greed_index (crowdsourced, unreliable)
- ❌ AAII_sentiment (crowdsourced, lag)
- ❌ NAAIM_exposure (crowdsourced)
- ❌ seasonality_data (not actionable)
- ❌ econ_indicators (duplicates load_macro_indicators)
- ❌ earnings_estimates (unreliable)
- ❌ earnings_revisions (unreliable)
- ❌ value_metrics (not used by filters)
- ❌ ttm_squeeze (duplicates technical_data)
- ❌ market_indices (only need SPY, in market_health)
- ❌ insider_transactions (compliance risk)
- ❌ institutional_flows (unreliable signal)
- ❌ sector_fundamentals (low priority)
- ❌ implied_moves (already have vol_term_structure)
- ❌ alpha_vantage (rate-limited, slow)

### Still To Implement (4 Loaders)
1. **load_technical_data_daily** — Compute RSI/MACD/SMA/ATR for all symbols from price_daily
   - Runtime: 5-10 min (Fargate)
   - Writes: technical_data_daily (100K rows)
   
2. **load_trend_template_data** — Detect Minervini/Weinstein chart patterns
   - Runtime: 10-15 min (Fargate)
   - Reads: price_daily, technical_data_daily
   - Writes: trend_template_data (100K rows)
   
3. **load_market_health_daily** — Market-wide health metrics (VIX, SPY technicals, put/call ratios)
   - Runtime: 2-3 min (Lambda)
   - Writes: market_health_daily (500 rows)
   
4. **load_signal_quality_scores** — Composite scoring across all signal generators
   - Runtime: 3-5 min (Fargate)
   - Reads: buy_sell_daily + all signal tables
   - Writes: signal_quality_scores (100K rows)

## Orchestrator Integration

### Daily Trigger (EventBridge)
```
EventBridge Rule: "algo-eod-trigger-dev"
Schedule: "cron(0 22 ? * MON-FRI)" (5 PM ET weekdays)
Target: Step Functions State Machine (algo-eod-pipeline-dev)
```

### Orchestrator Phases
1. **Validate** — Check database connectivity, required tables, data freshness
2. **Load** — Fetch latest market data via loaders
3. **Calculate** — Run signal pipeline (50+ indicators)
4. **Filter** — Apply risk filters (circuit breaker, liquidity, earnings blackout, sector rotation)
5. **Position** — Size positions based on Kelly criterion, volatility, portfolio risk
6. **Execute** — Place orders via Alpaca API
7. **Reconcile** — Verify fills, update position tracking, alert on discrepancies

## Deployment Pipeline

### Current State (Manual)
- Terraform configures AWS infra (RDS, Fargate, Lambda, Step Functions)
- Code pushed to main, manually triggered via AWS Console or CLI
- No CI/CD automation

### Target State
- GitHub Actions on push to main:
  1. Run type checking: `pyright algo/`
  2. Run tests: `pytest tests/ -v`
  3. Build + push Lambda deployment packages to S3
  4. Update Step Functions state machine definition
  5. Update Fargate task definitions (ECR image)
  6. Run smoke test (dry-run orchestrator)

## Infrastructure Cost

- **RDS Postgres:** ~$50/month (dominates)
- **Fargate compute:** ~$8/month (5 × 10-min tasks/day)
- **Lambda:** ~$1/month (50+ short-lived invocations)
- **Step Functions:** ~$0.50/month (1 execution/day)
- **EventBridge:** <$1/month (1 rule, ~30 invocations/day)
- **S3 archive:** ~$2/month (60 GB cold storage)
- **DynamoDB:** <$1/month (sparse table)

**Total:** ~$60/month all-in (~$10-15 incremental compute + orchestration)

## Implementation Roadmap (Phase-Based)

### Phase 1: Cleanup (3 days)
- Delete 12 superseded loaders
- Consolidate technical_indicators.py → single source of truth
- Verify all remaining loaders in run-all-loaders.py + Terraform

### Phase 2: Build Missing Loaders (5 days)
- Implement load_technical_data_daily (Fargate)
- Implement load_trend_template_data (Fargate)
- Implement load_market_health_daily (Lambda)
- Implement load_signal_quality_scores (Fargate)
- Wire all 4 into run-all-loaders.py and Terraform

### Phase 3: Wire Orchestrator Trigger (3 days)
- Create EventBridge rule for daily 5 PM ET trigger
- Point to Step Functions algo-eod-pipeline-dev
- Test dry-run execution
- Verify data freshness in RDS

### Phase 4: Data Quality Gates (5 days)
- Add row-count validation between loader stages
- Add column-presence checks (no NULL where shouldn't be)
- Add version tracking in DynamoDB (loader version + timestamp)
- Alert on pipeline stage failures

### Phase 5: Symbology + Audit Trail (5 days)
- Migrate to symbol_id surrogate key everywhere
- Archive all historical prices to S3 Parquet
- Implement immutable append-only audit log

### Phase 6: Observability + Backtest (Ongoing)
- CloudWatch dashboards for pipeline stages
- SNS alerts for failures
- Implement backtesting framework (walk-forward, Sharpe ratio)
- Performance tracking vs. live results

## API Contract (25+ Endpoints)

See API_CONTRACT.md for full OpenAPI spec. Key endpoints:

```
GET  /health                  — System status
GET  /api/prices/:symbol      — Historical prices
GET  /api/signals/:symbol     — Buy/sell signals
GET  /api/positions           — Open positions
GET  /api/trades              — Trade history
POST /api/simulate/:symbol    — Backtest signal
```

## Future-Proofing (No Premature Build)

**These architectural seams survive HFT migration without rewrite:**
- S3 raw + RDS hot separation → works for any timeframe (minute, second)
- symbol_id surrogate → handles any asset class (stocks, crypto, commodities, forex)
- Indicator adapter pattern → scales to any bar timeframe
- DynamoDB rate-limit pattern → survives 10x volume

**What to add LATER (not now):**
- Kinesis: Only when streaming minute or finer bars
- Timestream: Only when querying tick-level time-series
- MSK (Kafka): Only with multiple stream consumers

## Deployment Verification

After each deployment:
1. `python3 algo/algo_orchestrator.py --dry-run` — Full pipeline end-to-end
2. `SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE` — Data freshness
3. `curl https://api.example.com/api/health` — API availability
4. Check CloudWatch for loader stage failures

## See Also
- CLAUDE.md — Local development setup
- tests/ — Unit + integration test suite
- algo/algo_orchestrator.py — Main orchestrator entry point

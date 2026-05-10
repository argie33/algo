# Stock Analytics Platform — Tech Stack Overview

## 165 Python Modules (Organized by Function)

### Core Orchestration (The Brain)
- **algo_orchestrator.py** — Master 7-phase daily workflow (data → signals → exits → entries → reconciliation)
- **algo_config.py** — Configuration, market windows, position limits, risk thresholds
- **algo_market_calendar.py** — Market hours, holidays, trading windows

### Data Pipeline (Get Fresh Data)
- **algo_data_freshness.py** — Verify market data is recent enough
- **algo_data_patrol.py** — Monitor data quality, detect anomalies
- **algo_data_remediation.py** — Fix missing/bad data
- **data_source_router.py** — Route requests to yfinance/Alpaca/Polygon (with fallbacks)

### Signal Generation (What to Trade)
- **algo_filter_pipeline.py** — 5-tier signal filter (data quality → market health → trend → quality → portfolio)
- **algo_advanced_filters.py** — Momentum, quality, catalyst, risk analysis
- **algo_backtest.py** — Historical signal validation

### Risk Management (Don't Blow Up)
- **algo_circuit_breaker.py** — Kill switches (drawdown, daily loss, VIX, market stage)
- **algo_market_exposure.py** — Sector/market cap exposure tracking
- **algo_market_exposure_policy.py** — Concentration and correlation limits
- **algo_governance.py** — Position sizing, kelly criterion, leverage

### Trade Execution (Actually Trade)
- **algo_trade_executor.py** — Execute trades via Alpaca (with 11 production blockers)
- **algo_exit_engine.py** — Exit logic (trailing stops, time-based, Minervini breaks)
- **algo_continuous_monitor.py** — Real-time position monitoring

### Observability (Know What's Happening)
- **algo_alerts.py** — Critical alerts via SNS/email
- **algo_audit_log.py** — Audit trail of all decisions
- **algo_daily_reconciliation.py** — Daily P&L, portfolio snapshot
- **algo_market_events.py** — Earnings, splits, dividends tracking

### Infrastructure & Integration
- **FULL_BUILD_VERIFICATION.py** — End-to-end system check
- **algo_run_daily.py** — Local testing entry point
- **algo_dry_run_simulator.py** — Simulate trades without execution

### Data Loaders (18 official loaders only)
- **loadstocksymbols.py** — Universe of tradeable stocks
- **loadpricedaily.py, loadpriceweekly.py, loadpricemonthly.py** — OHLCV data
- **loadstockscores.py** — Technical indicators (RSI, MACD, etc.)
- **loadbuyselldaily.py** — Entry/exit signals
- **loadearningsrevisions.py, loadestimatedeps.py** — Earnings data
- **loadalpacaportfolio.py** — Account positions from Alpaca
- ETF equivalents (same pattern for SPY, QQQ, IWM, etc.)

### Database Integration
- **PostgreSQL tables** — 21M+ price rows, 19M+ technical indicators, 800k+ signals, 50+ trades with Alpaca sync
- **Automatic schema creation** on first Lambda run

### Frontend (Admin Dashboard)
- **webapp/frontend/src/pages/** — React components
  - DeepValueStocks.jsx — Generational value opportunities
  - PortfolioAnalytics.jsx — P&L, position tracking
  - SignalExplorer.jsx — Buy/sell signal analysis
  - MarketDashboard.jsx — SPY/QQQ/IWM trends, VIX, breadth
- **webapp/lambda/routes/stocks.js** — REST API (deep-value, signals, portfolio)

## Infrastructure (Terraform IaC)

**All infrastructure is managed exclusively by Terraform** — Infrastructure as Code (IaC) only.

### 9 Terraform Modules
1. **vpc** — VPC, subnets, security groups, VPC endpoints, bastion host
2. **compute** — ECS cluster, ECR registry, capacity providers, CloudWatch logs
3. **database** — RDS PostgreSQL, Secrets Manager, KMS encryption, parameter groups, monitoring
4. **iam** — IAM roles, policies, GitHub OIDC, service principals, trust policies
5. **storage** — S3 buckets (frontend, logs, data, artifacts), bucket policies, lifecycle
6. **loaders** — 40 ECS task definitions, EventBridge rules, CloudWatch log groups, DLQ
7. **services** — Lambda functions (API, Algo), API Gateway, CloudFront, Cognito, EventBridge Scheduler
8. **batch** — AWS Batch compute environments, job queues, auto-scaling, spot instances
9. **monitoring** — CloudWatch dashboards, metric alarms, log filters, SNS topics

### GitHub Workflows (Deploy Only)
- **deploy-all-infrastructure.yml** — Master orchestrator (Terraform apply only)

## Tech Choices

| Layer | Technology | Why |
|-------|-----------|-----|
| **Runtime** | Python 3.11 + Node.js 20 | Fast, async, ecosystem |
| **Database** | PostgreSQL 15 | ACID, complex queries, proven reliable |
| **Orchestration** | EventBridge Scheduler | Reliable, timezone-aware, cost-effective |
| **Compute** | Lambda + ECS Spot | Serverless for algo, batch for data loading |
| **Frontend** | React + Vite | Fast, modern, responsive |
| **Trading API** | Alpaca Paper Trading | Free paper account, fast fills, great API |
| **Data Sources** | yfinance + Alpaca + Polygon.io | Multi-source fallback for reliability |
| **IaC** | CloudFormation + Terraform (future) | Version-controlled, auditable |

## Key Entry Points for Development

1. **Local testing** — `algo_run_daily.py` (uses docker-compose.yml)
2. **AWS Lambda** — `template-algo-orchestrator.yml` → `lambda_function.py` (entry point for EventBridge)
3. **REST API** — `webapp/lambda/index.js` (Node.js Lambda)
4. **Data loaders** — ECS task definitions in `template-app-ecs-tasks.yml`
5. **Frontend** — `webapp/frontend/src/App.jsx`

## Architectural Foundation — Research Sources

Every algorithm decision traces to published research. This grounds all design choices in institutional best practices, not intuition.

### Canonical Research Stack

| Concept | Source | Implementation |
|---------|--------|-----------------|
| **8-point Trend Template** | Mark Minervini, *Trade Like a Stock Market Wizard* | All 8 criteria; threshold ≥7/8 |
| **4-Stage Analysis** | Stan Weinstein, *Secrets For Profiting* | 30-week MA + slope + price-vs-MA classification |
| **CAN SLIM Composite** | William O'Neil, *How to Make Money in Stocks* | Quality/growth/momentum factor weights |
| **Cup-with-Handle Stop** | O'Neil + Bulkowski pattern stats | Stop 1% below handle low |
| **Flat Base** | Minervini SEPA methodology | ≤15% depth, ≥5wk duration |
| **VCP** | Minervini signature pattern | 2-4 progressively tighter contractions |
| **3-Weeks-Tight** | IBD continuation pattern | 3 weekly closes within 1.5% |
| **High-Tight Flag** | IBD rare explosive pattern | 100%+ in 4-8wk + tight 1-3wk consolidation |
| **TD Sequential** | Tom DeMark, 1980s | 9-count exhaustion, perfected detection |
| **Power Trend** | Minervini | 20%+ in 21 trading days |
| **Mansfield RS** | Weinstein adaptation | (stock/SPY) / 52w MA(stock/SPY) − 1 |
| **Distribution Days** | IBD methodology | Close down 0.2%+ on volume above prior |
| **Follow-Through Days** | William O'Neil | Day 4-7 of attempt, +1.25% on rising volume |
| **Position Size 0.75%** | Minervini + Van Tharp | Range 0.5–1.0%, midpoint 0.75% |
| **Max 6 positions** | O'Neil/Minervini consensus | Concentration in best ideas |
| **Move stop to BE at +1R** | Curtis Faith, *Way of the Turtle* | Prevent whipsaws on normal volatility |
| **Chandelier 3×ATR** | LeBeau / Connors backtests | Trail in trending markets |
| **8-week rule** | O'Neil leading-stock studies | Hold winners up 20%+ in ≤3wk for 8 weeks |
| **Drawdown gates** | Minervini + CTA industry standard | -5/-10/-15/-20 cascade |
| **9-factor exposure** | IBD Big Picture + Zweig | Market regime classification |
| **Bracket orders** | Institutional best practice | Stop enforced even on system outage |
| **Multi-timeframe alignment** | Elder Triple Screen | 58% win when aligned vs 39% non-aligned |

**Conflict resolution:** When sources disagree, we pick the more conservative interpretation (e.g., Minervini's 30%+ above 52w low vs. looser variants).

### System Component Stack

**A. Signal Computer (`algo_signals.py`)**  
Canonical implementations of every published swing-trading signal. Methods: Minervini trend, Weinstein stage, base-type classification, VCP detection, TD Sequential, Mansfield RS, distribution days.

**B. Market Exposure (`algo_market_exposure.py`)**  
Quantitative regime score (0-100) from 9 weighted factors. Replaces naive "Stage 2 yes/no" with mathematical exposure classification. Hard vetoes cap exposure at 25-40% under severe conditions (DD ≥6, VIX >40, no follow-through days).

**C. Exposure Policy (`algo_market_exposure_policy.py`)**  
Maps exposure score to 5 action tiers:
- **Confirmed Uptrend (80-100%)**: 5 new entries/day, 1.0× risk
- **Healthy Uptrend (60-80%)**: 4 new entries/day, 0.85× risk
- **Pressure (40-60%)**: 2 new entries/day, 0.5× risk
- **Caution (20-40%)**: 1 new entry/day, 0.25× risk, halt new entries
- **Correction (0-20%)**: 0 new entries, 0.0× risk, force exit losers

**D. Swing Score (`algo_swing_score.py`)**  
Multi-factor composite (0-100, A+ to F): 25% setup quality, 20% trend quality, 20% momentum/RS, 12% volume, 10% fundamentals, 8% sector, 5% multi-timeframe.

Hard gates: Trend ≥7/8, Stage 2, ≤25% from 52w high, base count ≤3, no wide-loose base, no earnings within 5 days.

**E. Filter Pipeline (`algo_filter_pipeline.py`)**  
6-tier selection: Data quality → Market health → Trend template → Signal quality → Portfolio health → Advanced filters. Ranked by swing score. Final entry count limited by exposure tier.

**F. Position Sizer (`algo_position_sizer.py`)**  
Risk-based sizing: `risk_dollars = portfolio_value × 0.75% × drawdown_adjustment × market_exposure × stage_phase`. Capped at 15% per position and concentration limits.

**G. Trade Executor (`algo_trade_executor.py`)**  
Idempotent bracket-order execution to Alpaca. Blocks duplicates. Enforces stop loss + take profit as OCO children. Persists 15 metadata fields per trade.

**H. Exit Engine (`algo_exit_engine.py`)**  
Hierarchical exit priority: Hard stop → Minervini break → RS break → Time exit → Breakeven raise → Partial exits (T1/T2/T3) → Chandelier trail → TD Sequential → Distribution day exit.

---

## Database Schema (Auto-Created)
- **stock_symbols** — Ticker, name, sector, market cap
- **price_daily** — OHLCV + volume for each symbol
- **technical_indicators** — RSI, MACD, SMA, etc.
- **buy_sell_daily** — Entry/exit signals (with T1-T5 filter scores)
- **algo_trades** — Executed trades with Alpaca order IDs
- **algo_positions** — Open positions with P&L, trailing stops
- **algo_audit_log** — Decision log for every orchestrator run

## Cost Breakdown ($65-90/month)
- RDS: $20-30 (db.t3.micro, 61GB storage)
- ECS: $10-15 (t3 instances, spot pricing)
- Lambda: $0-5 (free tier + minimal execution)
- S3: $1-5 (versioning + lifecycle policies)
- CloudFront: $0 (mostly free tier)
- VPC: $0 (no NAT, using endpoints)

---
**Remember:** This is enterprise-grade — no shortcuts, no experimental loaders, no manual AWS changes.

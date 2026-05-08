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

## Infrastructure (AWS CloudFormation)

### 6 Templates (6 stacks)
1. **template-bootstrap.yml** — GitHub OIDC setup (one-time)
2. **template-core.yml** — VPC, subnets, security groups, ECR, S3 buckets
3. **template-app-stocks.yml** — RDS PostgreSQL, ECS cluster, Secrets Manager, CloudWatch logs
4. **template-app-ecs-tasks.yml** — 39 loader task definitions (18 stock loaders × 2 + 3 ETF loaders)
5. **template-webapp-lambda.yml** — REST API Lambda (Node.js, ARM64, SnapStart), API Gateway, CloudFront, Cognito
6. **template-algo-orchestrator.yml** — Algo Lambda (Python), EventBridge Scheduler (daily 5:30pm ET), SNS alerts, SQS DLQ

### 23 GitHub Workflows
- **deploy-*.yml** — Deploy individual stacks
- **deploy-all-infrastructure.yml** — Master orchestrator (deploys in dependency order)
- **bootstrap-oidc.yml** — Setup GitHub OIDC (one-time)
- **ci-*.yml** — Unit tests, linting, backtest regression
- **cleanup-*.yml** — Clean orphaned resources or full stack nuke

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

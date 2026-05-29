# Stock Analytics Platform — Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions (config: max_positions). Reconciles with Alpaca daily.

## SYSTEM MAP

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator (main loop) | `algo/algo_orchestrator.py` | Lambda (algo-algo-dev) | EventBridge schedule: 9:30 AM ET, 5:30 PM ET Mon-Fri |
| Loaders (data fetchers) | `loaders/load_*.py` (49 scripts: 9 essential + 40 supporting) | ECS Fargate tasks | Step Functions EOD pipeline + EventBridge schedules |
| API (REST endpoints) | `lambda/api/lambda_function.py` | Lambda (algo-api-dev) | API Gateway HTTP requests |
| Frontend (dashboard) | `webapp/frontend/src/` | S3 + CloudFront | npm run build (React app) |
| Signals (Phase 5) | `algo/algo_signals.py` | Lambda Phase 5 | Called by orchestrator |
| Database (data storage) | PostgreSQL | RDS (algo-db) | Schema: `terraform/modules/database/init.sql` |

## CREDENTIALS & SECRETS

**Local Development (PowerShell profile):**
```
DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL
APCA_API_KEY_ID, APCA_API_SECRET_KEY (Alpaca paper keys)
ALPACA_API_KEY, ALPACA_API_SECRET (Alpaca account)
ALPACA_PAPER_TRADING = true or false (paper vs live)
FRED_API_KEY (economic data)
```

**GitHub CI (GitHub Secrets):**
- `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` — Alpaca API keys
- `ALPACA_API_KEY`, `ALPACA_API_SECRET` — Alpaca trading keys
- `FRED_API_KEY` — Federal Reserve economic data
- `RDS_PASSWORD` — Database password
- `AWS_ACCOUNT_ID` — AWS account number

**Production (AWS Secrets Manager):**
- `algo/database` — RDS password (synced from Terraform)
- `algo/alpaca` — Alpaca API/trading keys
- `algo/fred` — FRED API key

**Rules:**
- Rotate credentials quarterly
- If leaked to git history, rotate immediately
- Never commit `.env` files
- CI uses OIDC (OpenID Connect) for AWS authentication, not static keys

## LOCAL AWS CREDENTIALS (Reader Access)

When troubleshooting or reading logs/resources in AWS, use the IaC-managed developer credentials:

**If you see:** `Error: The security token included in the request is invalid`
- Your local AWS credentials have expired. Use the refresh script (below).

**To refresh:**
```powershell
scripts/refresh-aws-credentials.ps1
```

**What this does:**
1. Triggers GitHub Actions workflow `refresh-dev-credentials.yml` (uses GitHub OIDC, no static keys)
2. Workflow reads developer credentials from `algo/developer-credentials` in AWS Secrets Manager
3. Downloads credentials artifact and updates `~/.aws/credentials` file
4. Verifies with `aws sts get-caller-identity` before completing

**Why this approach:**
- Credentials are generated fresh from IaC every refresh (never stale in Secrets Manager)
- No need to manage static keys locally
- GitHub OIDC = no credentials stored in git, CI environment, or PowerShell profile
- All credential rotations happen in Terraform (centralizing security)

**If the script fails:**
1. Verify GitHub CLI is authenticated: `gh auth status`
2. Check workflow logs: `gh run list --workflow refresh-dev-credentials.yml --limit 5`
3. Manually download: `gh workflow run refresh-dev-credentials.yml`, then `gh run download --name dev-credentials --dir ~/.aws-tmp`

**AWS credentials profile:** `algo-developer` (read-only IAM user, created by Terraform)

**Credential Rotation:** Automatic quarterly rotation (first Monday of each quarter at 02:00 UTC)
- Workflow: `.github/workflows/rotate-dev-credentials.yml`
- Manual trigger: `gh workflow run rotate-dev-credentials.yml`
- After rotation: Users must refresh with `scripts/refresh-aws-credentials.ps1`
- Procedure: Terraform invalidates old key, creates new one, stores in Secrets Manager

## CREDENTIAL FLOW (IaC)

Credentials flow through a single pipeline — never lose them, never hardcode them:

```
GitHub Secrets (source of truth)
    ↓  .github/workflows/update-credentials.yml
AWS Secrets Manager (algo/alpaca, algo/fred)
    ↓  .github/workflows/deploy-code.yml reads and sets Lambda env
Lambda env vars: APCA_API_KEY_ID, APCA_API_SECRET_KEY, APCA_API_BASE_URL
```

**Standard variable names:** `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` (always these, not ALPACA_API_KEY/ALPACA_SECRET_KEY).

**Rotation procedure:**
1. Generate new keys in Alpaca dashboard (alpaca.markets → API Keys)
2. `gh secret set ALPACA_API_KEY_ID --body "new_id"` (paper) or `ALPACA_API_KEY` (live)
3. `gh secret set ALPACA_API_SECRET_KEY --body "new_secret"` (paper) or `ALPACA_SECRET_KEY` (live)
4. `gh workflow run update-credentials.yml -f trading_mode=paper` (or live)
5. Update local PowerShell profile: APCA_API_KEY_ID + APCA_API_SECRET_KEY

## LIVE TRADING CONFIG

To switch from paper to live trading:
1. Get valid live keys from alpaca.markets → API Keys → Live Trading
2. Store live keys in GitHub Secrets: `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
3. `gh workflow run update-credentials.yml -f trading_mode=live`
4. Edit `terraform/terraform.tfvars`: set `alpaca_paper_trading = false`
5. `git push` — deploy-all-infrastructure.yml applies Terraform and redeploys Lambda

For paper trading (testing):
```
alpaca_paper_trading = true  (in terraform.tfvars)
```
Lambda endpoint and keys are set automatically by deploy based on tfvars value.

## CREDENTIAL ROTATION SCHEDULE

All credentials rotate on fixed schedules. Update locally when rotated:

| Credential | Interval | Procedure | Local Refresh |
|-----------|----------|-----------|---------------|
| `algo-developer` AWS key | Quarterly (Feb, May, Aug, Nov) | Automatic: `rotate-dev-credentials.yml` | `scripts/refresh-aws-credentials.ps1` |
| Alpaca API (paper) | Quarterly | Manual: regenerate in Alpaca dashboard → `gh secret set` → `update-credentials.yml` | Update PowerShell profile env vars |
| Alpaca API (live) | Quarterly | Manual: regenerate in Alpaca dashboard → `gh secret set` → `update-credentials.yml` | Update PowerShell profile env vars |
| FRED API key | Quarterly | Manual: regenerate in FRED dashboard → `gh secret set` → `update-credentials.yml` | Update PowerShell profile env vars |
| RDS database password | Quarterly | Manual: `terraform apply` with new password → redeploy Lambdas | Lambda env auto-updated |

**Rotation reminder:** Q1=February, Q2=May, Q3=August, Q4=November
- Automatic reminder runs first Monday of each quarter at 02:30 UTC (`.github/workflows/credential-rotation-reminder.yml`)
- Creates actionable checklist in GitHub Actions workflow summary
- All team members should receive summary in their notification settings

**If a credential is leaked:** Rotate immediately (don't wait for quarterly schedule). For AWS keys, delete old key in IAM console and trigger `rotate-dev-credentials.yml`. For API keys, regenerate in dashboard immediately and update GitHub Secrets.

## DEPLOYMENT ARCHITECTURE

**GitHub Actions → AWS:**
- Workflow: `aws-actions/configure-aws-credentials@v4`
- Authentication: OIDC (OpenID Connect) — GitHub token exchanges for temporary AWS credentials
- IAM Role: `arn:aws:iam::<ACCOUNT_ID>:role/algo-svc-github-actions-dev`
- No static AWS keys in repo

**Lambda Layer (psycopg2):**
- Name: `algo-psycopg2-layer-dev` (created by Terraform)
- Why: Python wheels built on Linux; Windows dev wheels incompatible. Layer built once, reused.
- Runtime: Python 3.12
- Used by: `algo-api-dev`, `algo-db-init-dev` Lambdas
- Deploy: Via `deploy-all-infrastructure.yml`

**Workflows & Deployment:**

| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| `deploy-code.yml` | `git push main` (automatic) | Run tests, lint, security scan, deploy code to Lambdas |
| `deploy-all-infrastructure.yml` | Manual dispatch | Terraform apply, rebuild Lambda layers, deploy ECS tasks |
| `test-orchestrator.yml` | Manual dispatch | Invoke orchestrator Lambda directly |
| `manual-invoke-loaders.yml` | Manual dispatch | Manually run individual ECS loader tasks |

## AWS RESOURCES (us-east-1)

| Resource Type | Name | Purpose |
|---------------|------|---------|
| ECS Cluster | `algo-cluster` | Container orchestration for loader tasks |
| Lambda Function | `algo-algo-dev` | Orchestrator (7-phase workflow) |
| Lambda Function | `algo-api-dev` | HTTP REST API endpoints |
| RDS Database | `algo-db` | PostgreSQL database (endpoint: `algo-db.<random>.us-east-1.rds.amazonaws.com`) |
| Secrets Manager | `algo-db-credentials-dev` | Database password (auto-synced from Terraform) |
| ECS Task Defs | `algo-<loader>-loader` | 49 individual loaders (9 essential in Step Functions pipeline, 40 supporting on EventBridge) |
| RDS Proxy | `algo-proxy` | Connection pooling for RDS (enabled via `enable_rds_proxy = true` in terraform.tfvars) |

## DATABASE CONNECTIONS (Dynamic RDS Proxy)

**All database connections route through RDS Proxy (when enabled):**
- Loaders: `DB_HOST` environment variable → RDS Proxy endpoint (set by Terraform)
- Orchestrator: `DB_HOST` environment variable → RDS Proxy endpoint (set by Terraform)
- Lambda functions: `DB_HOST` environment variable → RDS Proxy endpoint (set by Terraform)
- Secrets Manager secret: `host` field → RDS Proxy endpoint (dynamically set by Terraform)

**Configuration:**
- `terraform.tfvars`: `enable_rds_proxy = true` (line 35)
- RDS Proxy is created by `terraform/modules/database/main.tf` (lines 240-262)
- Database module outputs `rds_proxy_endpoint` which is passed to all modules
- Root `main.tf` uses `coalesce(rds_proxy_endpoint, rds_address)` to prefer proxy when available
- All endpoint references are **dynamic via Terraform variables** — no hardcoded endpoints

**Why RDS Proxy?** Connection pooling + query multiplexing reduces I/O contention. Eliminates orchestrator timeouts in Phase 3b (market exposure).

## SCHEDULE (EventBridge, Mon-Fri Only — UTC Times)

All times are UTC (EventBridge has no concept of US holidays).
The orchestrator exits early on market holidays via `MarketCalendar.is_trading_day()`.

| UTC Time | Event | ET Equivalent |
|----------|-------|---------------|
| 08:25 | stock_symbols loader | 4:25 AM EST / 5:25 AM EDT |
| 09:00 | stock_prices_daily loader (prices first, so downstream loaders see fresh data) | 4:00 AM EST / 5:00 AM EDT |
| 09:30 | market_data_batch (market health — runs AFTER prices to read from price_daily) | 4:30 AM EST / 5:30 AM EDT |
| 09:30 | Morning Step Functions pipeline starts (eod_bulk_refresh → technicals → signals → ECS orchestrator invoked) | 4:30 AM EST / 5:30 AM EDT |
| 14:30 | Morning orchestrator Lambda (EventBridge Scheduler, 9:30 AM ET) | 9:30 AM ET |
| 21:00 | EOD Step Functions pipeline (5:00 PM ET) | 5:00 PM ET |
| 22:30 | Evening orchestrator Lambda (EventBridge Scheduler, 5:30 PM ET) | 5:30 PM ET |

**Important:** market_data_batch schedule must stay at UTC 09:30 (after stock_prices_daily at UTC 09:00).
`load_market_health_daily.py` reads from `price_daily`, so it must run after prices are loaded.
If it runs before prices, market health will reflect yesterday's data, causing Phase 1 to halt
after any multi-day weekend because the calendar gap exceeds the staleness threshold.

## LOADERS

49 loader scripts in `loaders/load_*.py`:

**ESSENTIAL (9 loaders — Step Functions EOD pipeline):**
1. stock_symbols: Reference data for all tradable symbols
2. eod_bulk_refresh: Load daily OHLCV for all 5000+ symbols (maps to stock_prices_daily)
3. technical_data_daily: RSI, SMA, EMA, ATR, ADX, Bollinger Bands
4. market_health_daily: Market stage, distribution days, advance/decline, breadth, VIX
5. trend_template_data: Minervini 8-point, Weinstein stage
6. buy_sell_daily: BUY/SELL signals from technicals
7. signal_quality_scores: Win rate, profit factor, expectancy
8. algo_metrics_daily: Daily portfolio stats
9. swing_trader_scores: Final swing scoring

**SUPPORTING (40 loaders — EventBridge schedules + parallel workflows):**
- Reference: sp500_constituents, russell2000_constituents
- Price data: stock_prices_daily, stock_prices_weekly, etf_prices_daily, etf_prices_weekly, etf_prices_monthly
- Technical: (covered by technical_data_daily in EOD pipeline)
- Financial statements: financials_annual_income, financials_annual_balance, financials_annual_cashflow, financials_quarterly_income, financials_quarterly_balance, financials_quarterly_cashflow, financials_ttm_income, financials_ttm_cashflow
- Metrics: growth_metrics, quality_metrics, value_metrics, positioning_metrics, stability_metrics, stock_scores
- Earnings: earnings_history, earnings_calendar
- Analyst/Sentiment: analyst_sentiment, analyst_upgrades_downgrades, aaiidata, naaim_data, feargreed, sentiment, sentiment_social, company_profile, industry_ranking
- Signal processing: signal_themes
- Economic: fred_economic_data
- Market batch: market_data_batch

**SEC/EDGAR Request Header:** `User-Agent: algo-trading argeropolos@gmail.com` (required for SEC rate limits, hardcoded in `loaders/loader_loop.py`)

## KEY FILES & ENTRYPOINTS

| File | Purpose |
|------|---------|
| `algo/algo_orchestrator.py` | Main 7-phase orchestrator (data freshness → circuit breakers → position monitor → exits → signals → entries → reconciliation) |
| `algo/algo_signals.py` | Signal generation logic (Minervini trend + technical filters + fundamental screening) |
| `lambda/api/lambda_function.py` | REST API: `/api/stocks`, `/api/signals`, `/api/positions`, `/api/health`, etc. |
| `config/credential_manager.py` | Fetches secrets from AWS Secrets Manager (production) or env vars (local) |
| `terraform/main.tf` | Infrastructure as code (Lambdas, RDS, ECS, IAM, secrets) |

## DATA FRESHNESS POLICY

Phase 1 compares each table's latest date against the **previous trading day** (not a fixed calendar threshold). This handles multi-day holiday weekends correctly — e.g., after Memorial Day, the gap from Friday to Tuesday is 4 calendar days but the data is still from the most recent trading day.

| Table | Halt policy | Reason |
|-------|-------------|--------|
| `price_daily` (SPY) | Phase 1 halts | Core price data — missing = can't trade |
| `market_health_daily` | Phase 1 halts | Required for Tier 2 market gate |
| `trend_template_data` | Phase 1 halts | Required for Minervini trend filter |
| `signal_quality_scores` | Observe-only (logged, no halt) | Loaded by morning pipeline AFTER Lambda fires; halt would cause circular dependency |
| `buy_sell_daily` | Observe-only (logged, no halt) | Same — loaded post-Lambda by pipeline |
| `economic_data` | No halt | Stores FRED macro series (T10Y2Y, BAMLH0A0HYM2, ICSA etc). Refreshed daily at 9:00 AM UTC (5 AM ET) Mon-Fri by `run-fred-loader.yml` cron schedule. If missing, `algo_market_exposure.py` falls back to 0.7 default factor. |
| `company_profile`, `key_metrics` | Warning logged only | Background enrichment, 30-day SLA |

**Important:** `PipelineHealth.is_critical` only halts on `stock_symbols`, `price_daily`, and `market_health_daily`. All other tables generate warnings, not halts.

**Why:** Prevents trading on stale market data. The previous-trading-day comparison is implemented in `algo/orchestrator/phase1_data_freshness.py` using `MarketCalendar` to skip weekends and holidays when computing the expected data date.

## DEBUGGING & TROUBLESHOOTING

**Schema validation:** Verify these tables exist in RDS:
- `data_patrol_log` — data quality checks
- `data_loader_status` — loader execution history
- `algo_audit_log` — orchestrator decisions

If missing, rebuild schema via `deploy-code.yml` (loads `terraform/modules/database/init.sql` to RDS).

**Lambda environment variables:** All Lambdas require:
- `DB_SECRET_ARN` — Points to RDS password in Secrets Manager (must match actual Secrets Manager path)
- Check: Lambda config (not in code), CloudWatch Logs for `algo-api-dev` and `algo-algo-dev`

**Database connectivity from Lambda:**
- Lambdas run in VPC (security group controls). Requirements:
  - RDS endpoint in env var matches actual RDS instance
  - Secrets Manager password synced with RDS actual password
  - VPC Security Group allows outbound port 5432 to RDS subnet
  - RDS is in same VPC/subnet as Lambda

**Loader execution:**
- ECS tasks need: IAM task role with ECS permissions, internet access (NAT gateway), RDS access (VPC)
- Timeouts usually indicate: API rate limits (yfinance, SEC, Alpaca), no internet access, or RDS unreachable
- Check CloudWatch Logs for specific errors

**Signal generation:**
- Requires recent data in `technical_data_daily`
- If `buy_sell_daily` is empty: verify loaders ran successfully, price data exists, technicals were calculated
- Check `data_loader_status` table for which loaders succeeded/failed

**Alpaca authentication errors (401):**
- Live trading: `ALPACA_PAPER_TRADING=false`, `APCA_API_BASE_URL=https://api.alpaca.markets` in PowerShell profile
- Paper trading: `ALPACA_PAPER_TRADING=true`, `APCA_API_BASE_URL=https://paper-api.alpaca.markets`
- Verify in PowerShell: `$env:ALPACA_PAPER_TRADING`, `$env:APCA_API_BASE_URL`

**Orchestrator Lambda timeout (600+ second hangs):**
- NOT a cold-start issue. Root cause: RDS disk I/O contention during Phase 3b market exposure computation.
- Phase 3b runs 11 sequential database queries (IBD state, trend, breadth, VIX, McClellan, etc.)
- With high DiskQueueDepth (30+), each query waits for I/O → timeout after 600s.
- **Fix:** Enable RDS Proxy in terraform.tfvars: `enable_rds_proxy = true` (connection pooling + query multiplexing).
- RDS Proxy endpoint automatically replaces direct RDS connection in Lambda env vars (terraform/modules/services/main.tf line 502).
- Symptoms: Lambda logs show DB connection succeeds, then hangs in Phase 3b (market exposure computation).
- Check RDS metrics: `aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DiskQueueDepth --dimensions Name=DBInstanceIdentifier,Value=algo-db`

**API Lambda cold-start timeout (500 errors on first request):**
- Lambda in VPC takes 15-40s to initialize (ENI provisioning + imports) on cold-start
- API Gateway timeout: 29 seconds (hard limit)
- Solution: Reserved concurrency = 1 in Terraform (costs ~$0.015/hour, keeps instance warm)
- Workaround: Retry requests; second request works (instance warm)

**"Phase 7 reconciliation timeout":**
- Alpaca API calls have 30-second thread-based timeout wrapper (since May 26 fix)
- If orchestrator still hangs: check if Alpaca API endpoint is reachable, network issues

## ORCHESTRATOR PHASES

1. **Phase 1 — Data Freshness:** Verify price_daily, technical_data_daily recent (< 7 days). Halt if stale.
2. **Phase 2 — Circuit Breakers:** Check drawdown, daily loss, consecutive losses, VIX, market stage. Halt if any triggered.
3. **Phase 3 — Position Monitor:** Evaluate each open position (price, P&L, trailing stop, health score). Propose: HOLD, RAISE_STOP, or EARLY_EXIT.
4. **Phase 4 — Exit Execution:** Execute exits from Phase 3 + exit_engine rules (trailing stops, tiered targets, time decay).
5. **Phase 5 — Signal Generation:** Evaluate today's BUY signals through Tier 1-6 filters (data quality, market, trend, SQS, portfolio, advanced). Rank and take top N.
6. **Phase 6 — Entry Execution:** Execute trades for ranked candidates (final checks, position sizing, order placement).
7. **Phase 7 — Reconciliation:** Pull live Alpaca account, sync positions, calculate P&L, write portfolio snapshot to `algo_audit_log`.

All phases write audit logs. Fail-closed on critical (Phase 1, 2), fail-open on operational (Phases 3-7).

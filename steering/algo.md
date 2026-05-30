# Stock Analytics Platform — Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions (config: max_positions). Reconciles with Alpaca daily.

## SYSTEM MAP

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator (main loop) | `algo/algo_orchestrator.py` | Lambda (algo-algo-dev) | EventBridge schedule: 9:30 AM ET, 5:30 PM ET Mon-Fri |
| Loaders (data fetchers) | `loaders/load_*.py` (33 loaders) | ECS Fargate tasks | EventBridge schedules + Step Functions EOD pipeline |
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

## DEPLOYMENT FLOW (2026-05-29: OIDC Verified & Working)

**THE RIGHT WAY - Production deployments use GitHub Actions OIDC:**
```
git push main
    ↓
GitHub Actions triggers deploy-code.yml or deploy-all-infrastructure.yml
    ↓
GitHub token automatically exchanged for temporary AWS credentials (OIDC)
    ↓
Terraform/Lambda/S3 deployments execute with transient credentials
    ↓
Zero static keys, credentials auto-expire after 1 hour
```

**Status:** ✅ VERIFIED WORKING (2026-05-29 run 26637955418)
- Frontend deployment succeeded
- All Lambda functions updated
- CloudFront cache invalidated
- Zero authentication errors

**NEVER use local terraform apply or credential refresh scripts for production work.** Those are only for local development/debugging.

---

## LOCAL AWS CREDENTIALS (Auto-Refreshing)

**For local development only (not production deployment):**

Set up once:
```bash
scripts/setup-credential-process.sh
```

This configures your `~/.aws/config` to automatically fetch fresh credentials on-demand:
- No static credentials file
- No manual refresh needed
- Credentials always fresh and valid
- Works for all AWS CLI commands and Python boto3 calls

**How it works:**
1. When you run `aws s3 ls --profile algo-developer`, AWS SDK calls the credential_process script
2. Script fetches fresh credentials from AWS STS
3. Credentials cached locally for 50 minutes
4. No human intervention required

**For debugging locally:**
```bash
aws sts get-caller-identity --profile algo-developer
```

**When credentials expire (error: "The security token included in the request is invalid"):**
```powershell
# Run this to refresh:
scripts/refresh-aws-credentials.ps1
```

**Credential Rotation:** Automatic quarterly rotation (first Monday of each quarter at 02:00 UTC)
- Workflow: `.github/workflows/rotate-dev-credentials.yml`
- Rotates the IAM key in Secrets Manager
- Your next AWS command automatically fetches the new key
- No action required from you

## CREDENTIAL FLOW (Single Source of Truth)

All credentials flow from AWS Secrets Manager — never hardcode, never duplicate:

```
AWS Secrets Manager (single source of truth)
    ↓
GitHub Actions (OIDC) → reads for deployments
Local Development (credential_process) → auto-fetches for debugging
Lambda/ECS (IAM roles) → reads from environment
Step Functions (IAM roles) → reads from environment
```

**Secrets in Manager:**
- `algo/database` — RDS credentials
- `algo/alpaca` — Alpaca API keys (paper and live)
- `algo/fred` — FRED API key
- `algo/developer-credentials` — AWS IAM access key for local development

**Rotation procedure:**
1. Terraform automatically rotates all secrets quarterly (first Monday of each quarter, 2:00 AM UTC)
2. You don't need to do anything
3. For manual rotation: `gh workflow run rotate-dev-credentials.yml`

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

## DEPLOYMENT ARCHITECTURE (THE RIGHT WAY - OIDC ONLY)

**How to Deploy:**
```bash
git push main
# That's it. GitHub Actions does everything automatically via OIDC.
```

**Authentication: GitHub Actions → AWS via OIDC (Automatic)**
- GitHub OIDC provider exchanges GitHub token for temporary AWS credentials
- Zero static keys stored anywhere
- Credentials auto-expire after workflow completes
- Implementation: `aws-actions/configure-aws-credentials@v4` with `role-to-assume`
- IAM Role: `arn:aws:iam::<ACCOUNT_ID>:role/algo-svc-github-actions-dev` (terraform-created)
- Required Secrets: `AWS_ACCOUNT_ID`, `AWS_GITHUB_ACTIONS_ROLE_ARN`

**DO NOT:**
- ❌ Use `scripts/refresh-aws-credentials.ps1` — it adds complexity, use only for rare local debugging
- ❌ Store AWS static keys in GitHub Secrets — defeats entire purpose of OIDC
- ❌ Run `terraform apply` locally — always deploy via GitHub Actions

**Lambda Layer (psycopg2):**
- Name: `algo-psycopg2-layer-dev` (created by Terraform)
- Why: Python wheels built on Linux; Windows dev wheels incompatible. Layer built once, reused.
- Runtime: Python 3.12
- Used by: `algo-api-dev`, `algo-db-init-dev` Lambdas
- Deploy: Via `deploy-all-infrastructure.yml`

**Workflows & Deployment:**

| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| `deploy-all-infrastructure.yml` | `git push main` (automatic) | Terraform apply + Lambda layer rebuild + ECS tasks + code deploy |
| `deploy-code.yml` | `git push main` (automatic) | Tests, lint, security scan |
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

## SCHEDULE (EventBridge & Step Functions, Mon-Fri Only)

All times are UTC in code; ET equivalents listed for operations reference.
The orchestrator exits early on market holidays via `MarketCalendar.is_trading_day()`.

### Morning Data Loading (03:25-09:30 AM ET)
| UTC Time | ET Equivalent | Event | Reason |
|----------|---------------|-------|--------|
| 08:25 | 3:25 AM EST/5:25 AM EDT | stock_symbols loader (EventBridge) | Foundation: ensure new symbols are available |
| 08:30 | 3:30 AM EST/5:30 AM EDT | sp500_constituents loader (EventBridge) | Mark S&P 500 membership (after symbols loaded) |
| 08:35 | 3:35 AM EST/5:35 AM EDT | russell2000_constituents loader (EventBridge) | Mark Russell 2000 membership |
| 09:00 | 4:00 AM EST/5:00 AM EDT | stock_prices_daily loader (EventBridge) | Unified price loader (daily, weekly, monthly intervals + stocks, ETFs) |
| 09:30 | 4:30 AM EST/5:30 AM EDT | **EOD Step Functions Pipeline Starts** | Orchestrates multi-stage data loading with dependencies |
|  |  | ├─ stock_symbols (first step — guarantees fresh symbols before prices) | Reference data |
|  |  | ├─ stock_prices_daily (already loaded via EventBridge, but included for pipeline completeness) | OHLCV for 5000+ symbols |
|  |  | ├─ technical_data_daily + market_health_daily (parallel) | Technical indicators + market breadth |
|  |  | ├─ trend_template_data | Minervini + Weinstein scoring |
|  |  | ├─ buy_sell_daily + signal_quality_scores | Trading signals + quality filters |
|  |  | ├─ algo_metrics_daily + swing_trader_scores | Portfolio metrics + final ranking |
|  |  | └─ **Morning Orchestrator Lambda Invoked** | Phase 1: Data freshness, Phase 2-7: trading logic |

### Orchestrator Execution Schedule
The orchestrator runs **4 times daily** on trading days:

| Time ET | UTC | Purpose | Description |
|---------|-----|---------|-------------|
| 09:30 AM | 14:30 | **Primary Entry** | Main trading window after market opens (30min after bell) |
| 01:00 PM | 18:00 | **Rebalance** | Afternoon position refresh + profit-taking opportunities |
| 03:00 PM | 20:00 | **Pre-Close** | Final trades before 4 PM market close (intraday edge) |
| 05:30 PM | 22:30 | **Signal Prep** | Compute next day's signals (no trades, prep only) |

### Supporting Data Loaders (EventBridge Scheduled)
26 additional loaders run on fixed schedules throughout the day to refresh market data:
- **04:00 AM ET (09:00 UTC):** Stock symbols, constituent indices, financials, metrics
- **06:00 PM ET (23:00 UTC):** Earnings, analyst data, sentiment updates
- **04:30 PM ET (20:30 UTC):** FRED economic indicators (before EOD pipeline reads them)

**Important:** All dependent data must load before orchestrator runs. market_health_daily reads from price_daily, so it must always run after prices are loaded. If it runs before prices, market health will reflect yesterday's data, causing Phase 1 to halt after any multi-day weekend because the calendar gap exceeds the staleness threshold.

## LOADERS

33 loader scripts in `loaders/load_*.py`:

### Core Pipeline (9 loaders — Step Functions EOD pipeline)
1. **stock_symbols** — Reference data for all tradable symbols (foundation for all trading)
2. **stock_prices_daily** — Unified loader for OHLCV (daily, weekly, monthly intervals for stocks + ETFs)
3. **technical_data_daily** — Technical indicators (RSI, SMA, EMA, ATR, ADX, Bollinger Bands, etc.)
4. **market_health_daily** — Market breadth, advance/decline, distribution days, VIX, market stage
5. **trend_template_data** — Minervini 8-point, Weinstein stage scoring
6. **buy_sell_daily** — BUY/SELL trade signals from technical indicators
7. **signal_quality_scores** — Signal win rate, profit factor, expectancy (quality filters)
8. **algo_metrics_daily** — Daily portfolio stats and performance metrics
9. **swing_trader_scores** — Final swing trading scores (combines all signals + filters)

### Reference Data (3 loaders — EventBridge scheduled)
- **stock_symbols** — All tradable symbols (runs at 3:25 AM ET via EventBridge)
- **sp500_constituents** — Mark S&P 500 membership (runs at 3:30 AM ET)
- **russell2000_constituents** — Mark Russell 2000 membership (runs at 3:35 AM ET)

### Price Data (1 unified loader — EventBridge scheduled + pipeline included)
- **stock_prices_daily** — Daily OHLCV for 5000+ symbols, handles all timeframes (1d, 1wk, 1mo) and asset classes (stocks, ETFs) via environment variables (runs at 4:00 AM ET via EventBridge; also included in EOD pipeline for consistency)

### Financial Data (8 loaders — EventBridge scheduled)
- **financials_annual_income** — Annual income statements
- **financials_annual_balance** — Annual balance sheets
- **financials_annual_cashflow** — Annual cash flow statements
- **financials_quarterly_income** — Quarterly income statements
- **financials_quarterly_balance** — Quarterly balance sheets
- **financials_quarterly_cashflow** — Quarterly cash flow statements
- **financials_ttm_income** — Trailing twelve months income
- **financials_ttm_cashflow** — Trailing twelve months cash flow

### Computed Metrics (6 loaders — EventBridge scheduled)
- **growth_metrics** — Growth scores (EPS, revenue growth, etc.)
- **quality_metrics** — Quality scores (profit margins, ROE, etc.)
- **value_metrics** — Value scores (P/E, P/B, etc.)
- **positioning_metrics** — Positioning scores (institutional ownership, etc.)
- **stability_metrics** — Stability scores (volatility, beta, etc.)
- **stock_scores** — Aggregate stock scores (combines all metrics)

### Earnings Data (2 loaders — EventBridge scheduled)
- **earnings_history** — Historical earnings data
- **earnings_calendar** — Upcoming earnings dates

### Company & Analyst Data (4 loaders — EventBridge scheduled)
- **company_profile** — Company fundamentals and sector/industry classification
- **analyst_sentiment** — Analyst sentiment scores
- **analyst_upgrades_downgrades** — Recent analyst rating changes
- **industry_ranking** — Sector and industry relative performance

### Market Sentiment (5 loaders — EventBridge scheduled)
- **feargreed** — CNN Fear & Greed Index
- **aaiidata** — AAII investor sentiment survey
- **naaim_data** — NAAIM exposure index
- **sentiment** — Aggregate sentiment index (combines multiple sources)
- **sentiment_social** — Social media sentiment scores

### Signal Processing (2 loaders — EventBridge scheduled)
- **signal_themes** — Signal themes (momentum, reversal, breakout classification)
- (Note: buy_sell_daily handled in pipeline; signal_quality_scores also in pipeline)

### Economic Data (1 loader — EventBridge scheduled)
- **fred_economic_data** — FRED economic indicators (T10Y2Y, yields, jobless claims, etc.) loaded at 4:30 PM ET (before EOD pipeline)

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

## DATABASE CONNECTION PATTERN (DatabaseContext)

**Status: ✅ REFACTORING COMPLETE (2026-05-30)**

All database access must use `DatabaseContext` for automatic resource management:

```python
from utils.database_context import DatabaseContext

# Read operations
with DatabaseContext('read') as cur:
    cur.execute("SELECT * FROM table WHERE id = %s", (id,))
    result = cur.fetchone()
# Connection automatically closed and rolled back on exception
# No manual cur.close() needed

# Write operations (auto-commits on success, auto-rollbacks on exception)
with DatabaseContext('write') as cur:
    cur.execute("INSERT INTO table VALUES (%s, %s)", (val1, val2))
# Auto-committed on successful exit
# Auto-rolled back if exception occurs
```

**DO NOT:**
- ❌ Call `cur.close()` — DatabaseContext handles it
- ❌ Call `conn.commit()` or `conn.rollback()` — DatabaseContext handles it
- ❌ Store `self.conn = context.conn` and use it after the with block exits
- ❌ Mix manual connections with DatabaseContext

**Why:** The context manager pattern ensures transactions are atomic, connections are properly closed, and errors don't leave dangling connections. Manual commit/close calls defeat this guarantees.

**Exceptions:** Standalone utilities and ECS loaders that create their own connections (not using DatabaseContext) may call commit/rollback directly. This is fine for isolated tools.

## API GATEWAY ROUTING ARCHITECTURE

**Stage name: `$default` (critical for correct routing)**

The API Gateway HTTP API uses stage `$default`. This is intentional:
- With `$default` stage: CloudFront forwards `/api/signals` → rawPath in Lambda = `/api/signals` → `api_router` matches `/api/signals` handler ✓
- With named stage (e.g., "api"): CloudFront forwards `/api/signals` → API GW strips "api" prefix → rawPath = `/signals` → `api_router` has no handler for `/signals` → 404 for ALL endpoints

**Health check fast path:**
The `/health` and `/api/health` endpoints return 200 immediately, before DB connection test or env validation. This ensures uptime monitors always succeed even if DB is temporarily unavailable.

**Route configuration:**
- Routes use `/api/` prefix in route_key (e.g., `GET /api/signals`)
- CloudFront behavior `path_pattern = "/api/*"` routes to API Gateway origin
- API GW `$default` stage preserves the full `/api/...` path in rawPath
- `lambda/api/api_router.py` matches against `/api/` prefixed paths

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

**Terraform plan fails with "Invalid index" error (orphaned loaders in state):**
- Error: "Error: Invalid index — the given key does not identify an element in this collection value"
- Root cause: Terraform state contains deleted loaders (e.g., "market_data_batch") but current `all_loaders` config doesn't include them
- Fix: Before approving terraform apply in GitHub Actions, remove stale state entries:
```bash
# From repo root, run this BEFORE terraform apply:
terraform state rm "module.loaders.aws_ecs_task_definition.loader[\"market_data_batch\"]" 2>/dev/null || echo "Already removed"
terraform plan -var-file=terraform.tfvars  # Should succeed now
```
- Or use the provided helper: see CLAUDE.md for refresh-aws-credentials.ps1 usage pattern
- This is a one-time cleanup for state drift; once applied, future plans will not have this issue

## ORCHESTRATOR PHASES

1. **Phase 1 — Data Freshness:** Verify price_daily, technical_data_daily recent (< 7 days). Halt if stale.
2. **Phase 2 — Circuit Breakers:** Check drawdown, daily loss, consecutive losses, VIX, market stage. Halt if any triggered.
3. **Phase 3 — Position Monitor:** Evaluate each open position (price, P&L, trailing stop, health score). Propose: HOLD, RAISE_STOP, or EARLY_EXIT.
4. **Phase 4 — Exit Execution:** Execute exits from Phase 3 + exit_engine rules (trailing stops, tiered targets, time decay).
5. **Phase 5 — Signal Generation:** Evaluate today's BUY signals through Tier 1-6 filters (data quality, market, trend, SQS, portfolio, advanced). Rank and take top N.
6. **Phase 6 — Entry Execution:** Execute trades for ranked candidates (final checks, position sizing, order placement).
7. **Phase 7 — Reconciliation:** Pull live Alpaca account, sync positions, calculate P&L, write portfolio snapshot to `algo_audit_log`.

All phases write audit logs. Fail-closed on critical (Phase 1, 2), fail-open on operational (Phases 3-7).

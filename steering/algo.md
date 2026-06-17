# Stock Analytics Platform: Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 15 concurrent positions. Reconciles with Alpaca daily.

## System Map

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator (7 phases) | `algo/algo_orchestrator.py` | Lambda algo-algo-dev | EventBridge: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri |
| Loaders (6 core + supporting) | `loaders/load_*.py` | ECS Fargate | 6 core via Step Functions (2:15 AM, 4:05 PM ET); supporting loaders async |
| API | `lambda/api/lambda_function.py` | Lambda algo-api-dev | HTTP requests |
| Frontend | `webapp/frontend/src/` | S3 + CloudFront | npm run build |
| Database | PostgreSQL | RDS algo-db | Schema: `lambda/db-init/schema.sql` |

## API Rate Limiting

See `steering/rate-limiting-strategy.md` for complete rate limiting strategy. Quick summary:

- **API Gateway:** 10,000 RPS global hard limit
- **Public endpoints** (no auth): Global per-endpoint limits via `check_public_rate_limit()`
  - `/api/algo/markets`, `/api/algo/market-factors`, etc.: 50-100 req/min
- **Admin endpoints** (requires 'admin' Cognito group): Per-user, per-endpoint limits via `check_admin_rate_limit()`
  - Health checks: 30 req/min (loader-status, system-health)
  - Expensive operations: 5 req/5min (patrol)
  - Dashboard endpoints: 20 req/min
- **External APIs** (yfinance, FRED): Handled by adaptive rate limiting in loaders

## API Error Handling

All database errors return proper HTTP status codes with error details instead of masking failures with empty data objects:
- **503 Service Unavailable:** Database unreachable or schema missing (tables not created yet)
- **504 Gateway Timeout:** Query exceeded timeout (more than 15 seconds)
- **500 Internal Error:** Unexpected errors
- Never return 200 OK with empty data

**Implementation:**
- `db_route_handler` decorator in `lambda/api/routes/utils.py` always returns error responses, never graceful degradation
- Removed `default_error_response` parameter from all endpoints (was masking errors with success_response)
- Fixed `/api/sentiment` endpoint that was returning `{}` on missing data
- Improved error logging (changed warning→error) for optional data fetches

**Frontend Implications:**
- Must now handle 503/504/500 errors as actual errors, not check for empty data
- Display error alerts instead of blank charts when 503 returned
- Retry logic recommended for 503/504 (transient errors)

**Affected Endpoints:**
- Daily return histogram, trade distribution, holding period distribution, stage distribution
- Algo portfolio, risk metrics, performance analytics, sentiment
- Economic calendar

**Verification:**
```bash
# Test: Empty table → 503 error (not empty {}), clear error message
curl https://api.example.com/api/algo/sentiment
# Returns: {"statusCode":503,"errorType":"no_data","message":"Sentiment data not available","_error":"..."}
```

## Credentials & Secrets

**Sources (priority order):** Environment variables → Terraform outputs (S3 remote) → AWS Secrets Manager (`algo/*` secrets).

**Local Setup:**
```powershell
scripts/setup-local-dev.ps1  # Fetch credentials, configure dashboard + frontend, enable 24h credential cache
# Then: scripts/run-dashboard.ps1, npm run dev (webapp/frontend), or api-proxy-server.py
```

**Credential Locations:**
- Dashboard API: `algo/dashboard-config`
- Database: `algo/database`
- Trading (Alpaca): `algo/alpaca` (paper trading via ALPACA_PAPER_TRADING=true)
- Economic data (FRED): `algo/fred`

**Rules:** Rotate quarterly (first Monday). Rotate immediately if leaked. Never commit `.env` files. GitHub Actions uses AWS OIDC (no static keys).

**If credentials expire:** `scripts/refresh-aws-credentials.ps1` (fetches fresh from Secrets Manager via OIDC)

## Terraform Outputs: Version Control & Freshness

Outputs are tracked in git (`.terraform-outputs.json`) with timestamp for traceability. FRESH if < 24 hours old.

**Scripts:** `verify-terraform-outputs.ps1` (check freshness), `sync-terraform-outputs.ps1` (manual sync), `get-cached-terraform-outputs.ps1` (load cache or live fallback).

CI/CD automatically saves outputs to git after `terraform apply`. If stale, scripts fetch from live AWS.

## Deployment

**Frontend Build:** Reads API URL + Cognito config at build time. Injects cache-bust parameter to `index.html` (prevents stale config.js). Four-layer cache invalidation (S3 headers + CloudFront + browser fetch + parameter).

**Production:** `git push main` → deploy-all-infrastructure.yml (Terraform + Lambda + frontend + migrations + saves outputs to git)

**Staging:** `git push staging` → deploy-staging.yml (dry-run, separate Lambda, shared RDS)

**Database:** Schema applied exclusively by GitHub Actions workflow, NOT by Terraform (avoids race conditions and state drift).

## Lambda Ownership: Source of Truth

**Edit code in `lambda/` directories only. Never edit `terraform/lambda_*`.**

**Deployment (ONE-WAY):** `lambda/` source → CI/CD builds ZIP → Terraform deploys to AWS.

Editing `terraform/lambda_api.zip` directly or writing code in `terraform/modules/services/` will be overwritten on next deployment. Source of truth is always `lambda/{api,algo_orchestrator,db-init}/`.

**Verify source of truth:**

```bash
# This is what gets deployed (generated by CI/CD):
ls -lh terraform/lambda_api.zip

# This is what you edit (version controlled):
ls -la lambda/api/

# To see what's in the ZIP:
unzip -l terraform/lambda_api.zip | head -30
```

**Why this structure:** Terraform cannot build dependencies (pip install) because it's infrastructure-as-code, not a build tool. GitHub Actions builds Lambda packages before Terraform uses them. This ensures reproducible, version-controlled deployments.

## Data Architecture: Positions

**Single Source of Truth:** `algo_positions` table
- `algo_positions_with_risk`: MATERIALIZED VIEW — enriched with stops, targets, sector, swing_score, R-multiple, and risk metrics. Refreshed at end of Phase 7 via `REFRESH MATERIALIZED VIEW`. Dashboard queries this view.
- `open_positions` view: filtered for OPEN/PARTIALLY_EXITED only
- Legacy `positions` table DROPPED (was empty, replaced by algo_positions in Phase 3)

**Positions view notes:**
- `stop_loss_price` = `COALESCE(algo_positions.stop_loss_price, algo_positions.current_stop_price)` — current_stop_price is used because the executor and reconciliation write stops there; stop_loss_price mirrors it for consistency
- `r_multiple` = `(current_price - entry) / (entry - stop)` — positive when profitable, negative when at a loss
- Sector comes from `COALESCE(algo_trades.sector, company_profile.sector, 'Unknown')` — trades get sector at entry time from Phase 5 signal


## Data Architecture: Technical Indicators (Redundancy)

**Single Source of Truth:** `technical_data_daily` table (RSI, MACD, ATR, Bollinger Bands, Mansfield RS, etc.)
- Computed TWICE per trading day: **morning prep + EOD pipeline** (vectorized loader: 15-25 min per run)
- Phase 1 validates technical data freshness (< 2 trading days old) before signal generation
- Phase 5 signal generation depends on fresh technical_data_daily for buy_sell_daily signals
- Dual-computation eliminates single point of failure (was: EOD-only before 2026-06-16)

**Resilience:** If EOD pipeline fails on day 1:
- Day 1 morning pipeline still computes technical indicators (fresh at 2:00 AM) ✅
- Phase 1 passes freshness checks using morning data (not stale)
- Phase 5 signal generation uses previous day's buy_sell_daily signals (fallback) ✅
- Next day: Morning pipeline recomputes technical data, fresh for trading ✓

## Data Architecture: Market Exposure

**Single Source of Truth:** `market_exposure_daily` table computed daily (12 quantitative factors → market regime)
- Computed TWICE per trading day: **morning prep (3:30 AM ET) + EOD (4:05 PM ET)**
- All orchestrator runs use most recent computation (morning regime for 9:30 AM/1 PM/3 PM, EOD regime for 5:30 PM)
- This dual-computation eliminates single point of failure (was: EOD-only)

**Data flow (REDUNDANT):**
1. Morning pipeline (2:15 AM ET) → market_health_daily + trend_template → **market_exposure_daily (3:30 AM)** → 9:30/1 PM/3 PM orchestrators
2. EOD pipeline (4:05 PM ET) → market_health_daily + trend_template → **market_exposure_daily (4:30 PM)** → 5:30 PM orchestrator

**Resilience:** If EOD pipeline fails on day 1:
- Day 1: 9:30 AM orchestrator uses morning regime (computed 3:30 AM) ✅
- Day 1: 5:30 PM orchestrator falls back to morning regime (graceful degradation, 9+ hours fresh) ✅
- Day 2: 9:30 AM orchestrator has fresh morning regime again (not stale for entire week) ✅
- Dashboard always shows regime from past 24 hours (at worst, 1 day old + fallback to caution)

**Monitoring & Recovery:**
- Monitor: `SELECT MAX(date), MAX(computed_at) FROM market_exposure_daily` (should show today's date with 2 recent timestamps: ~3:30 AM and ~4:30 PM)
- Alert if: No computation in past 24 hours (both morning AND EOD failed)
- Verify: Check CloudWatch logs `/ecs/algo-market_exposure_daily-loader` for errors (appears in both morning + EOD pipelines)
- If morning fails: Fallback covers morning orchestrators (EOD will try again at 4:05 PM)
- If EOD fails: Morning computation from next day covers all orchestrators (no week-long staleness)
- Python import errors: Push to main to trigger CI/CD pipeline rebuild
- Manual trigger morning pipeline: `aws stepfunctions start-execution --state-machine-arn <morning-pipeline-arn> --name manual-test-$(date +%s)`

## Schedule (Daily, Mon-Fri)

**2:00 AM ET:** morning-prep-pipeline (Step Functions) — loads prices + market health + swing_trader_scores + technical indicators (5-5.5h) before 9:30 AM deadline

**2:40 AM ET:** Load SP500/Russell constituents (EventBridge)

**4:05 PM ET:** EOD pipeline (Step Functions) — loads prices, market health, market exposure, technical indicators, algo metrics, swing scores, buy/sell signals (3-4h)

**4:30 PM ET:** Compute circuit breaker metrics (EventBridge)

**4:45 PM ET:** Compute performance metrics (EventBridge)

**9:30 AM, 1 PM, 3 PM, 5:30 PM ET:** Orchestrator runs (7 phases: freshness, circuit breakers, position monitor, exits, signal generation, entries, reconciliation)

## Loader Configuration

**6 Core Loaders (FAIL-CLOSED):**
- `load_stock_symbols.py` — stock symbols and universe
- `load_prices.py` — daily OHLCV price data (formerly `load_stock_prices_daily.py`)
- `load_swing_trader_scores.py` — Minervini-based scoring
- `load_market_health_daily.py` — market breadth and health metrics
- `load_trend_criteria_data.py` — Weinstein trend template data (formerly `load_trend_template_data.py`)

**50 Supporting Loaders (FAIL-OPEN):** Earnings, sentiment, technical, economic, sector, etc. Continue if they fail.

**Parallelism:** Adaptive per-loader based on RDS connection pool. Base config in DynamoDB, reduces automatically if RDS >80% saturated.
- stock_prices_daily: min=1, max=3 (yfinance rate limit protection)
- technical_data_daily: min=1, max=2 (prevents RDS hangs)
- Analytics loaders: min=1, max=8

**Rate Limiting Mitigation:**
- yfinance: batch_size=150, request pacing, exponential backoff (5 max retries)
- Alpaca: High rate limits, current parallelism safe
- FRED: Single endpoint, low volume

## RDS Proxy Connection Pool

**Architecture:** Multiplexes 24 loaders (48-96 direct connections) to 20-30 persistent RDS connections

**Configuration:** AWS defaults (max_connections=100, connection_borrow_timeout=120s)

**Monitoring:** CloudWatch metric `DatabaseConnections` (AWS/RDS namespace)
- Morning prep (2:45-9:30 AM): expect <30 connections (2-3 loaders running)
- EOD pipeline (4:05-5:30 PM): expect 20-30 RDS connections (well below 500 max)
- Alert threshold: >80% of max (>400 connections) → investigate slow queries

## Production Monitoring (SLA Tracking)

**Pipeline Timing Alarms:**

| Metric | Threshold | Pipeline | Action |
|--------|-----------|----------|--------|
| `stock_prices_daily` | >120 min | Morning + EOD | Alert: yfinance rate limiting likely; check adaptive batching config |
| `morning_prep_pipeline` | >300 min | Morning (2-9:30 AM) | Alert: approaching 9:30 AM deadline; investigate loader health |
| RDS Connections | >40 | Any time | Warning: monitor for slow queries; check if parallelism needs reduction |

**CloudWatch Metrics Emitted:**

- `AlgoTrading/Operations:OperationDuration` — Each operation (loader, phase) emits duration in seconds with Operation dimension
  - Source: `TimeBlock` context manager in `monitoring/metrics_context.py`
  - Used for: SLA tracking, slow operation detection, rate limit diagnosis
- `AlgoTrading:LoaderDurationSeconds` — Detailed per-loader timing (price_daily, scores, health, etc.)
  - Emitted by: Orchestrator Phase 1 (data freshness check)
  - Period: Every orchestrator run (9:30 AM, 1 PM, 3 PM, 5:30 PM ET + morning/EOD pipelines)

**Dashboard Access:**
- `algo-pipeline-monitoring-dev`: Timeline of stock_prices_daily, RDS connections, and recent loader errors
- `algo-rds-monitoring-dev`: RDS CPU, connections, disk queue depth
- `algo-loader-monitoring-dev`: Supporting loader failures (28 loaders) consolidated alarm

**Dashboards auto-refresh every 5 minutes. View real-time to diagnose slow pipelines.**

**Manual Monitoring Checklist (SLA Validation):**

*Morning Preparation Pipeline (2:00 AM - 9:30 AM ET):*
1. At 2:30 AM: Monitor stock_prices_daily load time — should complete by 4:00 AM (~2h window)
2. At 7:00 AM: Confirm market_health_daily + swing_trader_scores loaded (separate fast path, ~10-30 min total)
3. At 9:00 AM: Verify Phase 1 passes (if not, halt flag triggers and orchestrator skips Phase 5/6)
4. If morning prep >90 min: Check CloudWatch for yfinance rate limiting (adaptive batching may have reduced batch_size)

*EOD Pipeline (4:05 PM - 6:00 PM ET):*
1. At 4:15 PM: stock_prices_daily should complete by 5:15 PM (1h limit for EOD SLA)
2. At 5:00 PM: Verify Phase 1 passes (circuit breakers computed, Phase 2+ scheduled)
3. If EOD >85 min: Investigate yfinance lag or RDS slow queries (disk queue depth)

**Alerting:** SNS topic `algo-loader-alerts-dev` receives alarms. Configure email subscription in Terraform variables.

## Pre-Computed Metrics

**circuit_breaker_status table:** Daily snapshot of 9 circuit breaker metrics (portfolio drawdown, daily loss, consecutive losses, open risk, VIX, market stage, SPY change, win rate, trigger count)
- Computed by: `loaders/compute_circuit_breakers.py` (EventBridge rule: 4:30 PM ET Mon-Fri)
- Computation time: 2-5 seconds (pure SQL aggregation)
- API response: `/api/algo/circuit-breakers` returns pre-computed data in 20-30ms (was 800ms on-the-fly)

**algo_performance_metrics table:** Daily snapshot of 14 performance stats (win rate, profit factor, Sharpe, Sortino, max drawdown, avg holding days, CAGR, Calmar, streaks)
- Computed by: `loaders/compute_performance_metrics.py` (EventBridge rule: 4:45 PM ET Mon-Fri)
- Computation time: 10-15 seconds (bulk trade analysis + portfolio snapshots)
- API response: `/api/algo/performance` returns pre-computed data in 20-30ms (was 1200ms on-the-fly)

**Verification:** Pre-computation loaders run via EventBridge schedule rules (Terraform: `terraform/modules/loaders/main.tf:533-540`). To verify daily execution:

1. **Check execution status (DynamoDB):**
   - Query `algo-loader-status` table: look for `compute_circuit_breakers` and `compute_performance_metrics` with today's date
   - Status: "SUCCESS" = loader completed; "FAILED" = check ECS task logs
   - Run (from AWS CLI): `aws dynamodb query --table-name algo-loader-status-dev --key-condition-expression "loader_name = :name AND execution_date = :date" --expression-attribute-values '{ ":name": {"S": "compute_circuit_breakers"}, ":date": {"S": "'$(date +%Y-%m-%d)'"}}'` (substitute today's date)

2. **Check table data (PostgreSQL):**
   ```sql
   SELECT MAX(check_date), COUNT(*) FROM circuit_breaker_status WHERE check_date >= CURRENT_DATE - 5;
   SELECT MAX(metric_date), COUNT(*) FROM algo_performance_metrics WHERE metric_date >= CURRENT_DATE - 5;
   ```
   Both should show today's date. If missing: loaders likely failed or didn't trigger.

3. **Check EventBridge rule status:**
   - Rule names: `algo-compute_circuit_breakers-schedule`, `algo-compute_performance_metrics-schedule` (Terraform: `/terraform/modules/loaders/main.tf`)
   - State: "ENABLED" in AWS EventBridge console
   - If disabled: re-enable and investigate reason for disable

4. **Check ECS task logs:**
   - CloudWatch log groups: `/ecs/algo-compute_circuit_breakers-loader`, `/ecs/algo-compute_performance_metrics-loader`
   - Look for "SUCCESS: 1 circuit breaker records computed" (circuit_breakers) or "SUCCESS: 1 performance metric records computed" (performance_metrics)
   - If missing or error: loader crashed; check full log for DatabaseError, timeout, or connection pool issues

5. **Manual trigger (testing only):**
   ```bash
   aws ecs run-task --cluster algo-cluster-dev --task-definition algo-compute_circuit_breakers-loader --launch-type FARGATE --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}"
   ```

**Alert conditions:** CloudWatch alarms configured for:
- No loader execution in 25+ hours (checked hourly)
- ECS task exit code non-zero (dead-letter queue monitoring)

If alarms trigger:
1. Check EventBridge rule state (enabled?)
2. Check ECS task definition (LOADER_NAME env var matches loader filename)
3. Check DynamoDB loader_locks table (orphaned lock from crash?)
4. Manually run task above to diagnose error in logs

## Data Freshness Configuration

**Configurable thresholds (algo_config table):**
- `phase1_min_symbol_count` (default 5000) — minimum symbols required for Phase 1 to pass
- `phase1_min_coverage_pct` (default 75) — minimum coverage % vs prior day
- `SIGNAL_STALE_THRESHOLD_HOURS` (default 24) — signal quality threshold
- `PIPELINE_HEALTHY_DAYS` (default 2) — healthy status threshold
- `PIPELINE_CRITICAL_DAYS` (default 7) — critical status threshold

**Price data coverage:** Recent loads complete ~5,600 symbols per date (partial coverage acceptable if >5000 and >=75% vs prior day). Phase 1 passes if both thresholds met.

**Weekend/holiday handling:** Automatically extends 1-2 days on weekends (no false stale warnings)

## Orchestrator Phases

1. **Phase 1:** Data freshness check (FAIL-CLOSED) — halt if price_daily/market_health_daily/market_exposure_daily >1 trading day old; warns on trend_template_data/swing_trader_scores/stock_scores/sector_ranking/buy_sell_daily
2. **Phase 2:** Circuit breakers (FAIL-CLOSED) — halt if any breaker triggered (drawdown ≥20%, daily loss ≥2%, consecutive losses ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%)
3. **Phase 3:** Position monitor + market exposure policy
4. **Phase 4:** Execute exits (always runs, unblocked by halt)
5. **Phase 5:** Signal generation (blocked by halt)
6. **Phase 6:** Trade entries (blocked by halt)
7. **Phase 7:** Reconciliation + reporting (always runs, unblocked by halt)

## Signal Generation (Phase 5)

**Primary: Pivot-breakout BUY signals filtered by quality ranking.** Combines buy_sell_daily technical breakout timing with stock_scores fundamental quality to generate high-conviction entries at key inflection points.

Pipeline:
1. Check halt flag (set by Phase 1 on stale data)
2. Market regime gate: halt if `market_exposure_daily.is_entry_allowed = false`
3. Exposure policy gate: halt if `exposure_constraints.halt_new_entries = true` (from Phase 3b)
4. **Primary path:** Fetch `buy_sell_daily` BUY signals within last 3 calendar days (covers 2 trading days, tolerant of weekends)
   - Must have signal_type='BUY' (pivot high > recent swing high AND swing high > SMA_50)
   - JOIN to `stock_scores` (composite_score >= 50)
   - JOIN to current `price_daily` + SMA_50 + `company_profile` for sector/industry
5. **Fallback:** If no buy_sell_daily BUY signals (e.g., morning runs before EOD loader runs at 4:05 PM ET), use stock_scores + price_daily without breakout gate
6. Trend filter: skip if close < sma_50 (uptrend confirmation)
7. Close quality gate: skip if close in bottom 40% of day's range (distribution signal)
8. Liquidity check on top 10 candidates (parallelized)
9. Return composite-score-ranked candidates to Phase 6

**Signal source logic:**
- `buysell_breakout`: buy_sell_daily BUY signals found (preferred, highest conviction)
- `stock_scores_fallback`: no fresh buy_sell_daily BUY signals available (early morning before EOD pipeline)

**Ranking:** composite_score from stock_scores (quality 25%, growth 20%, value 20%, positioning 15%, stability 12%, momentum 8%).

**Position limits:** Max 8 sector, max 5 industry (configurable via algo_config table)

## Infrastructure Constraints

**RDS (db.t4g.small, 2GB RAM):**
- ~100 concurrent connections max (safety threshold: 350)
- statement_timeout: 15 minutes (supports batch loaders with 5000+ symbols)
- work_mem: 16MB per sort operation
- effective_cache_size: 768MB (75% of RAM)

**Lambda API (256 MB, 25s timeout, 1 provisioned concurrency):** Warm container, prevents VPC cold-start. Deployed at `algo-api-dev`. Environment: 3 layers (API deps + psycopg2 + shared dependencies). Credentials: RDS via Secrets Manager, Alpaca/FRED via algo-secrets-dev. VPC-enabled with 2 private subnets for database access. CORS: Allows CloudFront domain, localhost:3000, localhost:5173.

**Lambda Orchestrator (512 MB, 600s timeout):** Pre-warmed at 9:25 AM (5 min before market open)

**CloudFront Domain:** Stored in AWS Secrets Manager (algo/cloudfront-domain), fetched at Lambda cold-start

**Trading Mode:** `alpaca_paper_trading = true` (paper mode via paper-api.alpaca.markets). To switch to live: (1) GitHub Actions → update-credentials.yml → set trading_mode=live, (2) Change terraform.tfvars to alpaca_paper_trading=false, (3) Push

**Environment Naming:** `environment = "dev"` (all AWS resources named `-dev`). Change to `prod` if staging provisioned in same account.

## Data Integrity & Resilience

**Technical Data Enrichment Pipeline:**
- `load_technical_data_daily_vectorized.py` (async, optimized for 5000+ symbols)
- `enrich_buy_sell_daily_technical.py` (post-processing backfill for incomplete loads)

Technical indicators (RSI, SMA_50, SMA_200, EMA_21, ADX, ATR, Mansfield_RS) are computed daily by the vectorized loader and stored in `technical_data_daily`. When the loader completes with < 70% coverage (normal: 80-83%), `buy_sell_daily` signals may have NULL technical columns. The enrichment script automatically backfills these from `technical_data_daily` after the loader finishes.

**Execution order:**
1. Morning/EOD pipeline: `load_technical_data_daily_vectorized.py` (2:15 AM, 4:05 PM ET)
2. Subsequent: `load_buy_sell_daily.py` (same pipeline, expects tech data to be available)
3. Backfill (if needed): `enrich_buy_sell_daily_technical.py` (manual or automated post-load)

This design tolerates incomplete upstream data and ensures signals always have technical data when available.

## Halt Flag Architecture (DynamoDB + RDS Redundancy)

**Problem Solved:** Previously, halt flag was stored only in DynamoDB, creating a single point of failure. Any DynamoDB outage would halt all trading even if the underlying reason for the halt had cleared.

**Solution (FIXED):** Dual-storage with intelligent fallback.

**Storage Strategy:**
- **Write:** Always write halt flag to both DynamoDB and RDS (`algo_runtime_state` table)
- **Read:** Try DynamoDB first (fast), fall back to RDS if DynamoDB unavailable
- **Circuit Breaker:** If DynamoDB fails >3 times in 5 minutes, skip DynamoDB reads and use RDS only (prevents cascade failure)

**Implementation:**
- Core logic: `utils/db/halt_flag.py` (HaltFlagManager class)
- Database backing: `algo_runtime_state` table in RDS (added to schema.sql)
- Orchestrator integration: `algo/algo_orchestrator.py` uses HaltFlagManager instead of direct DynamoDB calls
- Failover: If both storages unavailable, fail-closed (conservatively assume halt for safety)

**TTL & Cleanup:**
- Halt flag records have `expires_at` field (24h TTL)
- Can be manually cleaned up: `DELETE FROM algo_runtime_state WHERE expires_at < NOW()`
- Auto-expires halt flag at market open of next trading day (via timestamp comparison in HaltFlagManager)

**Monitoring:**
- Log entries: `[HALT_FLAG]` prefix for all halt flag operations
- Metric: `HaltFlagCheckFailure` emitted when both storages unavailable
- CloudWatch alarm: Monitor for repeated HaltFlagCheckFailure metrics (indicates infrastructure issue)

## Known Limitations & Mitigations

**F-01 (Position monitoring pricing):** Position monitor uses daily closing prices from the database (price_daily table) for all price data. Real-time pricing fallback chains were removed as dead code.

**F-02 (Halt flag redundancy):** Halt flag now uses dual-storage (DynamoDB + RDS) with circuit breaker pattern. Single storage failure no longer halts all trading. If both storages unavailable, fails closed for safety (conservative approach).

**F-03 (Portfolio optimization):** numpy deployed to Lambda layer. Phase 7 executes weight optimization.

**Analytics loader OOM risk:** company_profile, analyst_sentiment, etc. auto-killed if running >2 hours during pre-flight checks (prevents RDS OOM).

**Morning prep completion:** Must finish before 9:30 AM. Currently completes in 5-5.5h (start 2:00 AM = 1-1.5h buffer). Monitor CloudWatch if approaching deadline.

## Dashboard Setup

### Browser Dashboard (Vite Dev Server)

**One-time PowerShell profile setup (run this, do not hardcode values):**
```powershell
# This fetches all credentials dynamically from Secrets Manager:
scripts/setup-local-dev.ps1
```

The script writes `VITE_PROXY_TARGET`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, and other
required vars to the PowerShell profile, sourced from `algo/dashboard-config` in Secrets Manager.

**Run dev server:**
```powershell
cd webapp/frontend && npm run dev
```

Behavior:
- Public pages (markets, economic, sectors, sentiment, scores, deep-value) load with AWS data immediately
- Protected pages (algo-dashboard, portfolio, trades, admin) redirect to `/login`
- Login with Cognito email (argeropolos@gmail.com) to access protected pages
- Vite proxy transparently routes `/api/*` requests to AWS API Gateway (no CORS issues)

### Terminal Dashboard (Python Tool)

**Run (no additional setup required):**
```powershell
.\run-dashboard.ps1                    # Live view
.\run-dashboard.ps1 -Watch 60          # Auto-refresh every 60s
.\run-dashboard.ps1 -Legend            # Print legend/guide
```

Behavior:
- Fetches API URL + Cognito credentials from Terraform outputs (or uses hardcoded fallback if local)
- Prompts for Cognito login interactively
- Displays real-time metrics from AWS
- If AWS credentials expired, run: `scripts/refresh-aws-credentials.ps1`

## Key Files

- `algo/algo_orchestrator.py` — 7-phase orchestrator
- `lambda/api/lambda_function.py` — REST API
- `terraform/main.tf` — infrastructure as code
- `lambda/db-init/schema.sql` — database schema (3031 lines)
- `loaders/load_*.py` — data loaders
- `tools/dashboard/` — terminal dashboard
- `run-dashboard.ps1` — convenience wrapper (auto-fetches credentials)

## Configuration

All trading parameters in `algo_config` table (configurable without deploy). Infrastructure parameters require Terraform deploy.

**Database:** Schema single source of truth. All code uses `DatabaseContext` context manager.

**API Gateway:** Uses `$default` stage (intentional). CloudFront preserves `/api/` path.

## API Response Format

All responses include `statusCode` root field:

```json
{ "statusCode": 200, "data": { ... } }
{ "statusCode": 200, "items": [...], "total": 100, "limit": 50, "offset": 0 }
{ "statusCode": 404, "errorType": "not_found", "message": "..." }
```

Response helpers: `success_response(data)`, `list_response(items, total, ...)` in `lambda/api/routes/utils.py`

## GitHub Actions Workflows

**Production Auto (4):** deploy-all-infrastructure.yml, deploy-staging.yml, ci-fast-gates.yml, build-push-ecr.yml

**Scheduled (3):** run-fred-loader.yml (5 AM ET), rotate-developer-credentials.yml (quarterly), verify-both-envs.yml (6h)

**Infrastructure (2):** build-lambda-layer.yml, verify-and-init-db.yml (manual dispatch)

**Credentials (4):** rotate-developer-credentials.yml, rotate-credentials-simple.yml, update-credentials.yml, refresh-dev-credentials.yml

**Manual (3):** manual-invoke-loaders.yml, manual-invoke-orchestrator.yml, test-and-debug.yml

**Test (1):** reset-cognito-test-user.yml

## Error Handling & Data Quality

**API Error Consistency:** Routes return HTTP 200 with empty arrays for missing optional data. Phase 1 monitors freshness. Fallback chain: primary API → in-memory cache → hardcoded zeros (with _is_fallback_data flag).

**Data Patrol:** Monitors staleness, coverage, and sanity thresholds (parameterized via algo_config). Can adjust without code changes.

**Loader Status Monitoring:** `data_loader_status` table tracks RUNNING/COMPLETED/FAILED. DynamoDB fallback with 1-hour TTL.

**Circuit Breaker Status:** Distributed DynamoDB lock (`orchestrator-run-lock`) prevents concurrent orchestrator executions. 600-second expiration.

## Data Encryption at Rest

**Implementation:** All data stored at rest is encrypted using customer-managed KMS keys for compliance (SOC2, PCI-DSS).

**RDS Database Encryption:**
- Customer-managed KMS key (not AWS-managed default)
- Enabled via `enable_rds_kms_encryption = true` in Terraform (line 940 in variables.tf)
- KMS key alias configurable via `rds_kms_key_alias` variable
- Rotation: KMS keys have automatic annual key rotation enabled

**S3 Bucket Encryption:**
- All S3 buckets support customer-managed KMS encryption
- Configurable via `s3_encryption_kms_key_id` variable in Terraform
- Buckets with encryption: code, lambda_artifacts, data_loading, log_archive, frontend
- Default: AES256 (AWS-managed); can be switched to customer-managed KMS by setting `s3_encryption_kms_key_id`
- Enforcement: Set `enforce_s3_kms_encryption = true` to deny unencrypted uploads

**Secrets Manager Encryption:**
- All secrets automatically encrypted by AWS Secrets Manager using default service key
- Customer-managed KMS key support available if needed (configure in AWS console)

**Database Backups:**
- RDS automated backups inherit database encryption settings
- Final snapshots use same KMS key as database
- Backup retention: 1-7 days (configurable)

## Lambda API Configuration

**Lambda Function Configuration:**
- Function name: `algo-api-dev`
- Runtime: Python 3.12
- Memory: 256 MB
- Timeout: 25 seconds (API Gateway hard limit: 29s)
- Provisioned concurrency: 1 (keeps one container warm, prevents cold-start 502 errors)
- Reserved concurrency: 50 (supports 26 concurrent dashboard calls from MarketsHealth + headroom)
- VPC: Enabled with 2 private subnets for RDS access
- Layers: API dependencies + psycopg2 + shared (numpy/pandas/scipy)

**Secrets Manager Configuration (VPC Cold-Start):** Increased timeouts to handle VPC cold-start latency: Secrets Manager connect timeout 10s (was 2s), read timeout 15s (was 3s). This prevents 503 "Database connection failed" errors on first invocation.

**Environment Configuration:**
- DB_HOST: RDS Proxy endpoint (`algo-rds-proxy-dev.proxy-...rds.amazonaws.com`)
- DB_SECRET_ARN: Fetched from Secrets Manager at cold-start
- CLOUDFRONT_DOMAIN: Set dynamically at deployment (e.g., `https://d2u93...cloudfront.net`)
- COGNITO_USER_POOL_ID: Set from deployed Cognito user pool
- ALGO_SECRETS_ARN: Alpaca API keys from Secrets Manager

**Health Check:**
- Endpoint: `/api/health` (no auth required)
- Returns: `statusCode: 200` with system health snapshot (RDS connections, data freshness, import status)
- Example response: `{"status": "healthy" | "degraded" | "critical", "rds_connection_pool": {...}, "freshness": {...}}`

**Database Connectivity:**
- RDS Proxy acts as connection pool manager
- Expected connections during active requests: 20-30 (from 48-96 loader connections via proxy)
- Timeout errors: Check RDS Performance Insights for slow queries (7-day free tier)
- Connection refusal: Check security group ingress rules (must allow port 5432 from Lambda SG)

**Testing Lambda API:**
```bash
# Direct invocation (for debugging)
aws lambda invoke --function-name algo-api-dev \
  --payload '{"httpMethod":"GET","path":"/api/health"}' \
  --log-type Tail response.json
cat response.json

# Via API Gateway (production path)
curl https://<api-gateway-endpoint>/api/health
```

## Troubleshooting

**"Error: The security token included in the request is invalid" when running loaders/scripts:**
- Credentials may have expired (check: `scripts/credential-cache-status.ps1`)
- Cache corrupted: Clear and refresh: `scripts/credential-cache-status.ps1 -Action Clear; scripts/refresh-aws-credentials.ps1`
- AWS access revoked: Contact administrator or run `scripts/refresh-aws-credentials.ps1` to fetch new credentials from Secrets Manager

**Lambda returns 502 Bad Gateway (VPC cold-start timeout):**
- Cause: VPC cold-start (15-40s) exceeds API Gateway timeout (29s). Provisioned concurrency should prevent this.
- Check: Is provisioned concurrency enabled? `aws lambda get-provisioned-concurrency-config --function-name algo-api-dev`
- Fix: Ensure terraform.tfvars has `api_lambda_provisioned_concurrency = 1`
- Workaround: Client should retry with exponential backoff (retry after 2s)

**Lambda returns 5xx error (internal):**
- Check Lambda logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
- Check database connectivity: Verify RDS Proxy is reachable from Lambda (security group rules)
- Check credentials: Lambda environment variables include DB_SECRET_ARN (should be decrypted at runtime)
- Check Lambda layer: Verify psycopg2 layer is deployed (`aws lambda get-function --function-name algo-api-dev`)

**Phase 1 halts on stale data:**
- Check `DATA_FRESHNESS_MAX_HOURS` (may need increase for holidays)
- Check morning prep pipeline completion: `scripts/orchestrator-history.py recent 1`
- Check yfinance status: `curl https://query1.finance.yahoo.com/...`

**API route failures:**
- Check Lambda logs: `aws logs filter-log-events --log-group-name /aws/lambda/algo-api-dev --filter-pattern "FAILED"`
- Syntax check: `python -m py_compile lambda/api/routes/algo.py`

**RDS connection saturation:**
- Check CloudWatch DatabaseConnections metric during EOD (4:05-5:30 PM ET)
- Check for slow queries: RDS Performance Insights (7-day free)
- Reduce loader parallelism if needed: `scripts/update-loader-parallelism.py`

**Orchestrator lock timeout:**
- Another instance still running
- Check CloudWatch logs for "Lock acquisition failed"
- Verify no ECS tasks stuck: `aws ecs list-tasks --cluster algo-cluster`


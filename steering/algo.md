# Stock Analytics Platform: Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions. Reconciles with Alpaca daily.

## System Map

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator (7 phases) | `algo/algo_orchestrator.py` | Lambda algo-algo-dev | EventBridge: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri |
| Loaders (6 core + supporting) | `loaders/load_*.py` | ECS Fargate | 6 core via Step Functions (2:15 AM, 4:05 PM ET); supporting loaders async |
| API | `lambda/api/lambda_function.py` | Lambda algo-api-dev | HTTP requests |
| Frontend | `webapp/frontend/src/` | S3 + CloudFront | npm run build |
| Database | PostgreSQL | RDS algo-db | Schema: `lambda/db-init/schema.sql` |

## Credentials

**Local dev (PowerShell profile):** DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, FRED_API_KEY

**Production (AWS Secrets Manager):** algo/database, algo/alpaca, algo/fred

**CI (GitHub Secrets):** API keys + AWS_ACCOUNT_ID, RDS_PASSWORD

**Rules:** Rotate quarterly (first Monday of each quarter). If leaked, rotate immediately. Never commit .env files. OIDC for GitHub Actions (no static keys).

**Credential Refresh (if expired):**
```powershell
scripts/refresh-aws-credentials.ps1
```

## Deployment

**Frontend Build:** Reads API URL + Cognito config at build time. Injects cache-bust parameter to `index.html` (prevents stale config.js). Four-layer cache invalidation (S3 headers + CloudFront + browser fetch + parameter).

**Production:** `git push main` → deploy-all-infrastructure.yml (Terraform + Lambda + frontend + migrations)

**Staging:** `git push staging` → deploy-staging.yml (dry-run, separate Lambda, shared RDS)

**Database:** Schema applied exclusively by GitHub Actions workflow, NOT by Terraform (avoids race conditions and state drift).

## Data Architecture: Positions

**Single Source of Truth:** `algo_positions` table
- `algo_positions_with_risk` view: enriched with stops, targets, risk metrics (used by dashboard)
- `open_positions` view: filtered for OPEN/PARTIALLY_EXITED only
- Legacy `positions` table DROPPED (was empty, replaced by algo_positions in Phase 3)

**Data flow:** Orchestrator Phase 6 updates position state → Phase 7 calls `compute_position_metrics()` → Dashboard queries enriched view

## Schedule (Daily, Mon-Fri)

**2:00 AM ET:** morning-prep-pipeline (Step Functions) — loads prices + market health + swing_trader_scores (5-5.5h) before 9:30 AM deadline

**2:40 AM ET:** Load SP500/Russell constituents (EventBridge)

**4:05 PM ET:** EOD pipeline (Step Functions) — loads prices, market health, algo metrics, swing scores (3-4h)

**4:30 PM ET:** Compute circuit breaker metrics (EventBridge)

**4:45 PM ET:** Compute performance metrics (EventBridge)

**9:30 AM, 1 PM, 3 PM, 5:30 PM ET:** Orchestrator runs (7 phases: freshness, circuit breakers, position monitor, exits, signal generation, entries, reconciliation)

## Loader Configuration

**6 Core Loaders (FAIL-CLOSED):** stock_symbols, stock_prices_daily, swing_trader_scores, market_health_daily, trend_template_data

**28 Supporting Loaders (FAIL-OPEN):** Earnings, sentiment, technical, etc. Continue if they fail.

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

## Pre-Computed Metrics

**circuit_breaker_status table:** Daily snapshot of 9 circuit breaker metrics (portfolio drawdown, daily loss, consecutive losses, open risk, VIX, market stage, SPY change, win rate, trigger count)
- Updated: 4:30 PM ET (2-5 seconds)
- Used by: `/api/algo/circuit-breakers` (now 30ms vs 800ms)

**algo_performance_metrics table:** Daily snapshot of 14 performance stats (win rate, profit factor, Sharpe, Sortino, max drawdown, avg holding days, cagr, streaks)
- Updated: 4:45 PM ET (10-15 seconds)
- Used by: `/api/algo/performance` (now 20ms vs 1200ms)

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

1. **Phase 1:** Data freshness check (FAIL-CLOSED) — halt if SPY/market_health/trend_template >1 trading day old
2. **Phase 2:** Circuit breakers (FAIL-CLOSED) — halt if any breaker triggered (drawdown ≥20%, daily loss ≥2%, consecutive losses ≥3, open risk ≥4%, VIX ≥35, market stage=4, weekly loss ≥5%, win rate <40%)
3. **Phase 3:** Position monitor + market exposure policy
4. **Phase 4:** Execute exits (always runs, unblocked by halt)
5. **Phase 5:** Signal generation (blocked by halt)
6. **Phase 6:** Trade entries (blocked by halt)
7. **Phase 7:** Reconciliation + reporting (always runs, unblocked by halt)

## Signal Generation (Phase 5)

**Vectorized on-the-fly computation** from price_daily (no pre-computed dependency):
1. Fetch 300-day OHLC history for all symbols in ONE query (bulk load)
2. Compute Minervini + Weinstein + power_trend in **parallel** for all symbols using NumPy
3. Apply hard gate: skip if Minervini template fails (8 criteria)
4. Quality score: Minervini-scaled (30-40) + Weinstein Stage 2 (+20) + VCP (+20) + base (+15) + power (+5) = 100 max, min 50
5. Close quality gate: skip if close in bottom 40% of range
6. Liquidity check on top 10 candidates (parallelized)
7. SwingScore 7-component ranking (disabled for speed, using quality ranking instead)

**Performance (verified 2026-06-10 test):**
- 9,940 symbols → 33.4 seconds (19x faster than sequential)
- 3,294 passed Minervini gate (33%)
- 1,211 qualified at quality >=50 (12%)
- 8 final signals with quality 80-95

**Position limits:** Max 8 sector, max 5 industry (configurable via algo_config table)

**Signal freshness check:** Logs warning if swing_trader_scores >1 day old, but doesn't halt (Phase 1 already halted on stale data)

## Infrastructure Constraints

**RDS (db.t4g.small, 2GB RAM):**
- ~100 concurrent connections max (safety threshold: 350)
- statement_timeout: 15 minutes (supports batch loaders with 5000+ symbols)
- work_mem: 16MB per sort operation
- effective_cache_size: 768MB (75% of RAM)

**Lambda API (256 MB, 28s timeout, 1 provisioned concurrency):** Warm container, prevents VPC cold-start

**Lambda Orchestrator (512 MB, 600s timeout):** Pre-warmed at 9:25 AM (5 min before market open)

**CloudFront Domain:** Stored in AWS Secrets Manager (algo/cloudfront-domain), fetched at Lambda cold-start

**Trading Mode:** `alpaca_paper_trading = true` (paper mode via paper-api.alpaca.markets). To switch to live: (1) GitHub Actions → update-credentials.yml → set trading_mode=live, (2) Change terraform.tfvars to alpaca_paper_trading=false, (3) Push

**Environment Naming:** `environment = "dev"` (all AWS resources named `-dev`). Change to `prod` if staging provisioned in same account.

## Known Limitations & Mitigations

**F-01 (Intraday pricing):** RealtimePricingEngine tries Alpaca Data API → IEX Cloud → YFinance → daily fallback. Market hours (9:30 AM - 4 PM ET): real-time prices. Outside hours or if APIs fail: daily prices from database.

**F-02 (Intraday circuit breaker):** Lambda runs at 10 AM, 12 PM, 3 PM ET (halt if portfolio P&L drops >15%). Updates DynamoDB `orchestrator_halt` flag. Flag auto-expires on prior trading day.

**F-03 (Portfolio optimization):** numpy deployed to Lambda layer. Phase 7 executes weight optimization.

**Analytics loader OOM risk:** company_profile, analyst_sentiment, etc. auto-killed if running >2 hours during pre-flight checks (prevents RDS OOM).

**Morning prep completion:** Must finish before 9:30 AM. Currently completes in 5-5.5h (start 2:00 AM = 1-1.5h buffer). Monitor CloudWatch if approaching deadline.

## Key Files

- `algo/algo_orchestrator.py` — 7-phase orchestrator
- `lambda/api/lambda_function.py` — REST API
- `terraform/main.tf` — infrastructure as code
- `lambda/db-init/schema.sql` — database schema (3031 lines)
- `loaders/load_*.py` — data loaders
- `tools/dashboard/` — terminal dashboard

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

## Troubleshooting

**Phase 1 halts on stale data:**
- Check `DATA_FRESHNESS_MAX_HOURS` (may need increase for holidays)
- Check morning prep pipeline completion: `scripts/orchestrator-history.py recent 1`
- Check yfinance status: `curl https://query1.finance.yahoo.com/...`

**API route failures:**
- Check Lambda logs: `fields @message | filter @message like /ROUTE_IMPORT_STATUS/`
- Syntax check: `python -m py_compile lambda/api/routes/algo.py`

**RDS connection saturation:**
- Check CloudWatch DatabaseConnections metric during EOD (4:05-5:30 PM ET)
- Check for slow queries: RDS Performance Insights (7-day free)
- Reduce loader parallelism if needed: `scripts/update-loader-parallelism.py`

**Orchestrator lock timeout:**
- Another instance still running
- Check CloudWatch logs for "Lock acquisition failed"
- Verify no ECS tasks stuck: `aws ecs list-tasks --cluster algo-cluster`

## Documentation Standards

**Allowed:** steering/*.md (permanent procedures, architecture), git commit messages (what changed & why), memory files (temp guidance only)

**Prohibited:** Session docs at root (STATUS_*.md, EXECUTION_*.md, CHECKLIST.md), one-time scripts at root, logs at root

**Why:** Prevents bloat. Git log + steering docs = permanent source of truth.

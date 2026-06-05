# Stock Analytics Platform: Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions. Reconciles with Alpaca daily.

## System Map

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Lambda algo-algo-dev | EventBridge: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri |
| Loaders (37 total: 10 core + 27 supporting) | `loaders/load_*.py` | ECS Fargate | 10 core via Step Functions EOD pipeline (4:05 PM ET, includes sector_ranking), 27 supporting via EventBridge schedules |
| API | `lambda/api/lambda_function.py` | Lambda algo-api-dev | HTTP requests |
| Frontend | `webapp/frontend/src/` | S3 + CloudFront | npm run build |
| Database | PostgreSQL | RDS algo-db | Schema: `lambda/db-init/schema.sql` |

## Credentials

**Local dev (PowerShell profile):** DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, FRED_API_KEY

**Production (AWS Secrets Manager):** algo/database, algo/alpaca, algo/fred

**CI (GitHub Secrets):** APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, FRED_API_KEY, RDS_PASSWORD, AWS_ACCOUNT_ID

**Rules:** Rotate quarterly (first Monday of each quarter). If leaked, rotate immediately. Never commit .env files. OIDC for GitHub Actions (no static keys).

## Deployment

**Production:** `git push main` triggers deploy-all-infrastructure.yml (Terraform + Lambda + frontend + migrations). Uses GitHub OIDC for AWS auth (temp credentials, auto-expire). deploy-code.yml is for manual/selective runs only.

**Local:** Never run `terraform apply` locally. Use `scripts/refresh-aws-credentials.ps1` only for debugging.

**Staging (N+1):** Push to `staging` branch triggers deploy-staging.yml (dry-run, no schedules). Shares RDS with main, separate Lambda.

**Database Initialization (db-init):** Managed exclusively by GitHub Actions workflow (build-db-init-lambda job in deploy-all-infrastructure.yml), NOT by Terraform. The workflow:
1. Builds db-init Lambda from `lambda/db-init/`
2. Invokes it to apply schema from `lambda/db-init/schema.sql`
3. Removes Lambda after execution (ephemeral resource)

Terraform does NOT create or manage the db-init Lambda. This separation avoids:
- Race conditions (Terraform creating resource while workflow tries to invoke)
- State conflicts (Terraform seeing the Lambda as "unmanaged")
- Deployment churn (54 destroy + 53 add spins when db-init resources shift between tools)

If you need to rebuild the schema:
1. Ensure `lambda/db-init/schema.sql` is current
2. Run GitHub Actions "Deploy All Infrastructure" workflow manually
3. Workflow will automatically create, invoke, and clean up the db-init Lambda

## Schedule

**Daily runs (Mon-Fri):**
- 3:25 AM ET: stock_symbols (EventBridge)
- 3:30 AM ET: sp500/russell constituents (EventBridge)
- 4:30 AM ET: morning-prep-pipeline (Step Functions) — loads 1d prices (stock+etf), technicals, then refreshes buy_sell_daily → signal_quality_scores → swing_trader_scores (fail-open). Ensures signals are always fresh before 9:30 AM even if EOD pipeline ran slow overnight.
- 4:05 PM ET: EOD pipeline (Step Functions, 9 core loaders) — loads all intervals (1d/1wk/1mo), signals, scores, orchestrator dry-run.
- 9:30 AM, 1 PM, 3 PM, 5:30 PM ET: orchestrator (7 phases)

**Loaders:** 37 total (9 core via Step Functions, 28 supporting via EventBridge). Core loaders: stock_symbols, stock_prices_daily, technical_data_daily, market_health_daily, trend_template_data, buy_sell_daily, signal_quality_scores, algo_metrics_daily, swing_trader_scores.

**LOADER_PARALLELISM:** All loaders read thread-pool concurrency from the `LOADER_PARALLELISM` environment variable (set by Terraform ECS task definition). CLI `--parallelism` arg falls back to the env var. Parallelism tuned per loader to prevent database connection pool exhaustion:
- **Critical path loaders**: technical_data_daily (parallelism=2), buy_sell_daily (parallelism=3), signal_quality_scores (parallelism=2), swing_trader_scores (parallelism=2)
- **Analytics loaders**: company_profile (parallelism=2), analyst_sentiment (parallelism=2), stability_metrics (parallelism=2), value_metrics (parallelism=2), growth_metrics (parallelism=2), quality_metrics (parallelism=2)
- **Small loaders**: parallelism=1 to avoid rate limiting or because data size is small
- **Justification**: When 9 core loaders run via Step Functions EOD pipeline concurrently at parallelism=4, they create 36 concurrent database connections, exhausting the RDS Proxy connection pool. Reduced parallelism = longer individual execution time but no connection contention, leading to faster overall pipeline completion.
- **Enforcement**: Parallelism values are defined per-loader in `terraform/modules/loaders/main.tf` (loaders map, each key has `parallelism` field). ECS task definitions automatically receive correct LOADER_PARALLELISM env var. Do NOT override with global settings in task definition revisions.

## Infrastructure Constraints

**CloudFront Domain Hardcoding (Mitigated, Permanent Fix TBD):** `d2u93283nn45h2.cloudfront.net` is hardcoded in `terraform.tfvars` (frontend_origin line 9, api_cors_allowed_origins line 19) due to circular dependency: API Gateway CORS references CF domain, but CF origin references API Gateway. Terraform cannot resolve this automatically.

**Current Mitigation (Verified Workaround):** 
- GitHub Actions workflow `verify-cloudfront.yml` runs daily (10 AM UTC / 5 AM ET) + on-demand dispatch
- Workflow fetches actual CF domain from AWS and compares against hardcoded values
- **If mismatch detected:** Alerts with instructions to update `terraform.tfvars` (lines 9, 19), commit, and push (triggers automatic redeploy)
- Local verification: `./scripts/verify-cloudfront-domain.ps1` (requires AWS CLI + credentials)

**Recommended Permanent Fix (Not Yet Implemented):** Option 1: Secrets Manager (3-4 hour effort)
1. Store CloudFront domain in Secrets Manager: `aws secretsmanager create-secret --name algo/cloudfront-domain --secret-string 'd2u93283nn45h2.cloudfront.net'`
2. Modify `lambda/api/lambda_function.py`: Fetch domain at Lambda startup or on each request (with caching) instead of checking hardcoded terraform.tfvars
3. Remove hardcoded values from terraform.tfvars lines 9, 19 and API Gateway CORS config
4. Result: If CloudFront recreated, domain in Secrets Manager auto-propagates to API without manual terraform.tfvars changes

**Current Action if Mismatch Detected (Until Option 1 Implemented):** Update `terraform.tfvars` with new domain, commit, and push (triggers redeploy).

## Known Limitations

1. **Intraday pricing (F-01 - IMPLEMENTED):** RealtimePricingEngine integrated into position monitor (Phase 3). Tries Alpaca Data API → IEX Cloud → YFinance → daily price_daily fallback. Market hours (9:30 AM - 4 PM ET) during Mon-Fri: fetches real-time prices. Outside market hours or if APIs fail: uses daily prices from database. Position sizing uses real-time prices when available, daily prices as fallback.

2. **Intraday circuit breaker (F-02 - IMPLEMENTED):** Circuit breaker Lambda runs at 10 AM, 12 PM, and 3 PM ET to halt trading if portfolio P&L drops > 15%. Updates DynamoDB `orchestrator_halt` flag; orchestrator Phase 1 checks and fails-closed. Halt flag auto-expires on prior trading day (prevents stale flags from blocking next day's run).

3. **Portfolio optimization (F-03 - IMPLEMENTED):** numpy deployed to Lambda layer. Phase 7 (reconciliation + weight optimization) executes instead of silently failing.

## Analytics Loader OOM Risk

company_profile, analyst_sentiment, stability_metrics, value_metrics iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still running when the orchestrator fires, the t4g.micro RDS OOMs. **MITIGATION**: Orchestrator now automatically kills any analytics loader running > 2 hours during pre-flight checks.

Advisory lock: `OptimalLoader` uses `pg_try_advisory_lock` to prevent duplicate runs. Lock auto-releases on exit/crash. Manual stop if needed: `aws ecs stop-task --cluster algo-cluster --task <ARN>`.

## Loader Failure Monitoring

**Status:** IMPLEMENTED. 9 core loaders (Step Functions) + 28 supporting loaders (EventBridge) with integrated monitoring.

**Implementation:**
- **Core loaders (Step Functions):** Centralized monitoring via state machine
- **Supporting loaders (EventBridge):** ECS task state change rule captures STOPPED/FAILED events and publishes to SNS
- **Consolidated CloudWatch alarm:** Triggers on any supporting loader failure
- **SNS email subscription:** Sends alerts to argeropolos@gmail.com
- **Dashboard:** CloudWatch dashboard (`algo-loader-monitoring-dev`) shows real-time failure count, recent errors, and successful runs per loader

**Alert flow:** Loader fails → EventBridge task state change → SNS → Email alert
**Dashboard:** CloudWatch console → CloudWatch → Dashboards → algo-loader-monitoring-dev

## Morning Prep Pipeline Monitoring (4:30 AM ET)

**Purpose:** The morning prep pipeline loads fresh prices and technicals before 9:30 AM market open, ensuring swing_trader_scores are computed for the orchestrator run.

**Timing Constraints:**
- Start: 4:30 AM ET (after EOD pipeline finishes at ~4:05 PM previous day)
- Must complete before: 9:30 AM ET market open (5 hours available, 4h buffer recommended)
- Steps: stock_prices_daily (1d only) → technical_data_daily + market_health_daily → buy_sell_daily → signal_quality_scores → swing_trader_scores

**Monitoring (Copy-paste ready for CloudWatch Logs Insights):**

1. **Duration tracking:**
   ```
   fields @timestamp, @duration
   | filter ispresent(@duration)
   | stats max(@duration) as max_duration_sec by @logStream
   | sort max_duration_sec desc
   ```

2. **Check for failures in last 24 hours:**
   ```
   fields @timestamp, @message
   | filter @logStream = /morning-prep-pipeline/
   | filter @message like /error|fail|stopped/i
   | stats count() as failures by @message
   ```

3. **Execution timeline (see which step is slow):**
   ```
   fields @timestamp, @logStream, @message
   | filter @logStream = /morning-prep-pipeline/
   | filter @message like /starting|completed|failed/
   | sort @timestamp asc
   ```

**Actions if morning prep exceeds 4 hours:**
- Execution may still complete before 9:30 AM but with low margin for error
- If exceeding 4 hours: check EOD pipeline from previous day (may still be running when morning prep starts)
- Check yfinance rate limiting (stock_prices_daily step) — may need to reduce parallelism
- Check RDS health (CPU, connections, disk I/O)
- If consistently slow: increase ECS task CPU/memory for slow steps

**Implementation:**
- Step Functions state machine `morning-prep-pipeline-dev` with fail-open error handling
- stock_prices_daily: TimeoutSeconds=5400 (90 min) with LOADER_INTERVALS="1d" (only daily, not weekly/monthly)
- technical_data_daily + market_health_daily: run in parallel, max 5400s each
- buy_sell_daily + signal_quality_scores + swing_trader_scores: sequential, 3600s each, fail-open
- All steps retry up to 2× on transient failures

**Grace Period (Phase 1):**
- Orchestrator (9:30 AM) allows yesterday's swing_trader_scores if morning prep hasn't finished
- Phase 1 grace period: allows stale data at market open but HALTS if stale at intraday runs (1 PM, 3 PM, 5:30 PM)
- If morning prep consistently misses the window: increase ECS task resources or split into parallel branches

## Loader Execution Time Monitoring & Timeout Prevention

**Current Design:**
- Stale data failsafe uses async (Event) invocation: trigger loader and proceed immediately. Circuit breakers in Phase 2+ conservatively handle stale data while loader runs in parallel.
- stock_prices_daily loads 5000+ symbols across 3 intervals (1d, 1wk, 1mo) and 2 asset classes = 30,000+ API requests
- Batch fetching (batch_size=100) reduces API calls 50x. Actual execution time: 1.5-2 hours with parallelism=8
- Step Functions timeout: 27000s (7.5h), ECS timeout: 25200s (7h)

**Execution Time Monitoring:**

1. **CloudWatch Metrics:**
   - Metric: `LoaderDurationSeconds` (namespace: `algo/Loaders`, dimensions: table_name)
   - Published by each loader via `MetricsPublisher.put_loader_result()`
   - Available in CloudWatch console: Metrics → algo/Loaders → LoaderDurationSeconds

2. **CloudWatch Logs Insights Query (copy-paste ready):**
   ```
   fields @timestamp, @duration, @logStream
   | filter @message like /duration_sec|LoaderDurationSeconds/
   | stats avg(@duration) as avg_sec, max(@duration) as max_sec, count() as runs by @logStream
   | sort max_sec desc
   ```

3. **Manual Verification:**
   ```bash
   # List recent execution times for all loaders
   aws logs start-query \
     --log-group-name /ecs/algo-loader \
     --start-time $(date -d '1 day ago' +%s) \
     --end-time $(date +%s) \
     --query-string 'fields @timestamp, @logStream, @message | filter @message like /duration_sec/ | stats max(@duration) by @logStream'

   # Check specific loader duration (example: stock_prices_daily)
   aws logs tail /ecs/algo-loader --follow | grep -i "price_daily" | grep "duration_sec"
   ```

4. **Step Functions Execution Monitoring:**
   - AWS Console → Step Functions → `algo-eod-pipeline-dev` → Executions tab
   - Look for execution duration in the "Execution summary" card
   - If execution time > 7h, Step Functions will timeout

**Rate Limiting Mitigation:**
- **yfinance:** Batch fetching (batch_size=100) reduces API calls 50x (5000 symbols → 50 API calls). Retry logic: 5 max attempts with exponential backoff.
- **Alpaca:** Paper API has higher rate limits. Current parallelism=8 stays well within limits.
- **FRED:** Single endpoint, low call volume, no observed rate-limiting.

**If Timeout Still Occurs (Troubleshooting):**

1. **Check the symptom:**
   - CloudWatch logs show `TASK STATUS: STOPPED` with high runtime (> 7h)
   - Step Functions execution failed after 27000 seconds (7.5h)

2. **Root cause analysis:**
   - Check yfinance API status: `curl -s https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL 2>&1 | head -c 100`
   - Check RDS connections: `aws rds describe-db-instances --db-instance-identifier algo-db --query 'DBInstances[0].DBInstanceStatus'`
   - Check for network issues: `aws logs tail /ecs/algo-loader --grep "timeout\|connection"`

3. **Action:**
   - If yfinance is slow: wait for recovery (usually recovers within hours)
   - If RDS is slow: check DiskQueueDepth and CPU in CloudWatch RDS metrics
   - If network: check security groups allow egress to port 443 for all AWS services
   - Step Functions auto-retries 2x before failing; monitor for success on retry

**Data Availability (Time-Based Constraints):**
- **Loaders run at 3:25-4:05 AM ET:** Market is closed; previous day's data is available immediately after market close (4 PM ET previous day)
- **Pipeline completes before 9:30 AM:** Ensures data is fresh for Phase 1 freshness check
- **No intraday data issues:** Orchestrator intraday pricing (Phase 3) only active 9:30 AM - 4 PM ET Mon-Fri; uses fallback to daily prices outside market hours

## Orchestrator Phases

1. **Phase 1:** Data freshness (halt if stale) — **FAIL-CLOSED**
   - Halts if SPY price data > 1 trading day old
   - Halts if market health data > 1 trading day old
   - Halts if trend template data > 1 trading day old
   - Uses trading-day-aware freshness (accounts for weekends/holidays)
2. **Phase 2:** Circuit breakers (halt if triggered) — **FAIL-CLOSED**
   - Portfolio drawdown ≥ 20%
   - Daily loss ≥ 2%
   - Consecutive losses ≥ 3 trades
   - Total open risk ≥ 4% of portfolio
   - VIX ≥ 35 (extreme fear)
   - Market stage = 4 (confirmed downtrend)
   - Weekly loss ≥ 5%
   - Prior-day market health (SPY down >2% yesterday)
   - Win rate floor < 40% (on 30-trade sample)
3. **Phase 3:** Position monitor
4. **Phase 3b:** Market exposure policy
5. **Phase 4:** Execute exits (unblocked by halt flag, must always run)
6. **Phase 4b:** Pyramid adds
7. **Phase 5:** Signal generation (blocked by halt flag)
8. **Phase 6:** Trade entries (blocked by halt flag)
9. **Phase 7:** Reconciliation + reporting (unblocked by halt flag, must always run)

**Fail-Closed Guarantee:** Phases 1-2 are fail-closed. If data is uncertain or any circuit breaker fires, the orchestrator halts new entries immediately. Phases 3-7 are fail-open (continue without entries). Exit execution (Phase 4) and portfolio reconciliation (Phase 7) always run regardless of halt state to manage existing risk.

## Staging Environment Isolation

**How it works:**
1. Staging Lambda queries for `algo-db-staging` on every deploy
2. If found, uses staging RDS (isolated — prevents data corruption)
3. If not found, falls back to dev RDS with warning logged to GitHub Actions

**To enable staging isolation (optional, costs ~$12/month):**
```bash
./scripts/setup-staging-infrastructure.sh
```

**To disable later (recover cost):**
```bash
terraform workspace select staging
terraform destroy -var-file=terraform.staging.tfvars
terraform workspace select default
terraform workspace delete staging
```

## Configuration

All trading parameters in `algo_config` database table. Changes take effect on next Lambda invocation (max 3 hours). No code deploy needed. Infrastructure parameters (execution_mode, dry_run, paper_trading) require deployment via Terraform.

## Database

Schema: `lambda/db-init/schema.sql` (single source of truth). All code must use `DatabaseContext` context manager. No manual commit/close calls.

## API Gateway

Uses `$default` stage (intentional). CloudFront preserves `/api/` path. Health check endpoints return 200 even if DB unavailable.

## Key Files

- `algo/algo_orchestrator.py`: main 7-phase loop
- `algo/algo_signals.py`: signal generation
- `lambda/api/lambda_function.py`: REST API
- `terraform/main.tf`: infrastructure as code
- `lambda/db-init/schema.sql`: database schema (3031 lines)

## Authentication & Email

**Cognito User Pool:** `algo-pool-dev` (us-east-1). See `steering/EMAIL_DELIVERY_SETUP.md` for setup guide.

**Architecture:** Cognito password reset → CustomMessage trigger → Lambda → SES → User inbox.

## Live Trading Readiness

- Authentication: ✓ ENABLED (cognito_enabled = true)
- Email: Configured via SES + Cognito custom email triggers. See `steering/EMAIL_DELIVERY_SETUP.md` for setup.
- RDS: ✓ UPGRADED to t4g.small (2GB, ~100 connections) + tuned loader parallelism (2-3 per critical loader) = 20-30 typical concurrent connections (well below limit)
- API Lambda: Provisioned concurrency enabled (1 unit) — prevents VPC cold-start timeouts
- Circuit breaker: Halt flag auto-expires on prior trading day; exits always run
- Portfolio optimization: numpy layer deployed; Phase 7 weight optimization executes
- Intraday pricing: RealtimePricingEngine fetches live prices (Alpaca → IEX → YFinance); falls back to daily prices
- Loader monitoring: CloudWatch dashboard + SNS alerts on task failures
- Stale data failsafe: ✓ ASYNC trigger — loader runs in parallel, orchestrator proceeds with caution while Phase 2+ circuit breakers handle uncertainty

**⚠️ Environment Naming:** `environment = "dev"` in terraform.tfvars (all AWS resources named `-dev`). Rename to `prod` if staging is provisioned in same account.

**⚠️ Trading Mode:** `alpaca_paper_trading = true` (PAPER mode via `paper-api.alpaca.markets`). To switch to live:
1. Run GitHub Actions → `update-credentials.yml` → set `trading_mode=live`
2. Change `alpaca_paper_trading = false` in `terraform.tfvars`
3. Push → triggers deploy

## GitHub Actions Workflows

17 workflows (down from 25). Strategic consolidation maintains all functionality while reducing UI clutter and complexity.

**Production Auto-Triggered (4 workflows):**
- `deploy-all-infrastructure.yml` — Main deployment (push main): Terraform + code + migrations + frontend
- `deploy-staging.yml` — Staging deployment (push staging): dry-run, separate Lambda
- `ci-fast-gates.yml` — Pre-commit gating (push main): lint, unit tests, secret scanning
- `build-push-ecr.yml` — Build container image (push main, on code changes): detects loaders/*, Dockerfile, requirements.txt

**Production Scheduled (3 workflows):**
- `run-fred-loader.yml` — 5 AM ET Mon-Fri: Load FRED economic data (production requirement)
- `rotate-developer-credentials.yml` — Quarterly (Feb/May/Aug/Nov): Auto-rotate AWS IAM keys via Terraform
- `verify-both-envs.yml` — Every 6 hours: Health check across prod/staging

**Infrastructure Builds (2 workflows):**
- `build-lambda-layer.yml` — Manual dispatch: Build shared-deps Lambda layer
- `verify-and-init-db.yml` — Manual dispatch + workflow_call: Initialize/verify database

**Manual Credential Management (4 workflows - keep separate, different credential types):**
- `rotate-developer-credentials.yml` — Scheduled + manual: Auto-rotate OUR AWS IAM key (Terraform-based)
- `rotate-credentials-simple.yml` — Manual only: Fallback AWS IAM rotation when Terraform broken (AWS CLI-based)
- `update-credentials.yml` — Manual dispatch: Sync third-party API keys (Alpaca, FRED) to Secrets Manager
- `refresh-dev-credentials.yml` — Manual dispatch: Export dev credentials for local ~/.aws/credentials

**Manual Invocation (2 workflows):**
- `manual-invoke-loaders.yml` — Manual dispatch with loader_type selector: Invoke specific ECS loader task
- `manual-invoke-orchestrator.yml` — Manual dispatch: Simple orchestrator Lambda invocation

**Testing & Diagnostics (1 unified workflow):**
- `test-and-debug.yml` — Manual dispatch with scenario selector: 8-option menu consolidating all testing/debugging scenarios

**Test-Specific (1 workflow):**
- `reset-cognito-test-user.yml` — Manual dispatch: Reset Cognito test user password

## Performance Architecture

**API Lambda (256 MB, 28s timeout, 30 reserved concurrency, 1 provisioned concurrency):**
- Provisioned concurrency enabled via Terraform (keeps one container warm to avoid VPC cold-start)
- `statement_timeout` set to 30 seconds at RDS parameter group level (not per-request)
- CloudFront error_caching_min_ttl = 300 for SPA error rewrites

**Orchestrator Lambda (512 MB, 600s timeout, 1 reserved concurrency, 0 provisioned concurrency):**
- Pre-warm schedule: 9:25 AM ET Mon-Fri (5 minutes before market open, dry_run=true)
- Eliminates guaranteed cold start from 5:30 PM → 9:30 AM gap

**RDS (db.t4g.small, 2 GB RAM):**
- Instance provides 2 vCPU, 2GB RAM, ~100 concurrent connections. With tuned parallelism (2-3 per critical loader), typical concurrent connections = 20-30, well below limit. No connection pooling proxy needed.
- Performance Insights: ENABLED (7-day free retention)
- `statement_timeout = 900000ms` (15 minutes) at parameter group level — supports batch loaders processing 5000+ symbols with complex joins
- `work_mem = 16384` (16 MB per sort/hash operation)
- `effective_cache_size = 786432` (768 MB = 75% of 2 GB RAM)
- `random_page_cost = 1.1` (SSD-backed storage)

**CloudFront:**
- Static assets: `Managed-CachingOptimized` (long TTL, compressed)
- API: `Managed-CachingDisabled` (all /api/* requests pass through)
- Client-side: `dataCache.js` caches API responses 5 minutes in-memory

## Error Handling & Diagnostics

**API Error Types (for client-side error handling):**
All API errors return specific error types instead of generic "error" messages, enabling proper debugging:
- `schema_error` (503): Database schema mismatch or migration issue. Action: Check RDS schema version.
- `connection_error` (503): RDS/database connection failed. Action: Verify RDS Proxy and network connectivity.
- `query_error` (503): Database query execution failed. Action: Check CloudWatch logs for SQL error details.
- `auth_error` (403): JWT validation or Cognito authorization failed. Action: Verify token expiry and Cognito config.
- `cognito_config_error` (500): Cognito environment variables not configured. Action: Check Lambda env vars (COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID, COGNITO_REGION).
- `email_verification_error` (500): Cognito email verification operation failed. Action: Check Cognito user pool email sending permissions.
- `data_access_error` (500): Code bug accessing data fields (AttributeError, KeyError, IndexError). Action: Check CloudWatch logs for stack trace.
- `no_data_error` (500): Required data table is empty or missing. Action: Check loader execution and data freshness.
- `data_processing_error` (500): Generic data processing failure. Action: Check loader logs for specific error.
- `timeout` (504): Request exceeded 30-second timeout. Action: Increase RDS statement_timeout or optimize query.
- `invalid_input` (400): Client sent invalid query parameters or request body. Action: Check API parameter validation.

**Response Extraction & Data Safety:**
- Frontend `responseNormalizer.js` safely handles null/undefined values in API responses, filtering out bad items before returning to components.
- All array responses filter null/undefined entries to prevent "Cannot read property .type of undefined" crashes.
- Total pagination counts preserved even after filtering to maintain accurate pagination metadata.

**React Query Retry Strategy:**
- Default retry count increased from 2 to 5 attempts for better resilience during deployments.
- Max backoff timeout: 60 seconds (increased from 30s) to handle RDS restarts and Lambda cold starts.
- Non-retryable errors: 401 (Unauthorized), 403 (Forbidden), 404 (Not Found) — fail immediately.

**Config Loading & Service Worker Management:**
- Frontend config.js wait timeout increased from 5 seconds to 10 seconds to prevent auth failures on slow loads.
- Service Worker and API cache clearing now version-based (only on deploy) instead of every page load, improving performance.
- Smart cache invalidation: clears only API-related caches, not static asset caches.

## Market Calendar & Holiday Handling

**US Market Holidays (2025-2027):** Defined in `algo/algo_market_calendar.py` with early closes (1 PM ET) for days before/after major holidays.

**Edge Cases Handled:**
- **Weekends:** No loaders trigger Sat-Sun. Orchestrator phase 1 checks `MarketCalendar.is_trading_day()` before expecting fresh data.
- **Holidays:** System recognizes US market holidays. Phase 1 freshness checks account for multi-day gaps (e.g., Thanksgiving → Friday closed + Mon-Thu closed = no data for 4 days).
- **Early closes (1 PM ET):** Day before Independence Day, day after Thanksgiving, Christmas Eve. Market health data collected but trading windows differ.
- **Non-trading days in data:** yfinance occasionally returns weekend/holiday rows. `load_prices.py` validates and rejects via `MarketCalendar.is_trading_day()` in transform phase (line 222).

**Phase 1 Staleness Thresholds (accounting for holidays):**
- Working backward from today to find most recent trading day using `MarketCalendar.is_trading_day()`
- Allows 1-3 calendar days of staleness depending on gate (price_daily vs market_health_daily)
- Examples:
  - Today is Monday → expects data from Friday (3 days)
  - Today is Monday after Thanksgiving → expects data from Wednesday (4 days)
  - Any Friday → expects data from Thursday (1 day)

**Loaders Skip Non-Trading Days:**
- Morning prep pipeline (4:30 AM) starts regardless of day, but checks `is_trading_day()` before processing
- EOD pipeline (4:05 PM) only triggers M-F via EventBridge schedule; Step Functions state machine has no holiday check
- FRED economic data loader (5 AM ET Mon) explicitly scheduled Monday-only

**Future Calendar Updates (if adding 2028+):**
1. Update `US_HOLIDAYS` dict in `algo_market_calendar.py` with new holidays
2. Update `EARLY_CLOSES` dict if new early-close dates added
3. No code changes needed — system automatically uses updated calendar
4. Verify NASDAQ/NYSE holiday calendar before adding (sometimes differs on observed dates)

## Recent Fixes (2026-06-05)

**DEPLOYED FIXES:**
1. **Terraform import path** — loader_failure_handler Lambda is in module.services, not module.pipeline. Fixed import statements.
2. **Morning prep parallelization** — Parallelized signal_quality_scores + swing_trader_scores execution. Reduces 6h pipeline to 4h45m, fits in 5h window (4:30-9:30 AM).
3. **Stale data failsafe aggressive** — Halts if failsafe loader fails AND data is 2+ days old. Only proceeds if failsafe succeeded OR data is fresh (1 day old).
4. **Rate limiting cascade** — Progressive batch size reduction instead of per-symbol fallback. Avoids 5000+ API calls with exponential backoff taking 6+ hours.
5. **Data patrol staleness** — 3-hour freshness window instead of complex trading day logic. Prevents false halts from stale patrol results.
6. **ECS scheduling timeout dynamic** — First attempt: 30s poll timeout. Retry: 120s. Accommodates cluster load variability.
7. **Phase 1 logging** — Explicit staleness tolerance logging for debugging.

## Troubleshooting

**Full dataset runs failing (stale data, rate limiting, timing):** All major blockers fixed (2026-06-05). If issues persist:

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. RDS Proxy is enabled (enable_rds_proxy = true) — if timeouts recur, verify proxy endpoint is active: `aws rds describe-db-proxies --region us-east-1`.

**API Lambda 503 errors / protected endpoints returning 401 "Unable to fetch Cognito keys":** The API Lambda is in a private VPC subnet. Cognito IDP is public. The Lambda security group must allow HTTPS (port 443) egress to `0.0.0.0/0` for Cognito JWKS requests via NAT Gateway. If the SG only allows HTTPS to VPC CIDR (10.0.0.0/16), Cognito timeouts after 30s. Fix: add `egress { from_port=443, cidr_blocks=["0.0.0.0/0"] }` to api-lambda SG in `terraform/modules/vpc/main.tf` and apply.

**API Lambda 500 errors on first request (cold start):** VPC cold-start (15-40s) + API Gateway timeout (29s). Provisioned concurrency (1 unit) is wired in Terraform. If 502s recur after deploy, allow 60-90 seconds for PC warm-up. Workaround if PC isn't active: retry (second request works).

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Kill analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics) but keep stock_prices_daily and technical_data_daily running.

**Halt flag stuck:** Use `python scripts/check_halt_flag.py` to check status. `--clear` flag resets it manually if needed. The auto-expiry logic should handle stale flags from prior trading days automatically.

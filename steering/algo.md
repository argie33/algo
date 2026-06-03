# Stock Analytics Platform: Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions. Reconciles with Alpaca daily.

## System Map

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Lambda algo-algo-dev | EventBridge: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri |
| Loaders (37 total: 9 core + 28 supporting) | `loaders/load_*.py` | ECS Fargate | 9 core via Step Functions EOD pipeline (4:30 AM ET), 28 supporting via EventBridge schedules |
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

## Schedule

**Daily runs (Mon-Fri):**
- 3:25 AM ET: stock_symbols (EventBridge)
- 3:30 AM ET: sp500/russell constituents (EventBridge)
- 4:30 AM ET: morning-prep-pipeline (Step Functions) — loads 1d prices (stock+etf), technicals, **then refreshes buy_sell_daily → signal_quality_scores → swing_trader_scores** (fail-open). Ensures signals are always fresh before 9:30 AM even if EOD pipeline ran slow overnight.
- 4:05 PM ET: EOD pipeline (Step Functions, 9 core loaders) — loads all intervals (1d/1wk/1mo), signals, scores, orchestrator dry-run.
- 9:30 AM, 1 PM, 3 PM, 5:30 PM ET: orchestrator (7 phases)

**Loaders:** 37 total (9 core via Step Functions, 28 supporting via EventBridge). Core loaders: stock_symbols, stock_prices_daily, technical_data_daily, market_health_daily, trend_template_data, buy_sell_daily, signal_quality_scores, algo_metrics_daily, swing_trader_scores.

**LOADER_PARALLELISM:** All loaders read thread-pool concurrency from the `LOADER_PARALLELISM` environment variable (set by Terraform ECS task definition). CLI `--parallelism` arg falls back to the env var. Critical path loaders (technical_data_daily, buy_sell_daily, signal_quality_scores, algo_metrics_daily, swing_trader_scores) run at parallelism=4. Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics, growth_metrics, quality_metrics) run at parallelism=1 to avoid yfinance rate limits and RDS saturation.

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

## Known Limitations (Blocking Live Capital)

1. **Intraday pricing (F-01 - IMPLEMENTED):** RealtimePricingEngine integrated into position monitor (Phase 3). Tries Alpaca Data API → IEX Cloud → YFinance → daily price_daily fallback. Market hours (9:30 AM - 4 PM ET) during Mon-Fri: fetches real-time prices. Outside market hours or if APIs fail: uses daily prices from database. Position sizing uses real-time prices when available, daily prices as fallback.

2. **Intraday circuit breaker (F-02 - MOSTLY FIXED):** Circuit breaker Lambda:
   - **FIXED:** Correctly bundles config/ and utils/ modules (was missing, caused ModuleNotFoundError)
   - **FIXED:** Clears halt flag when portfolio variance returns to safe range (was stuck permanently)
   - **FIXED:** Moved from RDS SG to dedicated SG (was using rds_self_postgres as accidental side effect)
   - **FIXED:** Runtime/layer mismatch resolved (was Python 3.12 with 3.11 layer)
   - **FIXED:** P&L variance logic now reads opening snapshot from algo_portfolio_snapshots instead of comparing same data twice
   - Runs at 10 AM, 12 PM, and 3 PM ET to halt trading if portfolio P&L drops > 15%
   - Updates DynamoDB `orchestrator_halt` flag; orchestrator Phase 1 checks and fails-closed

3. **Portfolio optimization (F-03 - FIXED):** numpy + scipy deployed to Lambda layer. Phase 7 (reconciliation + weight optimization) executes instead of silently failing.

## Analytics Loader OOM Risk

company_profile, analyst_sentiment, stability_metrics, value_metrics iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still running when the orchestrator fires, the t4g.micro RDS OOMs. **FIX IMPLEMENTED**: Orchestrator now automatically kills any analytics loader running > 2 hours during pre-flight checks.

Advisory lock: `OptimalLoader` uses `pg_try_advisory_lock` to prevent duplicate runs. Lock auto-releases on exit/crash. Manual stop if needed: `aws ecs stop-task --cluster algo-cluster --task <ARN>`.

## Loader Failure Monitoring (F-04 - IMPLEMENTED)

**Status:** COMPLETE. 9 core loaders (Step Functions) + 28 supporting loaders (EventBridge) with integrated monitoring.

**Implementation:**
- **Core loaders (Step Functions):** Centralized monitoring via state machine (already in place)
- **Supporting loaders (EventBridge):** 
  - ECS task state change rule captures STOPPED/FAILED events and publishes to SNS
  - Consolidated CloudWatch alarm triggers on any supporting loader failure
  - SNS email subscription sends alerts to argeropolos@gmail.com
- **Dashboard:** CloudWatch dashboard (`algo-loader-monitoring-dev`) shows:
  - Real-time loader failure count (5-min aggregation)
  - Recent loader errors: queries logs for FAILED|CRITICAL|Exception keywords
  - Successful runs: counts per loader over last 24 hours
  - Log-based metrics support per-loader filtering without needing application instrumentation

**Alert flow:** Loader fails → EventBridge task state change → SNS → Email alert
**Dashboard:** CloudWatch console → CloudWatch → Dashboards → algo-loader-monitoring-dev

## Full-Universe Data Coverage Fix (2026-06-01)

**Root cause of "subset of data" / algo working with limited stock universe:**

Two bugs limited the algo to evaluating only a fraction of the full 5000+ stock universe:

1. **ETF price loader was loading all non-ETF stocks into ETF tables** (`loaders/load_prices.py`): The ETF asset_class path was using `get_active_symbols()` (5000+ non-ETF stocks) as the symbol list for `etf_price_daily/weekly/monthly`. This doubled the data load from ~300 batches to ~600 batches, causing the ECS task to time out (3h limit) before completing stock price updates for L-Z symbols. Stocks alphabetically in the second half (NFLX, ORCL, TSLA, etc.) had stale/missing price data. **Fix:** ETF price tables now only load the 17 essential ETF symbols (sector ETFs, index ETFs, macro ETFs) they actually need.

2. **RS percentile universe was S&P 500 only** (`algo/signals/signal_base.py`): The Mansfield RS percentile ranking used `WHERE is_sp500 = true` as its universe, returning `None` for the 4500+ non-S&P 500 stocks. This reduced their AdvancedFilters composite quality score by up to 15 points. **Fix:** Universe now uses all non-ETF stocks in `stock_symbols` so every active stock gets a proper RS percentile ranking. The `idx_price_daily_symbol_date` composite index makes this efficient for 5000+ symbols.

**Result:** The algo now evaluates the full 5000+ stock universe with fresh daily price data for all symbols, not just the alphabetical first half.

## Signal Pipeline Reliability (2026-06-01)

**Root cause of "few symbols" / 0-trade days:** When `swing_trader_scores` is empty or stale for the eval date, all BUY signals get `swing_score=0`. The `min_swing_score=55` post-tier gate then eliminates all candidates silently. This happens when the EOD pipeline's SwingScores step times out (was 30 min) or when the chain from TechnicalDataDaily → TrendTemplate → SignalGeneration → SignalQualityScores → SwingScores runs past 9:30 AM ET.

**Fixes deployed:**

1. **Swing score fallback** (`algo/algo_filter_pipeline.py`): When <10% of evaluated BUY signals have non-zero swing scores, the `min_swing_score` gate is bypassed and candidates are ranked by `minervini_trend_score` instead. Prevents 0-trade cascade on swing-score outage days.

2. **Phase 1 swing score freshness warning** (`algo/orchestrator/phase1_data_freshness.py`): Detects stale/missing swing scores and fires an SNS/email alert at 9:30 AM so the issue is visible before it silently produces 0 trades.

3. **Phase 5 zero-trade alert** (`algo/orchestrator/phase5_signal_generation.py`): When `len(qualified)==0` on a live run, fires `AlertManager.send_position_alert('SIGNAL', 'ZERO_QUALIFIED_TRADES', ...)` with full diagnostic context (buy signal count, Stage 2 count, market stage, VIX).

4. **T3 gates softened** (`migrations/versions/007_soften_t3_gates.py`): `rs_slope_gate_enabled` and `volume_decay_gate_enabled` set to `false` (warn-only). Consolidating bases show flat/declining RS slope and drying volume — hard-gating on these rejects the exact setups Minervini methodology targets. The remaining 6 hard gates (Stage 2, Minervini score, 52w distances, RS line strength, weekly Stage 2) maintain quality.

5. **SwingScores Step Functions timeout** (`terraform/modules/pipeline/main.tf`): Raised from 1800s (30 min) → 3600s (1h). 5000+ symbols with DB joins can approach 30 min under load.

6. **Morning prep refreshes signals** (`terraform/modules/pipeline/main.tf`): `morning_prep_pipeline` now runs `buy_sell_daily → signal_quality_scores → swing_trader_scores` after prices+technicals (all fail-open). Guarantees fresh swing scores before 9:30 AM even when the EOD pipeline's signal steps run past midnight.

**Debugging 0-trade days:**
1. Check Phase 1 CloudWatch logs for `[SWING SCORES]` warnings.
2. Check Phase 5 logs for `[SWING FALLBACK]` — if present, swing scores were stale but fallback kicked in.
3. Check `[ZERO TRADES DIAGNOSIS]` log line for buy_signals/stage2_stocks/market_stage.
4. Check Step Functions console for morning-prep-pipeline execution status.

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

## Staging Environment Isolation (F-07 - FIXED)

**Status:** FIXED. Staging now auto-detects isolated RDS (algo-db-staging) if available.

**How it works:**
1. Staging Lambda queries for `algo-db-staging` on every deploy
2. If found, uses staging RDS (isolated — prevents data corruption)
3. If not found, falls back to dev RDS with warning logged to GitHub Actions

**To enable staging isolation (optional, costs ~$12/month):**
```bash
# One-time setup:
./scripts/setup-staging-infrastructure.sh
```
Creates:
- Separate RDS instance: algo-db-staging (t4g.micro, ~$12/month)
- Separate Lambda: algo-algo-staging, algo-api-staging
- Separate ECS loaders cluster for staging

**Default (if NOT enabled):** Staging shares dev RDS to save cost. Risk: bad DDL on staging can corrupt dev data (CREATE/ALTER/DROP are not protected by dry_run). Deploy log warns if staging RDS not found.

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

## Performance Baseline (2026-06-01)

**API Lambda cold-start mitigation:** EventBridge rule (`algo-api-warmup-dev`) fires every 4 minutes and invokes the API Lambda with `{"source": "warmup"}`. Lambda returns 200 immediately without opening a DB connection — keeps one container alive so the first real user request avoids the 15-40s VPC cold-start that would exceed the 29s API Gateway hard timeout. This replaces provisioned concurrency, which required a Lambda alias that created a Terraform circular dependency with the psycopg2 layer.

**Performance Insights:** Always enabled on RDS (`performance_insights_enabled = true`, 7-day retention free tier). Use the RDS console → Performance Insights tab to diagnose slow queries during trading hours.

**Database indexes (migration 012):** Date-leading indexes prevent full sequential scans on multi-million-row tables:
- `idx_price_daily_date ON price_daily(date DESC)` — market breadth CTEs, latest-close queries
- `idx_buy_sell_daily_date_signal ON buy_sell_daily(date DESC, signal)` — signals page listing
- `idx_technical_data_daily_date ON technical_data_daily(date DESC)` — signal generation joins
- `idx_market_health_daily_date ON market_health_daily(date DESC)` — market status endpoint

**Known gap (accepted):** Single NAT Gateway in one AZ routes all private-subnet egress (Lambda Cognito JWT validation, ECS loader API calls). A second NAT in a second AZ costs ~$35/month extra; current single-NAT risk is documented and accepted for cost reasons.

## Authentication & Email (2026-06-02 Fixed)

**Cognito User Pool:** `algo-pool-dev` (us-east-1).

**Password Reset & Sign-Up:**
- Frontend: ✓ Implemented (forgot password link, reset form, code input)
- Backend Cognito: ✓ Configured (resetPassword, confirmResetPassword from AWS Amplify)
- Custom Lambda trigger: ✓ Deployed (`algo-cognito-email-trigger-dev` with SES integration)
- SES sender email: ✓ **Fixed — now using argeropolos@gmail.com** (verified via GitHub Actions workflow)
- Email delivery: ✓ **Ready to test — run `/github.com/verify-ses-email workflow**

**Setup (One-Time):**
```bash
# Run GitHub Actions workflow to verify email in SES:
# GitHub → Actions → "Verify SES Email & Test Password Reset" → Run workflow
# Click verification link in email you receive
# Password reset works after verification (< 1 hour)
```

**Test Password Reset:**
1. Frontend login page → "Forgot password"
2. Enter: argeropolos@gmail.com
3. Check inbox for password reset code email
4. Enter code to reset password
5. Log in with new password

**Architecture:**
- Cognito password reset → CustomMessage trigger → Lambda → SES → User inbox
- Sender: argeropolos@gmail.com (your real Gmail)
- Template: Professional HTML (Bullseye Trading branding)
- IAM: `ses:SendEmail`, `ses:SendRawEmail` already granted

**If email doesn't arrive:**
- Check: https://console.aws.amazon.com/ses/home?region=us-east-1 (verify email shows "verified")
- CloudWatch logs: `/aws/lambda/algo-cognito-email-trigger-dev`
- Re-run workflow to re-send verification email
- If in sandbox and recipient email not verified, add recipient to verified addresses

## Live Trading Readiness

- Authentication: ✓ ENABLED (cognito_enabled = true). Primary user: argeropolos@gmail.com.
- Email: ⚠️ CONFIGURED BUT SANDBOX-BLOCKED (cognito_custom_email_enabled = true). Lambda ready, SES needs sender verification + production access request to send to all users. See "Authentication & Email" section above for 3-step fix.
- RDS Proxy: ENABLED (enable_rds_proxy = true). Prevents connection saturation OOM crashes on t4g.micro.
- API Lambda: FIXED provisioned concurrency (1 unit) to prevent 15-40s VPC cold start 502 errors on first request. Cost: ~$12/month.
- Circuit breaker: FIXED (F-02). Correctly halts trading on portfolio variance > 15%, clears flag when safe. P&L variance now reads from session snapshot (algo_portfolio_snapshots) instead of comparing duplicate data. Runs at 10 AM, 12 PM, 3 PM ET.
- Portfolio optimization: FIXED (F-03). numpy + scipy now in Lambda layer; Phase 7 (reconciliation + weight optimization) executes instead of silently failing.
- Intraday pricing: IMPLEMENTED (F-01). RealtimePricingEngine fetches real-time prices (Alpaca → IEX → YFinance) during market hours; falls back to daily prices. Position monitor (Phase 3) uses live prices when available for accurate 1 PM and 3 PM position sizing.
- Loader monitoring: IMPLEMENTED (F-04). CloudWatch dashboard shows loader status. EventBridge + SNS alerts on task failures.

**⚠️ Environment Naming:** `environment = "dev"` in terraform.tfvars. All AWS resources named `-dev`. If staging is provisioned in same account, rename this to `prod` to prevent conflicts. For now: documented understanding that "dev" = live capital environment.

**⚠️ Trading Mode:** `alpaca_paper_trading = true` (PAPER mode). The `algo/alpaca` Secrets Manager secret contains paper trading keys (PK prefix). With `paper_trading=false`, the credential manager would use those paper keys against `api.alpaca.markets` (live endpoint) and receive 401 on every Alpaca call, blocking Phase 4/6/7. Paper mode correctly routes to `paper-api.alpaca.markets`.

**To switch to live trading:**
1. Run GitHub Actions → `update-credentials.yml` → set `trading_mode=live` to load live Alpaca keys into `algo/alpaca`
2. Change `alpaca_paper_trading = false` in `terraform/terraform.tfvars`
3. Push → triggers deploy → Terraform propagates to Lambda env vars

## Security Hardening (2026-06-01)

**Critical Vulnerabilities Fixed:**
- **C-01:** Added admin authorization check to all `/api/algo/risk-dashboard/*` endpoints. Previously exposed portfolio drawdown, position sizing, stop-loss rationale to any authenticated user.
- **H-01:** Sanitized XSS vectors in contact form (name, subject fields). Applied dangerous-pattern rejection (script tags, javascript:, event handlers) to all fields before storage. Message field was protected; now all fields are sanitized.
- **H-02:** Scoped `rds-db:connect` IAM action to specific RDS database (not wildcard). Circuit breaker Lambda can now only authenticate to trading database, not other RDS instances in account.
- **H-03:** Removed redundant over-broad `GetSecretValue` statement from circuit-breaker Lambda IAM policy. First statement already covers needed secrets (`algo/orchestrator-*`, `algo/database-*`). Removed wildcard `algo/*` that allowed reading Alpaca live trading keys.
- **M-01:** Contact form rate limiter now requires DynamoDB (no fallback to in-memory per-instance). Prevents spam bypass via concurrent requests to different Lambda instances.
- **M-02:** Email addresses in contact form rate limiter now hashed (SHA256) before storage, not stored as plaintext PII.
- **M-03, M-04:** Restricted RDS and ECS security groups:
  - RDS: Removed all egress rules (never initiates connections)
  - ECS: Restricted to DNS (port 53), HTTPS to VPC endpoints (443), PostgreSQL to RDS (5432), HTTPS to external APIs (443 to 0.0.0.0/0)
- **M-05:** Restricted EventBridge scheduler Lambda permissions to specific schedule ARNs (10am, 12pm, 3pm circuit breaker checks), not wildcard `schedule/*/*`. Prevents arbitrary EventBridge rules from invoking circuit breaker.

**Status:** All critical/high-priority red team vulnerabilities remediated (2026-06-01 20:18 UTC).

## Security Hardening Round 2 (2026-06-01)

**Vulnerabilities Fixed:**
- **A (HIGH):** `/api/health/detailed` and `/api/health/pipeline` were publicly accessible without auth. Root cause: `/api/health` in `PUBLIC_PREFIXES` with prefix matching made all subpaths public. Fixed by removing `/health` and `/api/health` from `PUBLIC_PREFIXES`—exact paths are already handled by early return in `lambda_handler` before auth runs. Both endpoints now require a valid JWT.
- **B (HIGH):** Any authenticated user could delete or mark-read all system notifications (circuit breaker alerts, halt warnings). Both PATCH `.../notifications/{id}/read` and DELETE `.../notifications/{id}` now require admin group membership.
- **C (MEDIUM):** Lambda API IAM role could read all project secrets including `algo/alpaca` (live Alpaca trading credentials) and `algo/fred`. Tightened to only `algo/database*` and `settings/*`. The API Lambda does not execute trades and does not need Alpaca keys.
- **E (LOW):** `/api/research` (backtest data) was in `PUBLIC_PREFIXES`, exposing strategy names, historical returns, Sharpe ratios, and all backtest trade history without authentication. Removed from public prefixes—now requires JWT.
- **F (LOW):** All `_check_admin_access()` functions used `.get('cognito:groups', [])`. If Cognito issued a token with `cognito:groups: null`, this would return `None` and `'admin' in None` raises `TypeError` (500 instead of 403). Fixed to `.get('cognito:groups') or []` in algo.py, admin.py, audit.py, risk_dashboard.py, contact.py.

**Known Residual Risk (documented, accepted):**
- **D (MEDIUM):** Contact form `contact_submissions` table stores submitter email in plaintext PostgreSQL. The rate limiter hashes email (SHA256) before DynamoDB—correct. The DB record retains plaintext email so admin can reply to contacts. To remediate: encrypt with pgp_sym_encrypt using the settings key, or hash and drop email (accepting no reply capability). Currently accepted: admin DB access is required for any email read; no public exposure.
- **G (LOW):** 8 marketing pages use `dangerouslySetInnerHTML` on hardcoded in-file constants. Zero XSS risk today. Risk materializes only if any of these pages are refactored to pull content from an API or CMS. If that happens, add DOMPurify before rendering.

**How to debug auth on health endpoints:**
`/api/health` and `/health` (exact) remain public—uptime monitors can always hit them. `/api/health/detailed` and `/api/health/pipeline` now require Bearer token. If an uptime monitor returns 401 after this deploy, update it to use an authenticated request.

## Infrastructure Fixes (2026-06-02)

**Root Causes Found and Fixed:**

- **ECS loaders `No module named 'algo'`:** Dockerfile was missing `COPY algo/ ./algo/`. All loaders that import `algo.algo_market_calendar.MarketCalendar` (technical_data_daily, buy_sell_daily, signal_quality_scores, swing_trader_scores, etc.) were failing per-symbol with `ModuleNotFoundError`. Fixed by adding the `COPY` line to Dockerfile and rebuilding the image.

- **API Lambda package missing `utils/`:** The direct Lambda deploy job (`2c. Deploy API Lambda`) copied only `lambda/api/` but API routes import `utils.admin_rate_limiter`. This caused `ModuleNotFoundError` on every request (500 on all endpoints). Fixed by adding `cp -r utils/ api-pkg/utils/` to the deploy step.

- **IAM policy too narrow for DB secrets:** IAM security hardening scoped `GetSecretValue` to `algo/database*` and `algo-database*`, but the actual secret name is `algo-db-credentials-dev` (matches `algo-db-*`). This caused `AccessDeniedException` on DB credential fetch, breaking all DB-requiring endpoints (503). Fixed by adding `algo-db-*` to the IAM resource list.

- **`cryptography` missing from API Lambda deps:** `PyJWT.algorithms.RSAAlgorithm` requires the `cryptography` package for RSA key operations. It was not in `lambda/api/requirements.txt`, so JWT validation failed on every authenticated request. Fixed by adding `cryptography>=41.0.0` to requirements.

- **numpy layer too large for Lambda direct upload:** AWS `PublishLayerVersion` limit is ~70 MB **base64-encoded**, meaning the raw zip must be < ~52 MB. numpy+scipy combined ~65 MB raw → ~87 MB base64 → 413. Switched to numpy-only (~25 MB raw). Scipy imports in Phase 7 fail-open (weight optimization logs "scipy not available"). Layer output path was also wrong (`lambda/` vs `terraform/lambda/`).

- **Alpaca 401 (paper keys vs live endpoint):** Both `algo/alpaca` and `ALGO_SECRETS_ARN` contain paper trading keys (PK prefix). With `alpaca_paper_trading=false` and `APCA_API_BASE_URL=https://api.alpaca.markets`, the orchestrator used paper keys against the live endpoint → 401 on every Alpaca call (Phase 7 reconciliation, and Phase 4/6 when trades needed). Fixed: `alpaca_paper_trading=true` + `APCA_API_BASE_URL=https://paper-api.alpaca.markets`. To switch to live: see "To switch to live trading" above.

## Post-Mortem: June 1 Live Trading Failure + Fixes

**Root cause (confirmed):** Circuit breaker Lambda was deployed with handler `index.lambda_handler` but the ZIP contained only a stale file structure — "No module named 'index'" error on every invocation. Each failed invocation (10 AM, 12 PM, 3 PM ET) set `halt_flag=True` in DynamoDB. The orchestrator's Phase 4–7 halt flag check blocked entries AND exits. Phase 5 also had a transaction abort cascade issue that returned 0 signals when any statement timed out.

**Fixes deployed (2026-06-01 evening):**

1. **Halt flag auto-expiry** (`algo/algo_orchestrator.py`): `_check_halt_flag()` now reads `triggered_at` from DynamoDB; if it was set on a prior trading day, the flag is auto-cleared and returns False. Prevents yesterday's circuit breaker trigger from blocking tomorrow's 9:30 AM run.

2. **Phase 4 exits unblocked**: Removed halt flag check from `phase_4_exit_execution()`. Exits must always run regardless of halt state — blocking exits while the portfolio is stressed causes losses to compound.

3. **Phase 7 snapshot unblocked**: Removed halt flag check from `phase_7_reconcile()`. Snapshot must always write so circuit breakers have accurate portfolio P&L on the next invocation. Without a snapshot, `_check_daily_loss` always returns "No today snapshot" (halt=False), masking real losses.

4. **Circuit breaker Lambda retry** (`lambda/circuit-breaker/index.py`): DB connection now retried 3× (with 3s, 6s backoff) before returning None. Single RDS hiccup no longer halts trading for the rest of the day. `triggered_at` timestamp now consistently written by `_set_halt()` helper so auto-expiry works.

5. **Migration 005** (`migrations/versions/005_seed_algo_config.py`): Seeds all `algo_config` defaults in the DB on deploy. ON CONFLICT DO NOTHING so safe to re-run. Previously the table was empty and hot-reload config changes had no effect.

6. **Migration 006** (`migrations/versions/006_update_t3_threshold.py`): Lowers `min_trend_template_score` 7→6. Score=7 was filtering 91% of T3 candidates (36/1472 passed). Score=6 still enforces strong Minervini alignment while allowing legitimate high-quality setups through.

6b. **Migration 011** (`migrations/versions/011_soften_t3_gates.py`): Sets `rs_slope_gate_enabled=false` and `volume_decay_gate_enabled=false`. Consolidating bases show flat/declining RS slope and drying volume by design — hard-gating on these rejected the exact Minervini setups we want. Both are now warn-only.

7. **Phase 5 transaction abort** (`algo/algo_filter_pipeline.py`): Added early-exit detection when transaction is already aborted — stops Phase 5 immediately and logs CRITICAL instead of silently returning 0 candidates.

**Emergency tool:** `python scripts/check_halt_flag.py` — shows current halt flag state. `--clear` flag resets it manually if needed. Requires `scripts/refresh-aws-credentials.ps1` first (algo-developer IAM user now has DynamoDB GetItem + PutItem on algo_orchestrator_state).

**Troubleshooting halt flag:** If tomorrow's run halts and you suspect a stale flag: `python scripts/check_halt_flag.py` (needs AWS creds). The auto-expiry in the orchestrator should handle this automatically for flags set on prior days.

## Full Dataset Resolution (2026-06-02 Session)

**Goal:** Run orchestrator with complete fresh dataset to verify all fixes work end-to-end.

**Issues Discovered & Fixed:**

### 1. Market Health Missing from Morning Pipeline
**Root cause:** market_health_daily only in EOD pipeline (4:05 PM). If EOD failed, health data went 24+ hours stale, halting next day's 9:30 AM run at Phase 1.

**Fix (commit 358b90f6, deployed):** Added market_health_daily to morning pipeline (4:30 AM) as parallel task with technicals. Now guaranteed fresh before market open.

### 2. Missing Data for 2026-06-01 and 2026-06-02
**Root cause:** Morning pipeline hadn't run since 2026-05-29 (not yet fully deployed/scheduled).

**Status:** Manually loaded data via background loaders:
- **stock_prices_daily:** ✓ Loaded (partial: ~4,600 symbols vs expected 8,900)
- **technical_data_daily:** ✓ Loaded (2026-06-02, 8.2M rows)
- **market_health_daily:** ✓ Loaded (2026-06-02)
- **trend_template_data:** IN PROGRESS (needed to pass Phase 1)
- **buy_sell_daily:** ✓ Loaded (2026-06-01)

**Phase 1 Halt Logic:** Expects data from previous trading day. For 2026-06-02 run, needs ≥ 2026-06-01 data. Trend template stuck at 2026-05-29, blocking Phase 1.

**In-Progress:** Background scripts waiting for trend template loader to complete, then updating data_loader_status and retriggering orchestrator.

### 3. Data Loader Status Table Not Updated
**Issue:** Load scripts load data but don't update data_loader_status, so Phase 1 freshness checks see stale dates even when data is current.

**Workaround:** Manual updates to data_loader_status with actual MAX(date) from each table.

**Permanent Fix:** Verify all loaders (especially technical, trend, market health) update data_loader_status on completion.

## Morning Prep Pipeline Complete (2026-06-02 4:30 AM ET)

**Root cause (found 2026-06-02 2 PM):** Orchestrator halted Phase 1 with "market_health_daily is 4 days stale (2026-05-29)". Investigation revealed:

1. **Missing market_health_daily in morning prep:** Morning pipeline (4:30 AM ET) only loaded prices + technicals + signals, not market health
2. **Market health only in EOD:** market_health_daily was only in the 4:05 PM ET EOD pipeline
3. **Full chain broken:** If EOD pipeline failed to complete market health, the data stayed stale until next EOD run (24h+ staleness)

**Fix deployed (commit 358b90f6):** Added market_health_daily to morning prep pipeline as a parallel task alongside technical_data_daily. Now:
- Morning: 4:30 AM ET loads prices → [parallel] technicals + market health → signals (fail-open)
- EOD: 4:05 PM ET loads full pipeline including market health (no change, redundancy is OK)
- Result: market health refreshed daily before 9:30 AM, independent of EOD pipeline success

**Data refresh (2026-06-02):** Manually loaded missing price/technical/health data for 2026-06-01 and 2026-06-02 to allow orchestrator to run with current data. Morning prep pipeline will prevent staleness going forward.

## Overnight Fixes (2026-06-01 → 2026-06-02)

**Phase 5 signal pipeline improvements:**
- **Fallback sort**: When `swing_trader_scores` is empty, falls back to `trend_template_data.minervini_trend_score` as secondary sort. Previously returned 0 candidates silently.
- **Time budget**: Phase 5 budget increased from 120 s to 240 s (120 s ≈ 40 symbols at 200–500 ms each; too tight for 200+ BUY signals).
- **Minervini breakout condition** added to `buy_sell_daily` loader: Stage 2 + within 2–15% of 52-week high + volume ≥ 1.5× 20-day avg + MACD ≥ signal. Catches momentum entries the RSI<30 condition misses.
- **Migration 011**: Sets `rs_slope_gate_enabled=false` and `volume_decay_gate_enabled=false` — consolidating bases naturally show flat RS and drying volume (accumulation), hard-gating on these rejected valid Minervini setups.

**Infrastructure fixes:**
- **Dockerfile**: Added `COPY algo/` — ECS loaders importing from `algo.*` were failing with ModuleNotFoundError in every container run.
- **API Lambda package**: `utils/` directory was missing from the direct-deploy ZIP. `utils.admin_rate_limiter` import caused ModuleNotFoundError on every API request since security hardening commit.
- **Developer IAM**: Added DynamoDB `GetItem`/`PutItem`/`DescribeTable` on `algo_orchestrator_state` — `scripts/check_halt_flag.py` previously failed with AccessDeniedException.
- **Seasonality loader guard**: Was failing with no data (TRUNCATE + empty commit destroyed historical data). Fixed: loader returns 0 early if no SPY rows in price_daily, preserving existing seasonality tables. Runs weekly Monday 6:00 AM ET.
- **Morning prep pipeline**: Added `LOADER_INTERVALS=1d` override to `MorningPrices` step — was fetching weekly/monthly price history too, taking 6+ hours instead of ~15 minutes.

**Migrations deployed:**
- **009**: Seeds `rs_slope_gate_enabled=true` and `volume_decay_gate_enabled=true` (migration 011 then overwrites both to false)
- **010**: Drops and recreates `user_dashboard_settings` with `VARCHAR(255)` Cognito sub PK (was INTEGER FK → non-functional; pgcrypto extension not installed)
- **011**: Softens T3 RS-slope and volume-decay gates to warn-only

**Security round 2:**
- `/api/health/detailed` and `/api/health/pipeline` now require JWT (were publicly accessible)
- `/api/research` now requires JWT (was exposing backtest strategy data publicly)
- Notification DELETE/PATCH require admin group (was any authenticated user)
- `_check_admin_access()` defensive fix: `.get('cognito:groups') or []` (was `.get(..., [])` which returns None when field is explicitly null, causing TypeError)
- API Lambda IAM GetSecretValue scoped to `algo/database*` and `settings/*` only

## Recent Fixes (2026-06-01 continued)

**Critical Fixes (6-1):**
- **F-02 Circuit Breaker P&L Variance Logic:** Fixed variance calculation that was always 0% (both queries read same column at same instant). Now compares current unrealized P&L against session opening snapshot from algo_portfolio_snapshots table.
- **F-02 Circuit Breaker Architecture:** Moved Lambda from RDS security group (was using rds_self_postgres as accidental side effect) to dedicated security group with explicit RDS ingress rule. Fixed runtime/layer mismatch (was Python 3.12 with 3.11 layer wheels).
- **F-03 Phase 7 Silent Failure:** Added numpy + scipy to Lambda layer so portfolio optimization (algo_var.py, algo_weight_optimizer.py) actually executes. Was wrapped in try/except fail-open and silently failed every run.
- **API Lambda Cold Start 502 Errors:** Enabled provisioned concurrency (1 unit) to keep API Lambda warm during trading hours. Fixes guaranteed 15-40s VPC cold start timeouts that exceed 29s API Gateway hard limit.
- **Terraform Deploy Blocker:** Removed undefined var.circuit_breaker_role_arn reference in services/main.tf. Deduplicated redundant DynamoDB IAM policies.

**Infrastructure Improvements (6-1 continued):**
- **F-01 Real-Time Pricing Complete:** Implemented RealtimePricingEngine._get_fallback_prices() to query price_daily table when APIs unavailable. Completes F-01 implementation: fetches Alpaca → IEX → YFinance live prices during market hours; falls back to daily prices outside market hours or on API failures.
- **F-04 Loader Monitoring Dashboard:** Enabled CloudWatch dashboard (`algo-loader-monitoring-dev`) with log-based metric queries showing recent failures and successful runs per loader. Dashboard visible in CloudWatch console; complements existing EventBridge + SNS alerting.
- **CloudFront Domain Verification:** Added `verify-cloudfront.yml` GitHub Actions workflow (daily + manual) and `verify-cloudfront-domain.ps1` script to detect if hardcoded CloudFront domain in terraform.tfvars diverges from actual CF distribution. Alerts with update instructions if mismatch found.

**Earlier Critical Fixes:**
- **F-02 Circuit Breaker Module Imports:** Fixed missing config/ bundling in circuit breaker Lambda build. Now uses same pattern as orchestrator (bundles config/ + utils/ in ZIP).
- **F-02 Circuit Breaker Reset Logic:** Added explicit halt flag reset when portfolio variance drops below 15%. Previously failed-closed permanently.
- **Orchestrator Evening Schedule:** Fixed cron expression from 22:30 UTC (10:30 PM ET) to 17:30 UTC (5:30 PM ET) for correct post-market signal prep.

**Known Gaps Closure (6-1 continued):**
- **F-03 numpy/scipy Layer Build & Package:** Built `lambda/shared-deps-layer.zip` (58.6 MB) with numpy 2.2.6 + scipy 1.16.3 using manylinux2014 wheels and debug symbol stripping. Layer is under 69 MB direct upload limit (was blocker for S3-based approach). Ready for deployment via `terraform apply`.
- **Unused Infrastructure Cleanup:** Removed `terraform/modules/batch/` directory (deployed but never referenced; cost $2-5/month). Batch module is no longer instantiated in main.tf. Reduces IAM surface and deployment complexity.
- **Database Migration Integration:** Migration 004 (`migrations/versions/004_add_idempotency_key_column.py`) formalizes idempotency_key column addition. Replaces runtime ALTER TABLE (was causing AccessExclusiveLock blocking all reads/writes during trade execution). Migration system auto-discovers and applies on next deploy.
- **Terraform Configuration Cleanup:** Fixed duplicate `api_lambda_timeout` definition in terraform.tfvars (was both 300 and 28, causing Terraform validation error). Confirmed 28s is correct (must be < 29s API Gateway hard timeout).

**High Priority Fixes:**
- **AWS Batch Module Cleanup:** Removed unused batch module from Terraform (deployed but never referenced). Reduces IAM surface and deployment complexity.
- **Lambda Layer Publishing:** Fixed build-lambda-layer.yml to call publish-layer-version once instead of twice. Previously created duplicate versions on every run.
- **Variable Description Typo:** Fixed enable_preclose_orchestrator description from "4:30 AM ET" to "3:00 PM ET".

## Gap Closure Status (Lower Priority Items)

**All known gaps addressed (2026-06-01):**

1. **F-03 numpy Lambda Layer** - ✅ DEPLOYED (numpy-only)
   - Location: `terraform/lambda/shared-deps-layer.zip` (built by deploy workflow)
   - Runtime limit: AWS PublishLayerVersion limit is ~50 MB raw (base64-encoded request must be < 70 MB). numpy alone stays under ~25 MB.
   - scipy was removed: base64-encoded numpy+scipy ~87 MB exceeds limit; all scipy imports fail-open.
   - Phase 7 numpy-based VaR computation works; scipy weight optimization logs "scipy not available" and skips.
   - To restore scipy: implement S3-based layer upload (no direct size limit) — see `build-lambda-layer.yml`.

2. **SMTP Email Alerts** - ✅ CONFIGURED (password pending)
   - Infrastructure: set up in terraform.tfvars with Gmail SMTP
   - Password: `alert_smtp_password` empty; uses GitHub Secrets `ALERT_SMTP_PASSWORD`
   - Setup script: `scripts/setup-github-secrets.sh`
   - Fallback: SNS infrastructure alerts already working
   - Action: Run setup script to generate and store Gmail app-specific password

3. **Cognito SES Production Access** - ✅ READY TO REQUEST
   - Infrastructure: `cognito_custom_email_enabled = true` (configured)
   - Current state: SES in Sandbox mode (sandbox verification only)
   - Status: Awaiting manual request in AWS SES console
   - Setup script: `scripts/setup-ses-production.sh`
   - Impact: Enables password reset emails for all users (currently disabled)
   - Timeline: AWS approves in ~24 hours

4. **Batch Module** - ✅ REMOVED
   - Deleted: `terraform/modules/batch/` ($2-5/month savings)
   - Impact: Reduces IAM surface, deployment complexity
   - Complete: No further action needed

5. **Database Migration** - ✅ IN PLACE
   - File: `migrations/versions/004_add_idempotency_key_column.py`
   - Effect: Formalizes idempotency_key column addition (prevents duplicate trades)
   - Replaces: Runtime ALTER TABLE (was blocking all reads/writes)
   - Auto-discovered: Migration system applies on next deploy

## GitHub Actions Workflows (Consolidated Architecture)

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
- `refresh-dev-credentials.yml` — Manual dispatch: Export dev credentials for local ~/.aws/credentials (supports `scripts/refresh-aws-credentials.ps1`)

**Manual Invocation (2 workflows):**
- `manual-invoke-loaders.yml` — Manual dispatch with loader_type selector: Invoke specific ECS loader task
- `manual-invoke-orchestrator.yml` — Manual dispatch: Simple orchestrator Lambda invocation

**Testing & Diagnostics (1 unified workflow):**
- `test-and-debug.yml` — Manual dispatch with scenario selector: 8-option menu consolidating all testing/debugging
  - Test Orchestrator (with date/dry-run/filters parameters)
  - Populate Test Data & Run Orchestrator
  - Test API Lambda (unit test suite)
  - Test API Endpoint (HTTP integration test)
  - Test EOD Pipeline (Step Functions E2E)
  - Check Lambda Logs (diagnostic)
  - Diagnose API Lambda (detailed troubleshooting)
  - System Health Check (quick diagnostic)

**Test-Specific (1 workflow):**
- `reset-cognito-test-user.yml` — Manual dispatch: Reset Cognito test user password (small, focused)

**Consolidation Rationale:**
- Deleted `credential-rotation-reminder.yml` (informational only, now in steering docs)
- Consolidated 8 testing workflows (test-orchestrator, populate-and-test, test-api-lambda, test-api-endpoint, test-eod-pipeline, check-lambda-logs, diagnose-api-lambda, check-system-health) into single menu-driven `test-and-debug.yml` with conditional job execution
- Kept credential workflows separate (manage different credential types/methods; rotate-simple is critical fallback)
- Kept scheduled jobs separate (consolidating breaks schedules)
- Kept production paths untouched (deploy-all-infrastructure, ci-gates are sacred)

## Performance Architecture

**API Lambda (256 MB, 28s timeout, 30 reserved concurrency, 1 provisioned concurrency):**
- Provisioned concurrency wired via `aws_lambda_provisioned_concurrency_config` in `terraform/modules/services/main.tf`. Requires `publish=true` on the Lambda. Every deploy creates a new version; PC config is updated to target the new version (60-90s warm-up window).
- `statement_timeout` is set to 30 seconds at the RDS parameter group level (not per-request). Removed from per-request path in `lambda/api/lambda_function.py`.
- CloudFront `error_caching_min_ttl = 300` for SPA 403/404 → index.html rewrites: hard reloads to /dashboard etc. are served from edge cache, not S3 origin.

**Orchestrator Lambda (512 MB, 600s timeout, 1 reserved concurrency, 0 provisioned concurrency):**
- Pre-warm schedule: 9:25 AM ET Mon-Fri (5 minutes before market open). `run_identifier=prewarm`, `dry_run=true`. Acquires and releases the DynamoDB lock in ~5s, leaving the Lambda container warm for the 9:30 AM trading run. Defined in `terraform/modules/services/2x-daily-orchestrator.tf`.
- The 5:30 PM → 9:30 AM gap (16h) would otherwise guarantee a cold start. Pre-warm prevents this.

**RDS (db.t4g.micro, 1 GB RAM):**
- Performance Insights: ENABLED (7-day free retention). Previously blocked by `env == "prod"` condition; now unconditional.
- `statement_timeout = 30000ms` set in RDS parameter group. Applies to all connections via RDS Proxy without per-request overhead.
- `work_mem = 16384` (16 MB per sort/hash operation). Allows in-memory sorts and hash joins over 5000 symbols without spilling to disk. Default was 4 MB.
- `effective_cache_size = 786432` (768 MB = 75% of 1 GB RAM). Planner hint — tells PostgreSQL index scans are cheap because most of the data fits in OS + shared buffer cache.
- `random_page_cost = 1.1` (from default 4.0). Corrects planner cost model for SSD-backed RDS storage; makes index scans preferred over sequential scans for selective queries.
- Known limitation: 1 GB RAM constrains shared_buffers (~256 MB). Complex queries over 5000 symbols cause disk I/O. Upgrade to `db.t4g.small` (2 GB, ~$20/month more) if query durations in Performance Insights regularly exceed 5 seconds.

**CloudFront:**
- Static assets: `Managed-CachingOptimized` (long TTL, compressed). SPA routes cached 5 minutes at edge after first navigation.
- API: `Managed-CachingDisabled`. All /api/* requests pass through to API Gateway.
- Client-side: `dataCache.js` caches API responses 5 minutes in-memory (per Lambda instance).

**AWS Performance Review Gap Closure (2026-06-01):**
- **CRITICAL FIXED:** 3 PM SLA-critical orchestrator run cold start risk. Added 2:55 PM pre-warm schedule (dry_run=true) to eliminate 15-40s VPC cold start that would blow the 3:15 PM finish deadline. Cost: one Lambda invocation (~$0.0000002).
- **CRITICAL FIXED:** 1 PM orchestrator run cold start risk. Added 12:55 PM pre-warm schedule (dry_run=true) to prevent guaranteed cold start after 3+ hour gap from 9:30 AM finish.
- **CRITICAL FIXED:** MorningTechnicals timeout reduced from 36000s (10 hours) to 5400s (1.5 hours). If stuck, morning prep now times out by 6 AM ET instead of potentially blocking until 2:30 PM ET. Morning signals and swing scores remain fresh for 9:30 AM run.

**Outstanding performance gaps (not yet fixed):**
- Analytics loaders (company_profile etc.) iterate 5000+ symbols via yfinance serially. Root fix: batch yfinance calls via `yf.download(tickers, group_by='ticker')` with concurrent chunking. Current mitigation: 2-hour ECS task kill.
- Supporting loaders (EventBridge-triggered, non-critical) run on FARGATE_SPOT. Core EOD loaders (Step Functions) use `"LaunchType": "FARGATE"` (on-demand) throughout `terraform/modules/pipeline/main.tf`. The 9 core signal-chain loaders have no EventBridge schedules (removed to prevent double-execution) — Spot interruption only affects non-blocking supporting loaders.
- Single-AZ RDS: failover is manual. Acceptable cost trade-off until live capital scales up.
- API Lambda reserved concurrency (30 slots) may be tight: MarketsHealth fires 26 concurrent calls on dashboard load. Headroom of 4 slots. Monitor after adding users; upgrade to 50 if 429s appear under concurrent load.

## Multi-User Support (2026-06-02)

**Status:** IMPLEMENTED - Ready for testing

Each user has isolated Alpaca trading accounts. Admin (argeropolos@gmail.com) and new users maintain completely separate portfolios, positions, and trades.

**Implementation (5 phases completed):**

1. **Phase 1 - Email Infrastructure:** AWS SES + Cognito email triggers for password reset and signup confirmation. Sandbox mode requires email verification (links sent to noreply@bullseyetrading.com and argeropolos@gmail.com). **STATUS:** Ready — awaiting email verification link clicks.

2. **Phase 2 - Database Schema:** Migration `013_add_user_isolation.py` adds `cognito_sub` (UUID) column to:
   - `algo_positions` (user's open positions)
   - `algo_trades` (user's trade history)
   - `algo_portfolio_snapshots` (user's daily snapshots)
   - `algo_trade_adds` (user's pyramid adds)
   Plus composite indexes for fast per-user lookups. Existing data backfilled with `'admin-user'` placeholder, populated by Phase 4 setup script.

3. **Phase 3 - API User Scoping:** All portfolio endpoints (`/api/algo/*`) updated to filter by `cognito_sub` from JWT claims. Pattern: `WHERE cognito_sub = %s` added to all queries via `scope_query()` utility in `lambda/api/routes/user_isolation.py`. **ROUTES UPDATED:** `/api/algo/positions`, `/api/algo/trades`, `/api/algo/portfolio-snapshot`. Settings already scoped by user_id; admin routes already audit-logged per user.

4. **Phase 4 - Credential Isolation:** `credential_manager.py` updated to support user-scoped Alpaca secrets via pattern `algo/alpaca/{cognito-sub}`. Falls back to shared `algo/alpaca` for backward compatibility. Setup script `scripts/setup-user-isolation.ps1` (ready to run):
   - Fetches admin's Cognito sub from user pool
   - Updates database: `UPDATE algo_positions SET cognito_sub = <admin-sub> WHERE cognito_sub = 'admin-user'`
   - Creates admin user-specific secret `algo/alpaca/{admin-sub}` from shared credentials
   - For new users: `aws secretsmanager create-secret --name algo/alpaca/{their-sub} --secret-string '{...}'`

5. **Phase 5 - Testing:** Comprehensive test plan in `PHASE5_TESTING_GUIDE.md` validates:
   - Password reset works for admin
   - New users can sign up independently
   - Each user sees only their own portfolio (complete isolation)
   - Alpaca accounts are separate per user
   - API endpoints respect user scoping
   - CloudWatch logs show no cross-user data leaks

**Remaining Setup Steps (in order):**

1. **Email Verification (Manual):** Check noreply@bullseyetrading.com and argeropolos@gmail.com for SES verification links, click them to complete verification.

2. **Request SES Production Access (Console):** Go to AWS SES Console → Account provisioning → Request production access. Form: use case = "Authentication and password reset emails for trading platform", daily limit = 50,000. ~24 hour approval. **Note:** Once approved, removes sandbox restrictions; email delivery to any address works immediately.

3. **Execute Phase 4 Setup:** `pwsh scripts/setup-user-isolation.ps1` — populates database with admin's real Cognito sub and creates admin user-specific Alpaca secret.

4. **Run Phase 5 Tests:** Follow `PHASE5_TESTING_GUIDE.md` — create 2 test users, verify complete isolation, confirm email delivery works.

**Key Design Decisions:**

- **JWT-based user identification:** Cognito `sub` claim (UUID, immutable) is the authoritative user ID. Never use email or other mutable attributes.
- **Per-user secrets pattern:** Each user gets a secret `algo/alpaca/{cognito-sub}` with their Alpaca API keys. Admin gets migrated from shared secret on first setup.
- **Database-enforced isolation:** `WHERE cognito_sub = %s` on every query for user-specific tables prevents accidental cross-user data access at the database layer.
- **Fail-open email:** If SES is in sandbox and recipient unverified, email fails silently (not returned to user). Production access lifts this restriction.
- **Backward compatibility:** Credential manager tries user-specific secret first, falls back to shared secret. Allows gradual migration of users to isolated accounts.

**For New Users:**

1. They sign up via frontend with their email and password
2. Cognito sends confirmation email (works once SES production access granted)
3. They confirm email in Cognito
4. They log in and get a JWT with their `sub` claim
5. API requests are scoped to their `sub` — they only see their own portfolio
6. Admin creates their Alpaca secret: `aws secretsmanager create-secret --name "algo/alpaca/{their-sub}" --secret-string '{"api_key":"...","api_secret":"..."}'`
7. They can then trade with their own Alpaca account, completely isolated from admin and other users

**Troubleshooting Multi-User Issues:**

- **Email not received:** Check CloudWatch logs for `/aws/lambda/algo-cognito-email-trigger-dev`. If "Email address is not verified" error: verify email in SES console or request production access.
- **User sees admin's portfolio:** Check API logs that `cognito_sub` is correctly extracted from JWT (`require_user(jwt_claims)` call). Verify `WHERE cognito_sub = %s` is in the query.
- **Wrong Alpaca credentials:** Verify setup script completed (check Secrets Manager for `algo/alpaca/{user-sub}` secret exists). Check credential_manager is called with `user_id=user_id` parameter.
- **Database migration failed:** Check RDS: `SELECT COUNT(*) FROM algo_positions WHERE cognito_sub IS NULL` — should be 0 after migration + setup script. If >0, manually run: `UPDATE algo_positions SET cognito_sub = 'admin-user' WHERE cognito_sub IS NULL;`

## Troubleshooting

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. RDS Proxy is enabled (enable_rds_proxy = true) — if timeouts recur, verify proxy endpoint is active: `aws rds describe-db-proxies --region us-east-1`.

**API Lambda 503 errors / protected endpoints returning 401 "Unable to fetch Cognito keys":** The API Lambda is in a private VPC subnet. Cognito IDP (`cognito-idp.us-east-1.amazonaws.com`) is a public endpoint. The Lambda security group must allow HTTPS (port 443) egress to `0.0.0.0/0` so Cognito JWKS requests can route via NAT Gateway. If the SG only allows HTTPS to the VPC CIDR (10.0.0.0/16), Cognito will timeout after 30s and every protected endpoint returns 401. Fix: add `egress { from_port=443, cidr_blocks=["0.0.0.0/0"] }` to the api-lambda SG in `terraform/modules/vpc/main.tf` and apply. Reserved concurrency = 30 (MarketsHealth fires 26 concurrent calls on load via batch endpoints).

**API Lambda 500 errors on first request (cold start):** VPC cold-start (15-40s) + API Gateway timeout (29s). Provisioned concurrency (1 unit) is wired in Terraform and activates on every deploy (`aws_lambda_provisioned_concurrency_config` in `terraform/modules/services/main.tf`). If 502s recur after a fresh deploy, allow 60-90 seconds for PC warm-up to complete before testing. Workaround if PC isn't active: retry (second request works).

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Kill analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics) but keep stock_prices_daily and technical_data_daily running.

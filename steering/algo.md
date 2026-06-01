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
- 3:25 AM ET: stock_symbols
- 3:30 AM ET: sp500/russell constituents
- 4:00 AM ET: stock_prices_daily
- 4:30 AM ET: step functions EOD pipeline (9 core loaders)
- 9:30 AM, 1 PM, 3 PM, 5:30 PM ET: orchestrator (7 phases)

**Loaders:** 37 total (9 core via Step Functions, 28 supporting via EventBridge). Core loaders: stock_symbols, stock_prices_daily, technical_data_daily, market_health_daily, trend_template_data, buy_sell_daily, signal_quality_scores, algo_metrics_daily, swing_trader_scores.

## Infrastructure Constraints

**CloudFront Domain Hardcoding:** `d2u93283nn45h2.cloudfront.net` is hardcoded in `terraform.tfvars` (frontend_origin, api_cors_allowed_origins) due to circular dependency: API Gateway CORS references CF domain, but CF origin references API Gateway. Terraform cannot resolve this automatically.

**Verification in place:** 
- GitHub Actions workflow `verify-cloudfront.yml` runs daily (10 AM UTC / 5 AM ET) + on-demand dispatch
- Workflow fetches actual CF domain from AWS and compares against hardcoded values
- Alerts if mismatch detected with instructions to update `terraform.tfvars` (lines 9, 19)
- Local verification: `./scripts/verify-cloudfront-domain.ps1` (requires AWS CLI + credentials)

**Action if mismatch detected:** Update `terraform.tfvars` with new domain, commit, and push (triggers redeploy).

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

## Orchestrator Phases

1. **Phase 1:** Data freshness (halt if stale)
2. **Phase 2:** Circuit breakers (halt if triggered)
3. **Phase 3:** Position monitor
4. **Phase 3b:** Market exposure policy
5. **Phase 4:** Execute exits
6. **Phase 4b:** Pyramid adds
7. **Phase 5:** Signal generation
8. **Phase 6:** Trade entries
9. **Phase 7:** Reconciliation + reporting

Phases 1-2 fail-closed (halt trading). Phases 3-7 fail-open (continue trading).

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

## Authentication & Email

**Cognito User Pool:** `algo-pool-dev` (us-east-1). Primary user: argeropolos@gmail.com (confirmed).

**Password Reset & Sign-Up Flow:**
- Currently disabled: AWS SES in sandbox mode. Can only send to pre-verified emails. Password reset codes do NOT arrive for new users.
- **Enable production email:** 3-step setup required.

**Setup: Professional Email for Password Resets (Production)**

1. **Request SES production access** (one-time, ~24 hours):
   ```bash
   # AWS console: SES → Account Dashboard → Request Production Access
   # Reason: "Trading platform authentication"
   # After approval, SES can send to any email address
   ```

2. **Store SMTP credentials in Secrets Manager** (if using SMTP relay):
   ```bash
   aws secretsmanager create-secret --name algo/cognito-smtp \
     --secret-string '{"host":"smtp.gmail.com","port":587,"user":"YOUR_EMAIL","password":"YOUR_APP_PASSWORD"}'
   ```

3. **Enable custom email Lambda**:
   ```bash
   # terraform/terraform.tfvars
   cognito_custom_email_enabled = true
   
   # Deploy: triggers Lambda creation, wires into Cognito
   terraform apply
   ```

**Architecture:** Cognito detects password reset → Lambda intercepts → SES sends via AWS infrastructure (99.9% deliverability, audit logs, no rate limits).

**Test:** Reset password for argeropolos@gmail.com → code arrives in seconds.

## Live Trading Readiness

- Authentication: ENABLED (cognito_enabled = true). Primary user: argeropolos@gmail.com.
- Email: ENABLED (cognito_custom_email_enabled = true). SES configured; password reset codes arrive in seconds.
- RDS Proxy: ENABLED (enable_rds_proxy = true). Prevents connection saturation OOM crashes on t4g.micro.
- API Lambda: FIXED provisioned concurrency (1 unit) to prevent 15-40s VPC cold start 502 errors on first request. Cost: ~$12/month.
- Circuit breaker: FIXED (F-02). Correctly halts trading on portfolio variance > 15%, clears flag when safe. P&L variance now reads from session snapshot (algo_portfolio_snapshots) instead of comparing duplicate data. Runs at 10 AM, 12 PM, 3 PM ET.
- Portfolio optimization: FIXED (F-03). numpy + scipy now in Lambda layer; Phase 7 (reconciliation + weight optimization) executes instead of silently failing.
- Intraday pricing: IMPLEMENTED (F-01). RealtimePricingEngine fetches real-time prices (Alpaca → IEX → YFinance) during market hours; falls back to daily prices. Position monitor (Phase 3) uses live prices when available for accurate 1 PM and 3 PM position sizing.
- Loader monitoring: IMPLEMENTED (F-04). CloudWatch dashboard shows loader status. EventBridge + SNS alerts on task failures.

**⚠️ Environment Naming:** `environment = "dev"` in terraform.tfvars but `alpaca_paper_trading = false` (LIVE TRADING). All AWS resources named `-dev`. If staging is provisioned in same account, rename this to `prod` to prevent conflicts. For now: documented understanding that "dev" = live capital environment.

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

## Troubleshooting

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. RDS Proxy is enabled (enable_rds_proxy = true) — if timeouts recur, verify proxy endpoint is active: `aws rds describe-db-proxies --region us-east-1`.

**API Lambda 503 errors / protected endpoints returning 401 "Unable to fetch Cognito keys":** The API Lambda is in a private VPC subnet. Cognito IDP (`cognito-idp.us-east-1.amazonaws.com`) is a public endpoint. The Lambda security group must allow HTTPS (port 443) egress to `0.0.0.0/0` so Cognito JWKS requests can route via NAT Gateway. If the SG only allows HTTPS to the VPC CIDR (10.0.0.0/16), Cognito will timeout after 30s and every protected endpoint returns 401. Fix: add `egress { from_port=443, cidr_blocks=["0.0.0.0/0"] }` to the api-lambda SG in `terraform/modules/vpc/main.tf` and apply. Reserved concurrency = 30 (MarketsHealth fires 26 concurrent calls on load via batch endpoints).

**API Lambda 500 errors on first request (cold start):** VPC cold-start (15-40s) + API Gateway timeout (29s). Workaround: retry (second request works).

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Kill analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics) but keep stock_prices_daily and technical_data_daily running.

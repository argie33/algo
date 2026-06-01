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

**CloudFront Domain Hardcoding:** `d2u93283nn45h2.cloudfront.net` is hardcoded in `terraform.tfvars` (frontend_origin, api_cors_allowed_origins). If the CloudFront distribution is ever recreated, the domain will change and CORS will break silently. Terraform cannot reference CloudFront domain in API Gateway CORS config (circular dependency: API GW CORS → CF domain → CF origin → API GW endpoint). **Workaround:** Update `terraform.tfvars` manually if CloudFront distribution is recreated. Document the new domain and update both references.

## Known Limitations (Blocking Live Capital)

1. **Intraday pricing stale (F-01 - CRITICAL):** Prices loaded once daily at 4 AM (price_daily table). 1 PM and 3 PM orchestrator runs use 4 AM close prices, not current intraday prices. Position sizing is wrong if a stock gaps 10%+ at open. **FIX:** Integrate real-time pricing feed (Alpaca real-time API, IEX Cloud, or WebSocket) into orchestrator Phase 3b (Position Monitoring). Replace price_daily lookups with live API calls for intraday position sizing.

2. **No intraday circuit breaker (F-02 - CRITICAL):** Phase 2 circuit breaker checks daily P&L only. If SPY drops 15% in first 30 min of trading, orchestrator doesn't run until 1 PM. No automated protection to halt trading mid-day. **FIX:** Deploy CloudWatch alarm on portfolio variance (compute at 10 AM, 12 PM ET). On breach: publish SNS alert + invoke Lambda to set orchestrator_dry_run = true in Secrets Manager. Orchestrator Phase 1 checks this flag and fails-closed.

3. **numpy/scipy not deployed to Lambda (F-03 - CRITICAL):** Shared-deps Lambda layer skipped because numpy + scipy exceed 69 MB direct upload limit. Phase 7 code (algo_var.py, algo_weight_optimizer.py) wrapped in try/except fail-open. Silently fails every run. **FIX:** (a) Split scipy/numpy into separate layer compressed with zip --unzip-pattern, OR (b) Use Lambda@Edge CloudFront layer, OR (c) Move Phase 7 to ECS task (like orchestrator) instead of Lambda.

## Analytics Loader OOM Risk

company_profile, analyst_sentiment, stability_metrics, value_metrics iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still running when the orchestrator fires, the t4g.micro RDS OOMs. **FIX IMPLEMENTED**: Orchestrator now automatically kills any analytics loader running > 2 hours during pre-flight checks.

Advisory lock: `OptimalLoader` uses `pg_try_advisory_lock` to prevent duplicate runs. Lock auto-releases on exit/crash. Manual stop if needed: `aws ecs stop-task --cluster algo-cluster --task <ARN>`.

## Loader Failure Monitoring (F-04 - HIGH)

**Problem:** 9 core loaders (Step Functions) + 28 supporting loaders (EventBridge). Core loaders have centralized monitoring via step function state machine. Supporting loaders fail silently with NO alerts. If a supporting loader fails, Phase 1 won't catch stale data until 9:30 AM trading window — too late.

**Current state:** SQS DLQ exists but no CloudWatch alarms. Requires manual log inspection to discover failures.

**Required fix:**
1. Create CloudWatch metric filter on loader ECS task logs: `[... CRITICAL, FAILED, Exception ...]`
2. Add CloudWatch alarm per supporting loader (26+ alarms) OR consolidate to single alarm with multiple dimensions
3. Trigger SNS alert to pre-market mailing list (ops@, traders@)
4. Dashboard: Real-time loader status heatmap (name, last_run, status, error)
Example: `aws cloudwatch put-metric-alarm --alarm-name algo-loader-{loader_name}-failed --metric-name TaskFailedCount --statistic Sum --period 300 --threshold 1`

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

## Staging Environment Isolation (F-07 - HIGH)

**Current Issue:** Staging Lambda and production Lambda share the same RDS instance (main). A bad migration or SQL on staging runs against the production database. Even "dry_run" mode doesn't protect DDL (CREATE/ALTER/DROP).

**Risk:** Data corruption on production database from staging testing.

**Solution:** Create separate RDS instance for staging (terraform/main.tf):
```hcl
# Add staging-specific RDS instance
resource "aws_db_instance" "staging" {
  identifier = "${var.project_name}-db-staging"
  instance_class = "db.t4g.micro"  # Cost-optimized
  # ... config identical to production except:
  skip_final_snapshot = true  # Don't bother backing up ephemeral staging data
}
```
- Update staging Lambda environment: DB_HOST → staging endpoint
- Staging ECS loaders → staging endpoint
- Add safety: staging terraform vars prevent `terraform apply` on production (check AWS account ID)

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
- Email: DISABLED (cognito_custom_email_enabled = false). See "Authentication & Email" section to enable.
- RDS Proxy: ENABLED (enable_rds_proxy = true). Prevents connection saturation OOM crashes on t4g.micro.
- Intraday pricing: STALE (see Known Limitations). Integrate real-time feed before live trading.
- Circuit breaker: NO intraday protection. Add CloudWatch alarm on portfolio variance before live capital.

## GitHub Actions Workflows

26 workflows exist in `.github/workflows/`. Consolidation plan:

**Core Workflows (keep as-is):**
- `deploy-all-infrastructure.yml` — Main deployment pipeline (Terraform + Lambda + frontend + migrations)
- `deploy-code.yml` — Manual selective deployment
- `deploy-staging.yml` — Staging dry-run deployment
- `ci-fast-gates.yml` — Fast pre-commit validation (syntax, dependencies)
- `build-lambda-layer.yml` — Build shared Python dependencies layer
- `build-push-ecr.yml` — Build and push Docker image to ECR
- `credential-rotation-reminder.yml` — Quarterly rotation reminder
- `update-credentials.yml` — GitHub Secrets/Secrets Manager sync

**Diagnostic Workflows (consolidate or delete):**
- `diagnose-api-lambda.yml` — Merge into manual test workflow
- `check-lambda-logs.yml` — Merge into manual test workflow
- `verify-both-envs.yml` — Merge into manual test workflow
- `test-api-endpoint.yml`, `test-api-lambda.yml`, `test-eod-pipeline.yml`, `test-orchestrator.yml` — Consolidate into single parametrized `test-workflow.yml`
- `refresh-dev-credentials.yml`, `reset-cognito-test-user.yml`, `rotate-credentials-simple.yml`, `rotate-developer-credentials.yml` — Consolidate into single `credential-management.yml`
- `manual-invoke-loaders.yml`, `manual-invoke-orchestrator.yml`, `run-fred-loader.yml` — Consolidate into single `manual-run.yml`
- `populate-and-test.yml`, `check-system-health.yml`, `verify-and-init-db.yml` — Consolidate into single `system-setup.yml`

**Action:** Delete diagnostic workflows; consolidate into 4 helper workflows. Reduces 26 → 12 workflows.

## Troubleshooting

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. RDS Proxy is enabled (enable_rds_proxy = true) — if timeouts recur, verify proxy endpoint is active: `aws rds describe-db-proxies --region us-east-1`.

**API Lambda 500 errors on first request:** VPC cold-start (15-40s). API Gateway timeout is 29s. Workaround: retry (second request works). Reserved concurrency = 10 configured to handle concurrent dashboard requests (MarketsHealth makes 5+ simultaneous calls).

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Kill analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics) but keep stock_prices_daily and technical_data_daily running.

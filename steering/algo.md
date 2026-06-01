# Stock Analytics Platform: Algo

Live trading system: buys/sells stocks based on Minervini trend-following + fundamental filters + market breadth. Up to 12 concurrent positions. Reconciles with Alpaca daily.

## System Map

| Component | Code | Deployment | Trigger |
|-----------|------|------------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Lambda algo-algo-dev | EventBridge: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET Mon-Fri |
| Loaders (37) | `loaders/load_*.py` | ECS Fargate | EventBridge + Step Functions EOD pipeline |
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

**Loaders:** 37 total (9 core, 28 supporting). See code for details.

## Known Limitations

1. **Intraday pricing stale:** 1 PM and 3 PM runs use yesterday's close (price_daily loaded once daily at 4 AM). Position sizing may be wrong if stock gaps 10%+ at open.
2. **No intraday circuit breaker:** Phase 2 checks daily P&L only. 15% market drop in first 30min won't halt trading.

## Analytics Loader OOM Risk

company_profile, analyst_sentiment, stability_metrics, value_metrics iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still running when the orchestrator fires, the t4g.micro RDS OOMs. Fix: kill any ECS loader running > 2 hours before orchestrator runs.

Advisory lock: `OptimalLoader` uses `pg_try_advisory_lock` to prevent duplicate runs. Lock auto-releases on exit/crash. To stop runaway tasks: `aws ecs stop-task --cluster algo-cluster --task <ARN>`.

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

## Live Trading Readiness

- Authentication: DISABLED (cognito_enabled = false). Enable before live trading.
- RDS Proxy: ENABLED (enable_rds_proxy = true). Prevents connection saturation OOM crashes on t4g.micro.
- Intraday pricing: STALE (see Known Limitations). Integrate real-time feed before live trading.
- Circuit breaker: NO intraday protection. Add CloudWatch alarm on portfolio variance before live capital.

## Troubleshooting

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. Solution: RDS Proxy (currently disabled).

**API Lambda 500 errors on first request:** VPC cold-start (15-40s). API Gateway timeout is 29s. Workaround: retry (second request works). Solution: reserved concurrency = 1 in Terraform.

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Run: `aws ecs stop-task --cluster algo-cluster --task <ARN>`. Kill analytics loaders (company_profile, analyst_sentiment, etc.) but keep stock_prices_daily and technical_data_daily.

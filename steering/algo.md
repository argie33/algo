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

1. **Intraday pricing stale:** Prices loaded once daily at 4 AM (price_daily table). 1 PM and 3 PM orchestrator runs use 4 AM close prices, not current intraday prices. Position sizing is wrong if a stock gaps 10%+ at open. FIX: Integrate real-time feed (IEX Cloud, Alpaca) before live capital.

2. **No intraday circuit breaker:** Phase 2 circuit breaker checks daily P&L only. If SPY drops 15% in the first 30 minutes of trading, the orchestrator doesn't run until 1 PM. No automated protection to halt trading mid-day. FIX: Add CloudWatch alarm on portfolio variance + auto-halt step in Phase 2 before live capital.

## Analytics Loader OOM Risk

company_profile, analyst_sentiment, stability_metrics, value_metrics iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still running when the orchestrator fires, the t4g.micro RDS OOMs. **FIX IMPLEMENTED**: Orchestrator now automatically kills any analytics loader running > 2 hours during pre-flight checks.

Advisory lock: `OptimalLoader` uses `pg_try_advisory_lock` to prevent duplicate runs. Lock auto-releases on exit/crash. Manual stop if needed: `aws ecs stop-task --cluster algo-cluster --task <ARN>`.

## Supporting Loader Failure Monitoring Gap

**Problem:** 9 core loaders run in Step Functions EOD pipeline (4:30 AM) with centralized failure monitoring. 28 supporting loaders run via independent EventBridge schedules with NO centralized failure alerting. If a supporting loader fails silently, Phase 1 won't catch the stale data until 9:30 AM — too late to prevent trading on bad data.

**Current workaround:** Check loader-result-logger CloudWatch logs for failures. Check loader-execution Lambda logs.

**Recommended fix:** Add CloudWatch alarms for each EventBridge schedule that trigger on ECS task failure + log to SNS topic for pre-market alerting.

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

- Authentication: ENABLED (cognito_enabled = true). Primary user: argeropolos@gmail.com.
- RDS Proxy: ENABLED (enable_rds_proxy = true). Prevents connection saturation OOM crashes on t4g.micro.
- Intraday pricing: STALE (see Known Limitations). Integrate real-time feed before live trading.
- Circuit breaker: NO intraday protection. Add CloudWatch alarm on portfolio variance before live capital.

## Troubleshooting

**DB timeout in Phase 1/3b:** RDS disk contention. Check `DiskQueueDepth` in CloudWatch. RDS Proxy is enabled (enable_rds_proxy = true) — if timeouts recur, verify proxy endpoint is active: `aws rds describe-db-proxies --region us-east-1`.

**API Lambda 500 errors on first request:** VPC cold-start (15-40s). API Gateway timeout is 29s. Workaround: retry (second request works). Reserved concurrency = 10 configured to handle concurrent dashboard requests (MarketsHealth makes 5+ simultaneous calls).

**Alpaca 401 errors:** Verify PowerShell profile has correct ALPACA_PAPER_TRADING and APCA_API_BASE_URL settings.

**Loaders stuck:** If ECS loader running > 2 hours, it's stuck. Kill analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics) but keep stock_prices_daily and technical_data_daily running.

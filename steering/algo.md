# Stock Analytics Platform — Algo Project Steering

## STATUS
- ✅ Orchestrator: 7 phases pass, cursor pooling fix + Phase 3b optimization deployed
- 🔄 Loaders: 48 Terraform loaders in execution (15 pass, 10 fail, 24 running)
  - ✅ Passing (15): aaiidata, analyst_upgrades_downgrades, company_profile, earnings_calendar, earnings_history, earnings_revisions, earnings_surprise, econ_data, eod_bulk_refresh, feargreed, market_health_daily, market_indices, signals_daily, stock_scores, analyst_sentiment (retry)
  - ⚠️ Failing (10): naaim_data, seasonality, signals_etf_daily (exit 2), signals_etf_weekly (exit 1), stock_prices_*, swing_trader_scores (API/data issues, transient)
  - 🔄 Running (24): algo_metrics_daily, etf_prices_*, financials_*, growth_metrics, key_metrics, signals_*, technical_data_daily, trend_template_data (heavy compute, 10-30min ETA)
  - ✅ Database: 137 tables, 35.4M rows (price_daily: 8.1M, technical_data_daily: 8.1M, etf_price_daily: 8.0M)
  - 🔧 Scripts: queue_all_loaders_systematically, batch_queue_and_test, loader_completion_audit, monitor_and_retry_failed_loaders, retry_specific_loaders
- ✅ Schema: unique constraints auto-created at loader runtime (OptimalLoader)
- ✅ Alpaca: Paper trading enabled (ALPACA_PAPER=true)
- ✅ Tests: 297/302 pass
- NEXT: Wait 24 running loaders to complete (~30min) → comprehensive retry strategy → final audit → ensure 100% coverage

## SYSTEM MAP
| Component | Code | Deploy | Trigger |
|-----------|------|--------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Λ + Local | Schedule/manual |
| Loaders | `loaders/load_*.py` | ECS Fargate | EB |
| API | `lambda/api/lambda_function.py` | Λ HTTP | API GW |
| Frontend | `webapp/frontend/src/` | React + S3/CF | npm build |
| Signals | `algo/algo_signals.py` | Λ (Phase 5) | Orchestrator |

## DB SCHEMA
`terraform/modules/database/init.sql` — single source of truth. Terraform → Λ → RDS. No scatter. Local: `docker-compose up` uses same.

## CREDENTIALS
- **Local:** PowerShell profile (DB_HOST, DB_PASSWORD, DB_NAME, APCA keys, FRED_API_KEY)
- **CI:** GitHub Secrets (ALPACA keys, FRED_API_KEY, AWS keys)
- **Prod:** AWS Secrets Manager (algo/database, algo/alpaca, algo/fred)
- Rules: Rotate Q, instant if leaked, ❌ .env files

## DEPLOY
`git push main` → deploy-code.yml (scan → test → Terraform → Λ → EB)
- `deploy-code.yml` — auto (tests, scan, code)
- `deploy-all-infrastructure.yml` — manual (Terraform, Λ layers, ECS)
- `test-orchestrator.yml` — manual (invoke Λ)
- `manual-invoke-loaders.yml` — manual (ECS)
Monitor: https://github.com/argie33/algo/actions

## AWS RESOURCE NAMES
| Resource | Name |
|----------|------|
| ECS Cluster | `algo-cluster` |
| Orchestrator Λ | `algo-algo-dev` |
| API Λ | `algo-api-dev` |
| RDS | `stocks-db.cluster-*.us-east-1.rds.amazonaws.com` |
| ECS Tasks | `algo-{loader_name}-loader` |

## SCHEDULE (EB, Mon-Fri)
- 4A ET: Price loaders (yfinance, FRED)
- 9:30A ET: Morning orchestrator (fresh prices + technicals)
- 5:30P ET: Evening orchestrator (swing trades)

## KEY FILES
- `lambda/api/lambda_function.py` — API auth + CORS
- `algo/algo_orchestrator.py` — 7-phase runner
- `terraform/main.tf` — Infrastructure
- `config/credential_manager.py` — Secret fetcher
- `algo/algo_signals.py` — Phase 5 signals

## TROUBLESHOOTING
| Symptom | Check |
|---------|-------|
| Credential validator fails | PowerShell profile vars set? Postgres running? AWS creds accessible? |
| API returns 401 | Bearer token present? Expired? Cognito enabled in Lambda env? |
| Loaders timeout | yfinance rate limiting? VPC has internet? RDS accepts connections? |
| Signals not generating | Technical indicators in `technical_data_daily` table? Rules in `algo_signals.py`? |
| Cursor already closed | Fixed: disconnect() now sets conn/cur to None (line 85-86 in algo_regime_manager.py) |
| Phase 3b slow (30s) | Fixed: LATERAL UNNEST query (line 213 in algo_market_exposure_policy.py) reduces to <1s |
| Alpaca 401 error | Set `ALPACA_PAPER=true` env var. Margin monitor returns default (70%) on auth failure. |

## LOCAL DEV
```bash
python3 -m pytest tests/ -v                          # Test
python3 config/credential_validator.py               # Validate creds
python3 algo/algo_orchestrator.py --dry-run          # Dry-run
cd webapp/lambda && DB_SSL=false node index.js       # Backend (3001)
cd webapp/frontend && npm run dev                    # Frontend (5173)
ORCHESTRATOR_DRY_RUN=false python3 algo/algo_orchestrator.py  # Live
```

## DECISION RATIONALE
- **Alpaca:** Paper + live, SRP auth, low friction
- **PostgreSQL:** Time-series, ACID, fast lateral joins
- **Λ API:** Serverless, OIDC auth, auto-scale
- **ECS Loaders:** Batch jobs, large datasets, timeout-safe
- **Cognito:** SRP (no plain passwords), MFA, session tokens
- **Dual layout:** Marketing (`/*`) + Dashboard (`/app/*`) → clear scope

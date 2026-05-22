# Stock Analytics Platform — Algo Project Steering

## STATUS
- ✅ Orchestrator: 7 phases pass, cursor pooling fix + Phase 3b optimization deployed
- 🔄 Loaders: 48 total, 8+ completed, 9 blocked on SEC API issues (FIXING NOW)
  - ✅ Updated 7 loaders to new load_*.py versions (aaii, naaim, feargreed, company_profile, analyst_sentiment, analyst_upgrade, industry_ranking)
  - ✅ All 48 loaders import + --help test OK
  - ✅ Terraform ECS mappings deployed successfully
  - 🔄 **CURRENTLY EXECUTING:** 25+ loaders actively running in ECS
    - **DONE (8):** aaiidata, algo_metrics_daily, analyst_upgrades, earnings_calendar, earnings_surprise, econ_data, feargreed, growth_metrics
    - **RUN (4):** analyst_sentiment, company_profile, earnings_history, earnings_revisions
    - **BLOCKED (9):** financials (annual/quarterly/ttm) + SEC API rate limiting
      - **FIX DEPLOYED:** SEC API rate limiter reduced 8→5 req/sec, backoff 4s→32s (commit 6e6b6631b)
      - **ACTION:** Docker image rebuilding via CI/CD, new image will resolve rate limiting
    - **PENDING (4):** ETF price loaders (eod_bulk_refresh, etf_prices_*)
- ✅ Schema: rs_percentile column added to stock_scores, migration script created
- ✅ Data: price_daily (8.1M rows), company_profile (10.1K), technical_data (8.1M), stock_symbols (10.2K)
- ✅ Alpaca: Paper trading enabled (ALPACA_PAPER=true), margin monitor non-blocking
- ✅ Tests: 297/302 pass, schema validated
- NEXT: Verify ECS completion (scripts/verify_loader_completion.py) → Run remaining 40+ loaders (scripts/batch_run_loaders.py)

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

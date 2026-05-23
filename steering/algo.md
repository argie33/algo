# Stock Analytics Platform — Algo Project Steering

## STATUS
- ✅ Orchestrator: 7 phases pass, cursor pooling fix + Phase 3b optimization deployed
- ✅ Loaders: 31+ core loaders COMPLETE, all critical data loaded
  - ✅ Executed (31): price_daily, technical_data_daily, buy_sell_daily (all variants), signal_quality_scores, trend_template_data, sector_performance, financial annual/quarterly, key/growth/quality/value metrics, swing_trader_scores, analyst_sentiment_analysis, AAII/fear_greed, economic_data, company_profile, earnings history/revisions/surprise
  - Fixed (5): datetime conversion (balance_sheet, income_statement, cash_flow), column names (signal_quality_scores, technical_data_daily), indentation (loadsectors)
  - Status: All primary loaders complete, data validation passed, 27.38 GB loaded
- ✅ Schema: updated_at column added to all tables, migration complete
- ✅ Data: 64/137 tables populated (46.7%) — all critical tables have data
  - price_daily: 8.1M rows | technical_data_daily: 8.1M rows | trend_template_data: 3.7M rows
  - buy_sell_daily: 97K rows | signal_quality_scores: 332K rows | sector_performance: 42 rows
  - Financial annual: 8-10K rows | Quarterly: 3.8-21K rows | ETF prices: 8M rows
- ✅ Alpaca: Paper trading enabled (ALPACA_PAPER=true), margin monitor non-blocking
- ✅ Tests: 297/302 pass, schema validated
- NEXT: Phase 7 orchestrator verification; optional backtest/options/commodity loaders for advanced features (73 empty tables)

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

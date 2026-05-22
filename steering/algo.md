# Stock Analytics Platform — Algo Project Steering

## STATUS
- OK Orchestrator: All 7 phases pass locally, Phase 7 JSON fix deployed
- OK Core loaders: price_daily (8M), technical_data_daily (8M), swing_scores (running refresh), market_health (1.2K)
- IN_PROGRESS Loaders: swing_trader_scores refresh running (was 4 days stale), whitelist fixed for 10 tables
- NEED Loaders: aaii_sentiment, analyst_sentiment, analyst_upgrade, company_profile, fear_greed, industry_ranking, naaim, sector_performance
- OK Frontend: 20+ pages built, API running on 3001, frontend on 5173, both responding
- OK Tests: 297/302 pass (5 position_sizer multiplier - can be tuned)

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
| Orchestrator Phase 4-5 fails | Alpaca creds valid? Paper trading enabled? `ALPACA_PAPER_TRADING=true`? |

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

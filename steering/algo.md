# Stock Analytics Platform — Algo

## STATUS
- ✅ Orchestrator: 7 phases, cursor pooling + Phase 3b opt
- ⚠️ Loaders: 54 → Fixed rate limit cascade (parallel overload). Serial runner + 4-256s SEC EDGAR retry. Running now
- ✅ Database: Schema in code, auto-deploy via Terraform
- ✅ Alpaca: Paper mode enabled
- ✅ Tests: 297/302 pass (tracked in CI)

## SYSTEM MAP
| Component | Code | Deploy | Trigger |
|-----------|------|--------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Λ + Local | Schedule/manual |
| Loaders | `loaders/load_*.py` | ECS Fargate | EventBridge |
| API | `lambda/api/lambda_function.py` | Λ HTTP | API Gateway |
| Frontend | `webapp/frontend/src/` | React + S3/CF | npm build |
| Signals | `algo/algo_signals.py` | Λ (Phase 5) | Orchestrator |

**DB:** `terraform/modules/database/init.sql` → Terraform → RDS. Schema enforced in-repo, docker-compose reuses.

## CREDENTIALS
| Env | Store | Keys |
|-----|-------|------|
| Local | PowerShell profile | DB_HOST, DB_PASSWORD, DB_NAME, APCA, FRED_API_KEY |
| CI | GitHub Secrets | ALPACA, FRED_API_KEY, AWS |
| Prod | AWS Secrets Manager | algo/database, algo/alpaca, algo/fred |
**Rules:** Rotate Q, instant if leaked, ❌ .env

## DEPLOY & RESOURCES
`git push main` → `deploy-code.yml` (auto: test → scan → Terraform → Λ → EB)

| Workflow | Type | Scope |
|----------|------|-------|
| deploy-code.yml | Auto | Tests, scan, code |
| deploy-all-infrastructure.yml | Manual | Terraform, Λ layers, ECS |
| test-orchestrator.yml | Manual | Invoke Λ |
| manual-invoke-loaders.yml | Manual | ECS tasks |

| Resource | Name |
|----------|------|
| ECS Cluster | `algo-cluster` |
| Orchestrator Λ | `algo-algo-dev` |
| API Λ | `algo-api-dev` |
| RDS | `stocks-db.cluster-*.us-east-1.rds.amazonaws.com` |
| Tasks | `algo-{loader}-loader` |

Monitor: https://github.com/argie33/algo/actions

## SCHEDULE (EB, Mon-Fri)
- 4A ET: Price loaders (yfinance, FRED)
- 9:30A ET: Morning orchestrator (fresh prices + technicals)
- 5:30P ET: Evening orchestrator (swing trades)

## KEY FILES
| File | Purpose |
|------|---------|
| `algo/algo_orchestrator.py` | 7-phase main loop |
| `lambda/api/lambda_function.py` | HTTP API, auth, CORS |
| `algo/algo_signals.py` | Phase 5 signal rules |
| `config/credential_manager.py` | Secrets fetcher |
| `terraform/main.tf` | Infra as code |

## TROUBLESHOOTING
| Issue | Fix |
|-------|-----|
| Creds fail | PowerShell profile vars? Postgres running? AWS creds valid? |
| API 401 | Token expired? Cognito env var set? |
| Loaders timeout | Rate limit? VPC internet access? RDS reachable? |
| Signals missing | Data in `technical_data_daily`? Rules in code? |
| Alpaca 401 | Set `ALPACA_PAPER=true` env |


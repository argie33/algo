# Stock Analytics Platform — Algo

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
| Local | PowerShell profile | DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL, APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_PAPER, FRED_API_KEY, AWS_SECRET_ACCESS_KEY |
| CI | GitHub Secrets | APCA_API_KEY_ID, APCA_API_SECRET_KEY, ALPACA_API_KEY, ALPACA_API_SECRET, FRED_API_KEY, AWS_SECRET_ACCESS_KEY |
| Prod | AWS Secrets Manager | algo/database, algo/alpaca, algo/fred |
**Rules:** Rotate Q, instant if leaked, ❌ .env. SEC_USER_AGENT hardcoded in loader_loop.py: `algo-trading email@example.com`

## DEPLOY & RESOURCES
`git push main` → `deploy-code.yml` (auto: test → scan) OR `deploy-all-infrastructure.yml` (terraform + Λ + EB)

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

## LIVE TRADING CONFIG
| Setting | Value | Purpose |
|---------|-------|---------|
| ALGO_LIVE_TRADING | I_UNDERSTAND_REAL_MONEY | Required for live trades |
| ALPACA_PAPER_TRADING | false | Disable paper mode |
| APCA_API_BASE_URL | https://api.alpaca.markets | Live API endpoint |
| execution_mode | auto | Auto-detect live intent |

## LOADER CONFIGURATION
24 loaders: `loaders/load_*.py` (stock prices, technical, metrics, company, earnings, industry, market health, NAAIM, signals, sentiment, value, quality, growth, AAII, fear/greed, weight optimization, balance sheet, cash flow, income statement, analyst upgrades/downgrades, swing trader scores, signal quality scores)

Credentials: SEC_USER_AGENT required for SEC EDGAR API (`algo-trading argeropolos@gmail.com`). Added to Λ + ECS tasks.

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
| Alpaca 401 | Set `ALPACA_PAPER=false` for live trading or `true` for paper |
| Loader failures | Audit → Fix only FAILING loaders. Never rerun working ones ($$). Spot-check known-good tables before queuing tasks. |


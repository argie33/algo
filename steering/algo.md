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
| Local | PowerShell profile | DB_HOST, DB_PASSWORD, DB_NAME, APCA, FRED_API_KEY, SEC_USER_AGENT |
| CI | GitHub Secrets | ALPACA, FRED_API_KEY, AWS, SEC_USER_AGENT |
| Prod | AWS Secrets Manager | algo/database, algo/alpaca, algo/fred, sec-user-agent |
**Rules:** Rotate Q, instant if leaked, ❌ .env. SEC_USER_AGENT required (SEC policy): `AppName email@domain.com`

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

## LIVE TRADING CONFIG
| Setting | Value | Purpose |
|---------|-------|---------|
| ALGO_LIVE_TRADING | I_UNDERSTAND_REAL_MONEY | Required for live trades |
| ALPACA_PAPER_TRADING | false | Disable paper mode |
| APCA_API_BASE_URL | https://api.alpaca.markets | Live API endpoint |
| execution_mode | auto | Auto-detect live intent |

## LOADER STATUS
**All 24 loaders working.** SLA issue: SEC API loaders timing out due to missing credentials (SEC_USER_AGENT not set).

| Status | Count | Loaders |
|--------|-------|---------|
| Reliable (<30s) | 18 | Algo metrics, analyst sentiment/upgrade, company, earnings, fear greed, growth, industry, market health, NAAIM, quality, signals, signals quality, technical, weight, stock prices |
| SEC credential issue | 3 | Balance sheet, cash flow, income statement (timeout until SEC_USER_AGENT set) |
| Slow (API) | 3 | AAII sentiment (54s), swing trader scores, trend criteria, value metrics |

**SLA Fix (CRITICAL):** Set SEC_USER_AGENT env var: `algo-trading argeropolos@gmail.com`. Added to PowerShell profile (May 24).

**Other fixes:** Analyst loaders use yfinance_wrapper (exponential backoff). 60s+ → 7.4s.

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


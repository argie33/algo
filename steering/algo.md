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
`git push main` → `deploy-code.yml` (auto: test → scan) OR `deploy-all-infrastructure.yml` (terraform + Λ + EB)
**CURRENT BLOCKER:** RDS parameter group state mismatch — running bootstrap & state cleanup fixes

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
**All 39 loaders blocked at NO_RECENT_RUNS** — waiting for infrastructure deploy to complete.

| Status | Count |
|--------|-------|
| BLOCKED | 39 | Infrastructure deployment failing (RDS parameter group blocker) |

Previous fixes: SEC_USER_AGENT, analyst loaders backoff, parameter group removal

**SEC Fix (COMPLETE):** SEC_USER_AGENT: `algo-trading argeropolos@gmail.com`. Added to Loader, Orchestrator, Data Patrol ECS task defs (May 24).

**RDS Fix:** Default parameter group (removed stale custom group). Resolves terraform conflicts.

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


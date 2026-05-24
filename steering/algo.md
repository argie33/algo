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

## LIVE TRADING CONFIG
| Setting | Value | Purpose |
|---------|-------|---------|
| ALGO_LIVE_TRADING | I_UNDERSTAND_REAL_MONEY | Required for live trades |
| ALPACA_PAPER_TRADING | false | Disable paper mode |
| APCA_API_BASE_URL | https://api.alpaca.markets | Live API endpoint |
| execution_mode | auto | Auto-detect live intent |

## LOADER STATUS (May 24, 2026)
**Validation:** 24/24 loaders working. 22 complete <20s with 10 symbols. 2 (stock prices) <120s (process 6 combinations).

| Category | Count | Loaders |
|----------|-------|---------|
| Fast (<10s) | 18 | Analyst sentiment, upgrade, algo metrics, company, earnings, fear greed, growth, industry, market health, naaim, quality, signals, quality scores, technical, trend, value, weight |
| Medium (10-20s) | 4 | Balance sheet, cash flow, income, AAII sentiment |
| Slow (20-120s) | 2 | Stock prices (daily, weekly) — process 3 intervals × 2 asset classes |

**Recent fixes:** yfinance loaders (analyst sentiment/upgrade) now use wrapper with exponential backoff retry logic.

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


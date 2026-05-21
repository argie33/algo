# Stock Analytics Platform — Algo Project Steering

## STATUS
- **Orchestrator:** ✅ 7 phases operational locally, AWS Lambda deployed
- **Loaders:** ⚠️ Running on schedule but DATA INCOMPLETE — need verification of successful completion
- **Frontend:** ⚠️ 4/13 pages 100% working (marketing), 9/13 partial/zero (render but missing data)
- **API:** ✅ Connected to PostgreSQL, Vite proxy fixed to port 3001, endpoints returning data
- **Database:** ✅ Connected, core metrics populated (key_metrics, value_metrics, quality_metrics, company_profile for 10K stocks)
- **Blocker:** Pages with dashes (—) & zero elements indicate incomplete data in: market indices, economic data, signals, backtest results
- **Root Cause:** Loaders must fetch & populate remaining tables from external APIs (FRED, yfinance, Alpaca, etc.)

## SYSTEM MAP
| Component | Code | Deployment | Trigger | Purpose |
|-----------|------|-----------|---------|---------|
| Orchestrator | `algo/algo_orchestrator.py` | Lambda + Local | Schedule/manual | 7 phases: load → filter → signal → validate → execute |
| Data Loaders | `loaders/load_*.py` | ECS Fargate | EventBridge | Fetch prices, earnings, technicals → PostgreSQL |
| API | `lambda/api/lambda_function.py` | Lambda HTTP | API Gateway | REST endpoints (signals, prices, portfolio) — Bearer token required |
| Frontend | `webapp/frontend/src/` | React + CloudFront/S3 | `npm run build` + push | Dashboard (Cognito auth) |
| Signals | `algo/algo_signals.py` | Called by Orchestrator | Phase 5 | Technical indicators (RSI, SMA, EMA, ATR) |

## DB SCHEMA
**Single source of truth:** `terraform/modules/database/init.sql`
- Terraform deploys it → Lambda applies on startup → RDS gets schema
- **RULE:** Never scatter init scripts in separate files (Python, JS, SQL elsewhere). One place only.
- Local dev: `docker-compose up` uses same `init.sql`

## CREDENTIALS
**Policy:** No `.env` files. Use:
- **Local:** PowerShell profile at `C:\Users\arger\OneDrive\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1` (DB_HOST, DB_PASSWORD, DB_NAME, APCA_API_KEY_ID, APCA_API_SECRET_KEY, FRED_API_KEY)
- **CI/CD:** GitHub Secrets (ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY, FRED_API_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- **Production:** AWS Secrets Manager paths: `algo/database`, `algo/alpaca`, `algo/fred`

**Rules:** ✅ Rotate quarterly. ✅ If secrets appear in git history, rotate immediately. ❌ Never .env files.

## DEPLOY
```bash
git push origin main  # Triggers deploy-code.yml (auto)
# GH Actions: scan → test → security check → Terraform → Lambda → EventBridge
```
Key workflows:
- `deploy-code.yml` — auto on push (tests, secret scan, deploy code)
- `deploy-all-infrastructure.yml` — manual (Terraform, Lambda layers, ECS)
- `test-orchestrator.yml` — manual (invoke Lambda with test payload)
- `manual-invoke-loaders.yml` — manual (trigger loader execution)

Monitor: https://github.com/argie33/algo/actions

## AWS RESOURCE NAMES
| Resource | Name | Terraform Var |
|----------|------|---------------|
| ECS Cluster | `algo-cluster` | `project_name=algo` |
| Orchestrator Lambda | `algo-algo-dev` | — (derived from project + env) |
| API Lambda | `algo-api-dev` | — |
| RDS | `stocks-db.cluster-*.us-east-1.rds.amazonaws.com` | `db_cluster_name` |
| ECS Tasks | `algo-{loader_name}-loader` | — |
| Environment | `-dev` (all suffixed) | `environment=dev` |

## SCHEDULE (EventBridge, Mon-Fri)
- **4:00 AM ET** — Price loaders run (yfinance, FRED, etc.)
- **9:30 AM ET** — Morning orchestrator (fresh prices + yesterday's technicals)
- **5:30 PM ET** — Evening orchestrator (complete dataset for swing trades)

## KEY FILES
- `lambda/api/lambda_function.py` — API auth, CORS, rate limits, security headers
- `algo/algo_orchestrator.py` — 7-phase orchestrator (core logic)
- `terraform/main.tf` — Infrastructure (VPC, RDS, Lambda, ECS)
- `config/credential_manager.py` — AWS Secrets Manager + GitHub Secrets fetcher
- `algo/algo_signals.py` — Buy/sell signal logic (Phase 5)

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
# Run tests
python3 -m pytest tests/ -v

# Validate credentials
python3 config/credential_validator.py

# Dry-run orchestrator
python3 algo/algo_orchestrator.py --dry-run

# Frontend dev (2 terminals)
cd webapp/lambda && DB_SSL=false node index.js  # Port 3001 (Vite proxies /api to here)
cd webapp/frontend && npm run dev   # Port 5173 (vite.config.js set to proxy to 3001)

# Live trading (real)
ORCHESTRATOR_DRY_RUN=false python3 algo/algo_orchestrator.py
```

## ROUTING ARCHITECTURE
**Frontend (React Router):**
- `/*` — Public marketing site (/, /about, /firm, /contact, /terms, /privacy)
- `/app/*` — Authenticated dashboard (requires ProtectedRoute wrapper)
  - `/app/markets`, `/app/economic`, `/app/sectors`, `/app/sentiment` — Market data
  - `/app/trading-signals`, `/app/deep-value`, `/app/swing` — Stock signals
  - `/app/scores`, `/app/backtests` — Analysis
  - `/app/portfolio`, `/app/trades`, `/app/performance` — Portfolio (auth required)
  - `/app/health`, `/app/audit`, `/app/algo-dashboard` — Admin (admin role required)
- **Fixed:** Removed duplicate routes (/app/market, /app/signals, /app/etf-signals) that caused intermittent failures

**Backend (Express Routes):**
- `/api/scores` — Stock multi-factor scoring (fixed to return stock_scores, not swing_trader_scores)
- `/api/signals` — Trading signals (from buy_sell_daily table)
- `/api/market` — Market health + indices
- `/api/economic` — Economic indicators
- `/api/sectors` — Sector performance
- `/api/trades` — Trade execution + history
- `/api/backtests` — Backtest results (also at `/api/research/backtests`)
- `/api/prices` — Historical prices
- Full routes in: `webapp/lambda/routes/*.js`

**Rule:** One route → one component → one API call. Duplicates cause race conditions.

## DECISION RATIONALE
- **Alpaca:** Supports paper + live trading, SRP auth, low friction
- **PostgreSQL:** Time-series data, ACID, efficient lateral joins for enrichment
- **Lambda API:** Serverless, OIDC auth (no long-lived keys), auto-scales
- **ECS Loaders:** Scheduled batch jobs, pulls large datasets without timeout, separate from API
- **Cognito:** SRP auth (password never sent plain), MFA, session tokens (not localStorage)
- **Dual-Layout:** Marketing (`/*`) + Dashboard (`/app/*`) prevents auth bleed, clarity on scope

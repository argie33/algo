# Stock Analytics Platform — Live Trading

## STATUS & GOAL
**GOAL:** Algo running LIVE with fresh data automatically every day before market open.
- **Local:** ✅ 100% working (orchestrator executes all 7 phases, 282 tests passing)
- **AWS:** ✅ Infrastructure deployed + Orchestrator working in LIVE mode
- **Blocker:** Verify loaders run on schedule and load fresh real data daily
- **Next:** (1) Test loaders execute correctly, (2) Verify fresh data loads, (3) Confirm orchestrator uses it

## WHY This Matters
Trading platform with real Alpaca credentials (paper + live). Security = non-negotiable. Every component must be bulletproof. Credentials rotated quarterly. Data flows: markets → loaders → database → signals → trades.

## SYSTEM MAP
| Component | Code | Where | Trigger | What |
|-----------|------|-------|---------|------|
| **Orchestrator** | `algo/algo_orchestrator.py` | Lambda + Local | Schedule/manual | Runs all 7 phases: load data → filter → signal → validate → execute trades |
| **Data Loaders** | `loaders/load_*.py` | ECS Fargate | EventBridge schedule | Fetch prices, earnings, technicals from yfinance/FRED/Alpaca → PostgreSQL |
| **API** | `lambda/api/lambda_function.py` | Lambda HTTP | API Gateway | REST endpoints for signals, prices, portfolio (requires Bearer token) |
| **Frontend** | `webapp/frontend/src/` | React → CloudFront/S3 | `npm run build` + git push | Dashboard (Cognito auth) |
| **Signals** | `algo/algo_signals.py` | Called by Orchestrator | Orchestrator Phase 5 | Buy/sell signals from technical indicators (RSI, SMA, EMA, ATR, stages) |
| **Tests** | `tests/`, `lambda/api/tests/` | Local | `pytest` | Unit + integration tests (282 passing) |

## DATABASE SCHEMA (IaC Best Practice)

**Single source of truth:** `terraform/modules/database/init.sql`
- Defines all tables including buy_sell_daily with loader-required columns (timeframe, signal_type, macd, macd_signal, etc)
- Terraform deploys it → Lambda reads it on startup → applies to RDS
- **NEVER** create separate init scripts (Python, JS, SQL files scattered around)
- Schema changes: edit init.sql, commit, deploy via Terraform
- Local dev: `docker-compose up` runs the same init.sql

## CREDENTIALS

### ⚠️ CRITICAL: NO .env FILES. EVER.
`.env` files leak secrets to git history. Use ONLY:
1. **PowerShell Profile** (local dev): `C:\Users\arger\OneDrive\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`
2. **GitHub Secrets** (CI/CD): `gh secret set ALPACA_API_KEY_ID "..."`
3. **AWS Secrets Manager** (Lambda/ECS): Via Terraform + IAM roles

**GitHub Secrets** (for CI/CD):
- `ALPACA_API_KEY_ID` — Paper trading key
- `ALPACA_API_SECRET_KEY` — Paper trading secret
- `FRED_API_KEY` — Economic data API key
- `AWS_ACCESS_KEY_ID` — IAM user for Terraform
- `AWS_SECRET_ACCESS_KEY` — IAM user for Terraform

**AWS Secrets Manager** (production Lambda/ECS):
- `algo/database` → `{host, user, password, port, database}`
- `algo/alpaca` → `{api_key, api_secret}`
- `algo/fred` → `{api_key}`

**Local Dev Only** (PowerShell Profile):
```powershell
# C:\Users\arger\OneDrive\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
$env:DB_HOST="localhost"
$env:DB_PASSWORD="stocks"
$env:DB_NAME="stocks"
$env:APCA_API_KEY_ID="PKQ4H6RGJFWUOPFARVUU5LEM2X"
$env:APCA_API_SECRET_KEY="2X9ZXfvw1BQThdZXpbZqmfwABEFZozQw1imTrdhDq7VG"
$env:FRED_API_KEY="..."
```

**Rules**:
- ❌ NEVER hardcode credentials in code or .env files
- ❌ NEVER commit .env or .env.local to git
- ✅ Always use PowerShell profile (local), GitHub Secrets (CI), AWS Secrets Manager (AWS)
- ✅ Rotate credentials quarterly
- ✅ If secrets appear in git history, rotate them immediately

## DEPLOYMENT (GitHub Actions Only)

**All deployment goes through GitHub Actions. No manual AWS CLI/Terraform commands.**

### Step 1: Setup AWS Secrets (One-Time)
```bash
# Get Alpaca paper keys: https://app.alpaca.markets/settings/api-keys
# Get FRED key: fred.stlouisfed.org → settings
# Get RDS endpoint from AWS Console → RDS

aws secretsmanager create-secret --name algo/alpaca \
  --secret-string '{"api_key":"...","api_secret":"..."}' --region us-east-1

aws secretsmanager create-secret --name algo/fred \
  --secret-string '{"api_key":"..."}' --region us-east-1

aws secretsmanager create-secret --name algo/database \
  --secret-string '{"host":"...","user":"stocks","password":"...","port":5432}' --region us-east-1
```

### Step 2: Deploy Code & Infrastructure
```bash
git add .
git commit -m "ready for deployment"
git push origin main

# GitHub Actions will:
# 1. Scan for secrets (TruffleHog)
# 2. Run tests (pytest)
# 3. Check security (bandit, pip-audit, tfsec)
# 4. Deploy Terraform (infrastructure)
# 5. Deploy Lambda functions
# 6. Update EventBridge schedules

# Monitor at: https://github.com/argie33/algo/actions
```

### Step 3: Verify Deployment
```bash
# Check Lambda deployed
aws lambda get-function-configuration --function-name algo-algo-dev --region us-east-1

# Check logs
aws logs tail /aws/lambda/algo-algo-dev --follow --region us-east-1

# Test orchestrator
aws lambda invoke --function-name algo-algo-dev --payload '{"source":"schedule"}' response.json --region us-east-1
```

### Test Locally
```bash
# Setup
python3 init_database.py
python3 run-all-loaders.py

# Unit tests
python3 -m pytest tests/ -v

# Validate credentials are accessible
python3 config/credential_validator.py

# Dry run orchestrator
python3 algo/algo_orchestrator.py --dry-run

# Check signal logic
python3 -m pytest algo/ -v -k "signal"
```

### Frontend Dev (Local)
```powershell
# Terminal 1: API server
cd webapp/lambda
node index.js  # Runs on port 3002

# Terminal 2: Frontend dev server
$env:VITE_FORCE_DEV_AUTH="true"
$env:VITE_DEV_AUTH_PASSWORD="Admin123!"
cd webapp/frontend
npm run dev  # Runs on port 5173

# Browser: http://localhost:5173
# Login with: dev-admin / Admin123!
```

### Run Live Trading (Local)
```bash
ORCHESTRATOR_DRY_RUN=false python3 algo/algo_orchestrator.py
# Fetches data → generates signals → (if authorized) places real trades with Alpaca
```

### Verify After Deploy
```bash
# Check Lambda is running
aws lambda get-function-configuration --function-name stocks-api-dev

# Check database connectivity
python3 config/credential_validator.py

# Hit API
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/api/signals

# View logs
aws logs tail /aws/lambda/stocks-api-dev --follow
aws logs tail /ecs/stocks-loaders --follow
```

## DECISION CONTEXT

**Why Alpaca?** Supports paper + live trading, SRP auth, low friction.

**Why PostgreSQL?** Time-series data (prices, indicators), ACID compliance, lateral joins for signal enrichment.

**Why Lambda for API?** Serverless, OIDC auth (no long-lived keys), scales automatically.

**Why ECS for loaders?** Scheduled batch jobs, can pull large datasets without timeouts, separate compute from API.

**Why Cognito?** SRP auth (password never sent plain), MFA support, session tokens (not localStorage).

**Security First:** All credentials in Secrets Manager, no env files, API requires Bearer token, audit logging, CSP headers.

## TROUBLESHOOTING

**"Credential validator fails"**
→ Check: `$env:DB_HOST`, `$env:DB_PASSWORD` set? Postgres running locally? AWS Secrets Manager accessible?

**"API returns 401"**
→ Check: Bearer token present? Token expired? Cognito enabled (`COGNITO_ENABLED=true` in Lambda env)?

**"Loaders timeout"**
→ Check: yfinance rate limiting? VPC has internet access? RDS can accept connections?

**"Signals not generating"**
→ Check: Technical indicators in `technical_data_daily` table? Buy/sell rules in `algo_signals.py` logic?

**"Orchestrator Phase 4-5 fails"**
→ Check: Alpaca credentials valid? Paper trading enabled? `ALPACA_PAPER_TRADING=true`?

## FILE STRUCTURE
```
algo/               # Trading algorithms, signal logic, orchestrator
loaders/            # Data loaders (prices, earnings, technicals)
lambda/             # Lambda functions (API, orchestrator)
  api/              # REST API handler
  algo_orchestrator/# Orchestrator handler
webapp/             # Frontend (React) + infrastructure
  frontend/         # React app (Cognito auth)
terraform/          # Infrastructure as Code (VPC, RDS, Lambda, ECS, etc.)
tests/              # Test suites (unit + integration)
config/             # Credential manager, env loader, validator
.github/workflows/  # CI/CD (TruffleHog, pytest, deploy)
```

## CRITICAL NAMING & CONFIGURATION

**Terraform Vars** (terraform/terraform.tfvars):
- `project_name = "algo"` → All AWS resources prefixed `algo-*`
- `environment = "dev"` → All names end with `-dev`
- `alpaca_paper_trading = false` → LIVE trading (true=paper/sandbox)
- `orchestrator_dry_run = false` → Actually execute trades

**AWS Resource Names** (derived from Terraform):
- ECS Cluster: `algo-cluster` (NOT `stocks-cluster`)
- Orchestrator Lambda: `algo-algo-dev` (NOT `stocks-algo-prod`)
- API Lambda: `algo-api-dev`
- RDS: `stocks-db.cluster-*.us-east-1.rds.amazonaws.com`
- Loaders: ECS task defs named `algo-{loader_name}-loader`

**Workflows to Use**:
- Deploy code: `gh workflow run deploy-code.yml` (auto-triggered on git push)
- Deploy infrastructure: `gh workflow run deploy-all-infrastructure.yml` (manual only)
- Test orchestrator: `gh workflow run test-orchestrator.yml` (manual)
- Test loaders: `gh workflow run manual-invoke-loaders.yml` (manual)

**Execution Schedule** (EventBridge in Terraform):
- 4:00 AM ET (9:00 UTC Mon-Fri): Price loaders run
- 9:30 AM ET (2:30 PM UTC Mon-Fri): Morning orchestrator (fresh prices + yesterday's technicals)
- 5:30 PM ET (10:30 PM UTC Mon-Fri): Evening orchestrator (complete dataset)

## KEY FILES (Don't Modify Without Understanding)
- `lambda/api/lambda_function.py` — API auth, rate limiting, security headers, CORS
- `algo/algo_orchestrator.py` — 7 phases: load → filter → enrich → signal → validate → size → execute
- `terraform/main.tf` — Infrastructure orchestration
- `config/credential_manager.py` — Secret fetching (GitHub Secrets + AWS Secrets Manager)
- `LIVE_TRADING_CHECKLIST.md` — Pre-market verification steps

## See Also
- `LIVE_TRADING_CHECKLIST.md` — Full pre-launch checklist
- `ARCHITECTURE.md` — Detailed system design
- `.github/workflows/deploy-code.yml` — CI/CD pipeline definition

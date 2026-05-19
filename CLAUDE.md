# Stock Analytics Platform — Live Paper Trading

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

## CREDENTIAL ARCHITECTURE
```
GitHub Secrets (source)
  ↓ (encrypted)
.github/workflows/* (reference them)
  ↓ (at runtime)
AWS Secrets Manager (stored)
  ↓ (Lambda fetches via boto3)
Lambda env vars ($DB_SECRET_ARN, $ALGO_SECRETS_ARN)
  ↓ (at execution)
Python: boto3.client('secretsmanager').get_secret_value()
```

**Secrets in AWS Secrets Manager (JSON format):**
- `algo/database` → `{username, password, host, port, dbname}`
- `algo/alpaca` → `{api_key_id, api_secret_key, base_url}`
- `algo/fred` → `{api_key}`

**Local Dev:**
Set in PowerShell profile:
```powershell
$env:DB_HOST="localhost"
$env:DB_PASSWORD="stocks"
$env:DB_NAME="stocks"
$env:ALPACA_API_KEY_ID="..."
$env:ALPACA_API_SECRET_KEY="..."
$env:FRED_API_KEY="..."
```

**Never:** Hardcode credentials, commit `.env`, print secrets in logs.

## HOW TO WORK HERE

### Deploy Code
```bash
git push origin main
# → GitHub Actions: TruffleHog (secrets scan) → pip-audit (deps) → bandit (SAST) → tfsec (Terraform)
# → Lambda redeploy (2-5 min)
# → Monitor: .github/workflows/deploy-code.yml
```

### Deploy Infrastructure
```bash
cd terraform
terraform plan -var-file=terraform.tfvars
terraform apply
# → New AWS resources: CloudTrail, RDS, Lambda, ECS, CloudFront, Cognito, etc.
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

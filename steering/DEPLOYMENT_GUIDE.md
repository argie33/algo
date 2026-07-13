# Deployment Guide: Lambda, Infrastructure & Testing

This guide walks through deploying the system and verifying operational readiness.

## Local Testing & Development

### Option 1: Quick Validation (5 min)
```bash
# Validate orchestrator readiness
python3 scripts/validate_orchestrator_readiness.py

# Test orchestrator end-to-end (dry run, no trading)
ORCHESTRATOR_EXECUTION_MODE=paper python3 scripts/test_orchestrator_execution.py
```

### Option 2: Paper Trading Mode (Simulated Execution)
```bash
# Set environment
export ORCHESTRATOR_EXECUTION_MODE=paper
export ORCHESTRATOR_DRY_RUN=false

# Run orchestrator (no actual Alpaca trades, but records to DB)
python3 -c "
from algo.orchestration import Orchestrator
from algo.infrastructure import get_config
config = get_config()
orch = Orchestrator(config=config, dry_run=False)
orch.execute()
"
```

### Option 3: Dashboard Development
```bash
cd webapp/frontend
npm install
npm run dev
# Opens at http://localhost:5173
# API proxy configured for localhost:3001 in dev mode
```

## AWS Deployment Prerequisites

### Step 1: Fix IAM Permissions
Contact AWS admin to grant `algo-developer` user:
- All DynamoDB permissions
- All Events (EventBridge) permissions  
- All Lambda permissions (invoke + configuration)
- All Logs permissions
- EC2 security group management (for RDS)

### Step 2: Set GitHub Secrets (if using GitHub Actions)
Required secrets in repository:
```
AWS_ACCOUNT_ID
GITHUB_ACTIONS_ROLE_ARN
ALPACA_API_KEY_ID
ALPACA_API_SECRET_KEY
JWT_SECRET
FRED_API_KEY
ALERT_EMAIL_ADDRESS
ALERT_SMTP_PASSWORD
TF_STATE_BUCKET
TF_STATE_KEY
```

### Step 3: Deploy Infrastructure
```bash
# Option A: Via GitHub Actions (Recommended)
# 1. Push code to main branch
# 2. Go to Actions → "Deploy All Infrastructure"
# 3. Click "Run workflow"
# 4. Monitor deployment in workflow logs

# Option B: Local Terraform (Requires IAM permissions)
cd terraform
terraform init -reconfigure
terraform plan
terraform apply -lock=false
```

## Data Loader Configuration

### Loader Execution Schedule (EventBridge Scheduler)
Once deployed, loaders execute on this schedule:

**2:15 AM ET (Morning Pipeline)**
- `load_prices` - Fetch OHLCV data  
- `load_technical_data_daily` - Compute SMA/momentum  
- `load_swing_trader_scores` - Swing score calculation

**4:05 PM ET (EOD Pipeline)**
- Stage 1: `load_prices`, `load_market_exposure_daily`, `load_fred_economic_data`
- Stage 2 (after Stage 1): metric loaders (quality, growth, value, positioning, stability)
- Stage 3 (after Stage 2): `load_stock_scores` - composite score calculation

### Orchestrator Execution Schedule (EventBridge Scheduler)
Once deployed, orchestrator executes:

**9:30 AM ET** (Morning - PRIMARY)  
**1:00 PM ET** (Afternoon - Rebalance)  
**3:00 PM ET** (Pre-close - Final positions)  
**5:30 PM ET** (EOD - Position management)

## Dashboard Setup

### Local Development
```bash
cd webapp/frontend
npm run dev
# Dashboard at http://localhost:5173
# API proxied to http://localhost:3001
```

### Production Deployment  
Dashboard deploys via GitHub Actions workflow: `deploy-frontend-only.yml`
- Builds React app with Vite
- Uploads to S3 cloudfront bucket
- Invalidates CloudFront cache

**Production API Configuration:**
- Uses `VITE_API_URL` environment variable or relative paths
- CloudFront routes `/api/*` to API Gateway (same-origin, no CORS needed)

## Known Issues & Workarounds

### Issue 1: Stale Loaders During Development
**Symptom:** Orchestrator halts due to stale `market_health_daily` or `market_exposure_daily`  
**Workaround:**
```python
# Run this before orchestrator tests
from datetime import datetime, timezone
from utils.db import DatabaseContext

yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
with DatabaseContext('write') as cur:
    cur.execute("""
        INSERT INTO market_health_daily (date, market_stage, vix_level, ...)
        VALUES (%s, 2, 16.0, ...) ON CONFLICT (date) DO UPDATE SET ...
    """)
```

### Issue 2: Alpaca Credentials Not Required for Paper Mode
**Behavior:** System gracefully continues without Alpaca credentials  
**Impact:** Paper trading works (records to DB, doesn't execute actual trades)  
**Why:** Phase 4 (Reconciliation) skips credential validation for paper mode

### Issue 3: DynamoDB Not Accessible Locally
**Symptom:** Price loader logs "AccessDeniedException" for DynamoDB  
**Impact:** None - falls back to constraint maximums  
**Expected:** OK for local development; needs IAM fix for production

## Testing Checklist

Before claiming system ready:

- [ ] Orchestrator validates environment correctly
- [ ] Price loader retrieves current market data
- [ ] Market health data is fresh (< 1 day old)
- [ ] Dashboard loads at localhost:5173
- [ ] Dashboard displays portfolio panel
- [ ] Dashboard displays positions panel  
- [ ] Dashboard displays trading signals
- [ ] Paper trading orchestrator executes without errors
- [ ] Database records positions and trades
- [ ] All 9 phases complete (or explicitly skipped with reason)


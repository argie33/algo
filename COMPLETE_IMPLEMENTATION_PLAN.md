# Complete Implementation Plan - Getting the Site Working Everywhere

**Principle:** IaC Only + GitHub Actions Only. No manual deployments. Everything version controlled.

---

## What We Have Now ✅

1. **60+ table database schema** (init_db.sql) - Ready
2. **Docker Compose setup** - Auto-initializes schema locally
3. **GitHub Actions workflow** - Schema initialization for AWS RDS
4. **Local development guide** - Complete setup instructions
5. **API Lambda code** - All routes defined (30+ endpoints)
6. **Algo orchestrator** - 7-phase trading system
7. **Existing GitHub Actions** - Deploy workflows for infra, webapp, algo, loaders

---

## What Still Needs to Work

### 🔴 Critical Path (Must Do First)

1. **Local Testing**
   - [ ] Docker Compose brings up with schema
   - [ ] API server starts and can query database
   - [ ] Algo can run end-to-end (7 phases)
   - [ ] Data loaders can populate data

2. **AWS Deployment**
   - [ ] Deploy core infrastructure (VPC, RDS, etc.)
   - [ ] Initialize RDS schema (via GitHub Actions)
   - [ ] Deploy Lambda API
   - [ ] Deploy ECS loaders
   - [ ] Deploy algo orchestrator
   - [ ] Load initial data

3. **Integration Testing**
   - [ ] 30+ API endpoints work
   - [ ] Portfolio management works
   - [ ] Trading works
   - [ ] Algo orchestration works
   - [ ] Data loaders populate fresh data

---

## Step 1: Local Development Setup ✅

### Already Done:
- init_db.sql has all 60+ tables
- docker-compose.yml mounts init_db.sql
- LOCAL_DEV_SETUP.md has all instructions

### What Happens When User Runs `docker-compose up -d`:
```
┌─ docker-compose up -d
│
├─ Postgres container starts
│  ├─ init_db.sql auto-runs on first startup
│  ├─ Creates 60+ tables
│  ├─ Inserts sample data (AAPL, MSFT, GOOGL)
│  └─ Ready in ~30 seconds
│
├─ Redis container starts
├─ LocalStack container starts (S3, Lambda simulation)
└─ Database ready for testing
```

**Test Locally:**
```bash
npm start              # API works
python3 algo_run_daily.py  # Algo works
python3 loadpricedaily.py  # Data loads
```

---

## Step 2: AWS Deployment via GitHub Actions

### Current Workflow Chain:
```
master: deploy-all-infrastructure.yml
├─ cleanup.yml (pre-deployment cleanup)
├─ bootstrap-oidc.yml (GitHub OIDC setup)
├─ deploy-core.yml (VPC, networking, ECR)
├─ deploy-data-infrastructure.yml (RDS, ECS cluster)
├─ deploy-webapp.yml (Lambda API)
├─ deploy-loaders.yml (ECS data loaders)
└─ deploy-algo.yml (algo orchestrator Lambda)
```

### What's Missing: Schema Initialization Step

**Need to Add:**
Between `deploy-data-infrastructure.yml` and `deploy-webapp.yml`, add:
- `initialize-database-schema.yml` ← We just created this!

**Flow:**
```
deploy-data-infrastructure.yml (creates RDS)
        ↓
initialize-database-schema.yml (init_db.sql on RDS) ← NEW
        ↓
deploy-webapp.yml (API can now query tables)
deploy-loaders.yml (loaders can populate data)
deploy-algo.yml (algo can trade)
```

### Updated Orchestrator Workflow

```yaml
# .github/workflows/deploy-all-infrastructure.yml
# (Add this step)

data-infrastructure:
  name: 3. Deploy Data Infrastructure
  needs: core
  uses: ./.github/workflows/deploy-data-infrastructure.yml
  secrets: inherit
  outputs:
    rds_endpoint: ${{ steps.rds.outputs.endpoint }}

initialize-schema:        # ← NEW STEP
  name: 4. Initialize Database Schema
  needs: data-infrastructure
  uses: ./.github/workflows/initialize-database-schema.yml
  with:
    rds_endpoint: ${{ needs.data-infrastructure.outputs.rds_endpoint }}
  secrets: inherit

webapp:
  name: 5. Deploy Webapp (Lambda API)
  needs: initialize-schema  # ← Changed from 'data-infrastructure'
  uses: ./.github/workflows/deploy-webapp.yml
  secrets: inherit

loaders:
  name: 6. Deploy Loaders (ECS)
  needs: initialize-schema  # ← Changed
  uses: ./.github/workflows/deploy-loaders.yml
  secrets: inherit

algo:
  name: 7. Deploy Algo Orchestrator
  needs: initialize-schema  # ← Changed
  uses: ./.github/workflows/deploy-algo.yml
  secrets: inherit
```

---

## Step 3: Initial Data Population

### Currently: Manual (❌ Not IaC)
```bash
# User has to manually run
python3 loadpricedaily.py
# This is NOT IaC ❌
```

### Better: GitHub Actions Workflow

**Option A: Post-Deployment Data Load (Recommended)**
- Create workflow: `populate-initial-data.yml`
- Runs after `deploy-loaders.yml` succeeds
- Triggers ECS tasks to load:
  - Stock symbols
  - Price data (last 1 year)
  - Analyst sentiment
  - Earnings data
  - Technical indicators

**Option B: ECS Scheduled Task**
- Configure in CloudFormation template
- Automatically runs on schedule
- Loads fresh data daily

**Option C: Manual Trigger (Current)**
- User can run workflow manually
- `gh workflow run populate-initial-data.yml`
- But also scheduled via EventBridge

### Data Load Workflow (to create)

```yaml
name: Populate Initial Data

on:
  workflow_call:  # Called by deploy-all-infrastructure.yml
  workflow_dispatch:  # Manual trigger
  schedule:  # Also run nightly
    - cron: '30 4 * * 1-5'  # Weekdays 4:30 AM

jobs:
  load-initial-data:
    name: Load Stock Data + Financials
    runs-on: ubuntu-latest
    steps:
      - name: Load stock symbols
        run: |
          # Run ECS task: load-symbols
          aws ecs run-task \
            --cluster stocks-data-cluster \
            --task-definition load-symbols:1 \
            --region us-east-1

      - name: Load price history
        run: |
          # Run ECS task: load-prices
          aws ecs run-task \
            --cluster stocks-data-cluster \
            --task-definition load-prices:1 \
            --region us-east-1

      - name: Load financial data
        run: |
          # Run ECS task: load-financials
          # etc.
```

---

## Step 4: Integration Testing (GitHub Actions CI)

### Current CI: `ci-fast-gates.yml`
```yaml
- Linting (ESLint, flake8)
- Unit tests
- Type checking
```

### Need to Add: API Integration Tests

**New Workflow: `ci-integration-tests.yml`**

```yaml
name: Integration Tests

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * *'  # Daily

jobs:
  start-local-env:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: stocks
          POSTGRES_USER: stocks
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

  test-api-endpoints:
    name: Test 30+ API Endpoints
    needs: start-local-env
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
        working-directory: webapp/lambda
      - run: npm run test:api
        working-directory: webapp/lambda

  test-algo-orchestrator:
    name: Test Algo (7-Phase Orchestrator)
    needs: start-local-env
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: python3 algo_run_daily.py --dry-run

  test-data-loaders:
    name: Test Data Loaders
    needs: start-local-env
    steps:
      - uses: actions/checkout@v4
      - run: python3 loadpricedaily.py --test --limit 10

  security-scan:
    name: Security Checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm audit --production
        working-directory: webapp/lambda
```

---

## Complete Deployment Flow

```
USER ACTION: git push main
        ↓
GitHub Actions: ci-fast-gates.yml (lint, unit tests)
        ↓ [if successful]
GitHub Actions: deploy-all-infrastructure.yml
        ├─ Cleanup (pre-deploy)
        ├─ Bootstrap OIDC
        ├─ Deploy Core (VPC, ECR, S3)
        ├─ Deploy Data (RDS, ECS cluster)
        ├─ ✨ Initialize Schema (NEW) ← init_db.sql on RDS
        ├─ Deploy Webapp (Lambda API)
        ├─ Deploy Loaders (ECS tasks)
        └─ Deploy Algo (Lambda orchestrator)
        ↓
GitHub Actions: populate-initial-data.yml (NEW)
        ├─ Load symbols
        ├─ Load prices
        ├─ Load financials
        └─ Load analyst sentiment
        ↓
GitHub Actions: ci-integration-tests.yml (NEW)
        ├─ Test 30+ API endpoints
        ├─ Test algo orchestrator
        ├─ Test data loaders
        └─ Security scans
        ↓
✅ SITE FULLY DEPLOYED & TESTED
```

---

## Files to Create / Modify

### ✅ Already Created:
- `init_db.sql` - 60+ tables
- `.github/workflows/initialize-database-schema.yml` - Schema init
- `LOCAL_DEV_SETUP.md` - Local dev guide
- `SCHEMA_DEPLOYMENT_GUIDE.md` - Schema deployment

### ⏭️ Need to Create:
1. `.github/workflows/populate-initial-data.yml`
2. `.github/workflows/ci-integration-tests.yml`
3. Update `.github/workflows/deploy-all-infrastructure.yml` (add schema init step)

### ⏭️ Need to Verify:
- `deploy-core.yml` - Creates VPC, RDS parameter group
- `deploy-data-infrastructure.yml` - Creates RDS instance
- `deploy-webapp.yml` - Lambda API deployment
- `deploy-loaders.yml` - ECS loader deployment
- `deploy-algo.yml` - Algo orchestrator deployment

---

## What Gets Deployed Where

### Local (docker-compose)
```
✅ PostgreSQL with 60+ tables
✅ Redis
✅ LocalStack (S3, Secrets, Lambda simulation)
✅ pgAdmin (UI, optional)
✅ Redis Commander (UI, optional)
```

### AWS (GitHub Actions)
```
✅ VPC with public/private subnets
✅ RDS PostgreSQL with 60+ tables
✅ S3 buckets
✅ Secrets Manager
✅ Lambda: webapp API (30+ endpoints)
✅ Lambda: algo orchestrator (7-phase)
✅ ECS cluster + tasks: data loaders
✅ EventBridge: scheduled algo execution
✅ CloudFront: frontend CDN
✅ Cognito: authentication
```

---

## Data Flow

```
STOCK DATA SOURCES
├─ Alpaca (price history, account)
├─ IEX Cloud (financials, sentiment)
└─ Market APIs (commodities, economics)
        ↓
ECS DATA LOADERS
├─ loadpricedaily.py
├─ loadfinancials.py
├─ loadanalystssentiment.py
└─ [18 more loaders]
        ↓
RDS DATABASE (60+ tables)
├─ price_daily, price_weekly, price_monthly
├─ buy_sell_daily (signals)
├─ technical_data_daily (RSI, MACD, etc)
├─ company_profile, analyst_sentiment
└─ [50+ tables]
        ↓
ALGO ORCHESTRATOR (7-phase)
├─ Phase 1: Data freshness check
├─ Phase 2: Circuit breakers
├─ Phase 3: Position monitoring
├─ Phase 4: Exit execution
├─ Phase 5: Signal generation
├─ Phase 6: Entry execution (Alpaca)
└─ Phase 7: Reconciliation
        ↓
ALPACA (Paper Trading)
└─ Trade execution, position tracking
        ↓
API LAMBDA (30+ endpoints)
├─ /api/portfolio
├─ /api/trades
├─ /api/signals
├─ /api/market
└─ [26 more]
        ↓
FRONTEND (React + Vite)
├─ Dashboard
├─ Portfolio
├─ Trading Signals
└─ Market Overview
```

---

## Execution Order

### Phase 1: Local Testing (THIS WEEK)
1. [ ] `docker-compose up -d` → verify 60+ tables
2. [ ] `npm start` → test API endpoints
3. [ ] `python3 algo_run_daily.py` → test algo
4. [ ] `python3 loadpricedaily.py` → test data loading
5. [ ] Frontend loads without errors

### Phase 2: AWS Infrastructure (NEXT)
1. [ ] `gh workflow run deploy-all-infrastructure.yml`
2. [ ] Core infrastructure deployed (VPC, ECR)
3. [ ] Data infrastructure deployed (RDS)
4. [ ] Schema initialized on RDS ✨
5. [ ] Webapp Lambda deployed
6. [ ] Loaders deployed
7. [ ] Algo orchestrator deployed

### Phase 3: Data + Integration (AFTER)
1. [ ] Load initial data (symbols, prices, financials)
2. [ ] Run integration tests (API, algo, loaders)
3. [ ] Verify 30+ endpoints work
4. [ ] Verify algo can execute
5. [ ] Monitor CloudWatch logs

### Phase 4: Production Hardening (LATER)
1. [ ] Performance testing
2. [ ] Security audit
3. [ ] Cost optimization
4. [ ] Production deployments

---

## GitHub Secrets Required

```
AWS_ACCESS_KEY_ID           (for deployments)
AWS_SECRET_ACCESS_KEY
AWS_ACCOUNT_ID
RDS_PASSWORD                (for schema init)
ALPACA_API_KEY              (for live data)
ALPACA_SECRET_KEY
SLACK_WEBHOOK_URL           (optional notifications)
```

---

## Success Criteria

✅ Local:
- [ ] Docker Compose brings up DB with 60+ tables
- [ ] API works on localhost:3001
- [ ] Algo runs without errors
- [ ] Data loaders populate data
- [ ] Frontend loads

✅ AWS:
- [ ] All stacks deployed (CloudFormation)
- [ ] RDS has 60+ tables
- [ ] Lambda APIs respond
- [ ] Algo scheduled execution works
- [ ] Data loaders run on schedule
- [ ] No "relation does not exist" errors

✅ Integration:
- [ ] API endpoints work (30+)
- [ ] Portfolio management works
- [ ] Trading works
- [ ] Signals display correctly
- [ ] Frontend loads and functions

---

## Next Actions

1. **Review this plan** - Do you agree with the flow?
2. **Create missing workflows:**
   - `populate-initial-data.yml`
   - `ci-integration-tests.yml`
   - Update `deploy-all-infrastructure.yml`
3. **Test locally** - Verify docker-compose setup
4. **Deploy to AWS** - Run GitHub Actions workflows
5. **Run integration tests** - Verify everything works

Everything stays IaC + GitHub Actions. No manual interventions. ✅

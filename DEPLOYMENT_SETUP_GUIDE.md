# AWS Deployment Setup Guide - CRITICAL ACTIONS REQUIRED

**Status:** 6 critical issues blocking deployment. Follow this guide step-by-step.

---

## STEP 1: Configure GitHub Secrets (5 minutes)
**Required before anything else can work**

### What to do:
1. Go to GitHub: https://github.com/argie33/algo
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret" and add these 5 secrets:

| Secret Name | Value |
|------------|-------|
| `AWS_ACCOUNT_ID` | `626216981288` |
| `AWS_ACCESS_KEY_ID` | Get from your AWS IAM console |
| `AWS_SECRET_ACCESS_KEY` | Get from your AWS IAM console |
| `RDS_USERNAME` | `stocks` |
| `RDS_PASSWORD` | `bed0elAn` |

**⚠️ SECURITY WARNING:** These secrets are sensitive. Never commit them to git. Use GitHub Secrets only.

### Why:
- Bootstrap workflow needs static AWS keys to create the OIDC provider
- Deploy workflows need AWS_ACCOUNT_ID to assume the role
- Loaders need RDS_USERNAME and RDS_PASSWORD to connect to database

---

## STEP 2: Trigger Bootstrap Workflow (15 minutes)
**This creates OIDC provider and deploy role**

### What to do:
1. Go to GitHub Actions: https://github.com/argie33/algo/actions
2. Click "Bootstrap OIDC Provider & Deploy Role" workflow
3. Click "Run workflow" → "Run workflow"
4. Wait for it to complete (should show green ✅)

### What it does:
- Creates AWS::IAM::OIDCProvider (allows GitHub to authenticate to AWS)
- Creates GitHubActionsDeployRole (allows GitHub to assume role and deploy)
- Exports outputs for other workflows to use

### Verify success:
```bash
# After workflow completes, check in AWS console:
# IAM → Identity Providers → token.actions.githubusercontent.com ✅
# IAM → Roles → GitHubActionsDeployRole ✅
```

---

## STEP 3: Deploy Infrastructure (30 minutes)
**This creates RDS, ECS, Secrets Manager, etc.**

### What to do:
1. Go to GitHub Actions: https://github.com/argie33/algo/actions
2. Click "Deploy Infrastructure (RDS/ECS/Secrets)" workflow
3. Click "Run workflow" → "Run workflow"
4. Wait for it to complete (10-15 minutes for RDS, 5-10 minutes for ECS)

### Verify success:
```bash
# Check RDS is created:
aws rds describe-db-instances --db-instance-identifier stocks \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address]' --output table

# Check ECS cluster exists:
aws ecs list-clusters --query 'clusterArns' --output table

# Check security groups allow access:
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=stocks-ecs-sg" \
  --query 'SecurityGroups[0].IpPermissions' --output table
```

---

## STEP 4: Complete Batch 5 Data Loading (30 minutes)
**Only 83% loaded locally - need to get to 100%**

### Current status:
- quarterly_income_statement: 22,333 / 25,000 (89%)
- annual_income_statement: 19,317 / 25,000 (77%)
- quarterly_balance_sheet: 23,114 / 25,000 (92%)
- annual_balance_sheet: 19,303 / 25,000 (77%)
- quarterly_cash_flow: 21,599 / 25,000 (86%)
- annual_cash_flow: 19,193 / 25,000 (77%)

### What to do (locally):
```bash
# Run Batch 5 loaders to completion
python loadquarterlyincomestatement.py
python loadannualincomestatement.py
python loadquarterlybalancesheet.py
python loadannualbalancesheet.py
python loadquarterlycashflow.py
python loadannualcashflow.py
```

### Verify success:
```bash
# Connect to local database:
psql -h localhost -U stocks -d stocks

# Run this query:
SELECT 
  'quarterly_income_statement' as table_name, COUNT(*) as cnt FROM quarterly_income_statement
UNION ALL SELECT 'annual_income_statement', COUNT(*) FROM annual_income_statement
UNION ALL SELECT 'quarterly_balance_sheet', COUNT(*) FROM quarterly_balance_sheet
UNION ALL SELECT 'annual_balance_sheet', COUNT(*) FROM annual_balance_sheet
UNION ALL SELECT 'quarterly_cash_flow', COUNT(*) FROM quarterly_cash_flow
UNION ALL SELECT 'annual_cash_flow', COUNT(*) FROM annual_cash_flow
ORDER BY table_name;

# All should show ~25,000 rows
```

---

## STEP 5: Test Full System (10 minutes)

### Local testing:
```bash
# Terminal 1: Start API server
node webapp/lambda/index.js

# Terminal 2: Start frontend
cd webapp/frontend && npm run dev

# Terminal 3: Run health check
curl http://localhost:3001/api/health
curl http://localhost:3001/api/diagnostics
```

### AWS testing:
```bash
# After infrastructure deployed, trigger a loader in AWS:
# GitHub Actions → "Run Batch 5 Loader - Phase 2" → Run workflow

# Then check:
# CloudWatch Logs → /ecs/loadquarterlyincomestatement
# (should show PARALLEL execution with 5 workers)
```

---

## STEP 6: Add Execution Metrics (1 hour)
**Optional - for performance tracking**

### Create metrics table:
```sql
CREATE TABLE loader_execution_metrics (
  id SERIAL PRIMARY KEY,
  loader_name VARCHAR(255),
  start_time TIMESTAMP DEFAULT NOW(),
  end_time TIMESTAMP,
  duration_seconds NUMERIC,
  rows_inserted INT,
  symbols_processed INT,
  speedup_vs_baseline NUMERIC,
  status VARCHAR(50),
  error_message TEXT
);
```

### Update loaders to log metrics:
- See `loadbuyselldaily.py` for example implementation
- Add logging to start, progress, and completion
- Write metrics to table at end

---

## Troubleshooting

### Bootstrap workflow fails:
- ❌ "ValidationError: User is not authorized"
  - **Fix:** Add AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY secrets
  
- ❌ "ThrottlingException"
  - **Fix:** Wait 30 seconds and retry

### Deploy infrastructure fails:
- ❌ "RoleSessionName must match"
  - **Fix:** Update template to use correct role name
  
- ❌ "Security group not found"
  - **Fix:** Template will auto-create, just retry

### Batch 5 loaders don't complete:
- ❌ "Connection refused"
  - **Fix:** Check `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` in `.env.local`
  
- ❌ "Table does not exist"
  - **Fix:** Run all Phase 1-3 loaders first

---

## What We're Building

```
GitHub Actions (with OIDC)
        ↓
AWS CloudFormation Deploy Role
        ↓
┌───────────────────────────┐
│  RDS PostgreSQL           │  ← Database (20GB initially, scaling to 100GB)
│  (stocks-prod-db)         │
└─────────┬─────────────────┘
          │
          ├→ quarterly_income_statement (25K rows)
          ├→ annual_income_statement (25K rows)
          ├→ quarterly_balance_sheet (25K rows)
          ├→ annual_balance_sheet (25K rows)
          ├→ quarterly_cash_flow (25K rows)
          └→ annual_cash_flow (25K rows)
          
      ECS Cluster
      (stock-analytics-cluster)
          ↓
      ECS Tasks (loaders)
      - 5 parallel workers per loader
      - Auto-scales based on load
      - Logs to CloudWatch
```

---

## Timeline

- **Step 1** (Secrets): 5 minutes
- **Step 2** (Bootstrap): 5-10 minutes
- **Step 3** (Infrastructure): 20-30 minutes
- **Step 4** (Batch 5): 30-45 minutes
- **Step 5** (Testing): 10 minutes
- **Step 6** (Metrics): 1 hour

**Total: ~2 hours**

---

## Success Criteria

✅ GitHub Secrets configured  
✅ Bootstrap workflow completed  
✅ RDS instance created and accessible  
✅ ECS cluster created  
✅ Batch 5 loaders at 100% (150,000 rows)  
✅ API health check returns 200  
✅ Frontend loads data from API  
✅ Loaders can run in parallel in AWS  

---

## Questions?

If any step fails, check:
1. AWS CloudFormation Events (for infrastructure issues)
2. GitHub Actions logs (for workflow issues)
3. CloudWatch Logs (for runtime issues)
4. `/api/diagnostics` endpoint (for data issues)

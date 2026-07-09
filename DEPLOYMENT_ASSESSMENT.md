# AWS Deployment Assessment & Action Plan

**Generated:** 2026-07-08
**Status:** Infrastructure Partially Deployed - Ready for Complete Migration

---

## CURRENT STATE

### Local Database (PostgreSQL)
- **Host:** localhost:5432 (::1)
- **Database:** stocks
- **Tables:** 184 total
- **Data:** 
  - stock_scores: 10,594 rows
  - algo_positions: Active positions stored
  - algo_trades: Trading history
  - algo_signals: Generated signals
  - And 180+ other operational tables
- **Status:** Ready for export

### AWS Infrastructure
- **RDS Instance:** algo-db (AVAILABLE)
  - Status: PostgreSQL 14.22 running
  - Storage: 61 GB allocated
  - Endpoint: algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com:5432
  - Database: stocks (empty - needs migration)
  - Multi-AZ: Disabled (single region)

- **AWS Resources (Deployed via Terraform):**
  - Step Functions Pipelines: 5 deployed
    - algo-computed-metrics-pipeline-dev
    - algo-eod-pipeline-dev
    - algo-financial-data-pipeline-dev
    - algo-morning-prep-pipeline-dev
    - algo-reference-data-pipeline-dev
  - Terraform State: Stored in S3 (stocks-terraform-state)
  - State Lock: DynamoDB table configured
  
- **Missing/Unable to Verify (Due to IAM Restrictions):**
  - Lambda functions (algo-api-dev, algo-orchestrator-dev)
  - API Gateway endpoints
  - ECR repositories
  - CloudFront distributions
  - Cognito resources
  - DynamoDB tables (phase1_cache, orchestrator_state, loader_config, etc.)

### IAM Permission Issue
- **Current User:** algo-developer
- **Issue:** Limited permissions - cannot read many AWS resources
  - Cannot list Lambda functions
  - Cannot describe DynamoDB tables
  - Cannot read S3 bucket policies
  - Cannot describe VPC attributes
  - Cannot read Secrets Manager
  - Cannot list ECR repositories
- **Impact:** Terraform plan/apply fails locally
- **Solution:** Use GitHub Actions (has elevated permissions via OIDC role)

---

## WHAT NEEDS TO BE DEPLOYED

### 1. Database Schema & Data Migration
**Current State:** Local database has schema but AWS RDS is empty

**Action Required:**
```bash
# Export local schema and data
pg_dump -h localhost -U stocks -d stocks --schema-only > schema.sql
pg_dump -h localhost -U stocks -d stocks --data-only > data.sql

# Import to AWS RDS (requires network connectivity to RDS)
# This step is handled by GitHub Actions deploy workflow
```

**Who does it:** GitHub Actions (deploy-all-infrastructure.yml)
- Step: "Setup Terraform Backend" → runs terraform init
- Step: "Build psycopg2 Lambda layer" → prepares db-migration Lambda
- Step: "Deploy db-init Lambda" → creates schema on AWS RDS
- Step: "Invoke db-init Lambda" → runs migrations

### 2. Lambda Functions

**Missing/Needing Deployment:**

| Function | Status | Built | Deployed | Role |
|----------|--------|-------|----------|------|
| algo-orchestrator-dev | Missing | ✓ (ZIP created) | ✗ | Orchestrator for 2x daily execution |
| algo-api-dev | Missing | ✓ (ZIP created) | ✗ | REST API for dashboard |
| algo-db-init-dev | Missing | ✓ (ZIP created) | ✗ | Schema initialization |
| loader-failure-handler | Missing | ✓ (ZIP created) | ✗ | Error handling for Step Functions |
| data-freshness-monitor | Missing | ✓ (ZIP created) | ✗ | Data quality monitoring |
| circuit-breaker | Missing | ✓ (ZIP created) | ✗ | Intraday trading halts (F-02) |
| aaii-sentiment-loader | Missing | ✓ (ZIP created) | ✗ | Reference data loader |

**Action:** Deploy via GitHub Actions
- Step: "Build Algo Lambda" → builds all Lambda code
- Step: "Deploy Algo Lambda" → pushes to AWS
- Step: "Deploy API Lambda" → pushes to AWS

### 3. EventBridge Scheduler Rules

**Status:** Not verified (IAM restrictions)
**Expected State:** Should be configured for 2x daily execution
- 9:30 AM ET: Morning run (market open)
- 5:30 PM ET: Evening run (signal prep)

### 4. ECS Docker Images

**Status:** Not deployed
**Action:** GitHub Actions workflow will:
1. Build Docker image for data loaders
2. Push to ECR
3. Register task definitions
4. Start ECS tasks

### 5. API Gateway & CloudFront

**Status:** Likely deployed but unable to verify
**Configured by:** Terraform (deploy-all-infrastructure.yml)

### 6. Cognito User Pool & Authentication

**Status:** Likely deployed but unable to verify
**Configured by:** Terraform (cognito.tf module)

---

## DEPLOYMENT PATH FORWARD

### Option 1: Full Deployment via GitHub Actions (RECOMMENDED)
**Why:** Has all necessary IAM permissions, handles all steps automatically

**Steps:**
```bash
# 1. Ensure all code is committed and pushed
git status
git push origin main

# 2. Trigger deployment workflow
# Go to: https://github.com/argie33/algo/actions
# Click: deploy-all-infrastructure.yml
# Click: Run workflow
# Select: main branch
# Leave inputs as default (false = use all steps)
```

**Timeline:** 5-10 minutes total
- Bootstrap backend: 1 min
- Terraform plan: 1 min
- Terraform apply: 2-3 min
- Build images: 2 min
- Deploy Lambdas: 1 min
- Initialize database: 1-2 min

**What it does automatically:**
1. ✓ Terraform init with proper permissions
2. ✓ Terraform plan (shows what will change)
3. ✓ Terraform apply (creates all AWS resources)
4. ✓ Build all Lambda functions
5. ✓ Deploy Lambda functions to AWS
6. ✓ Build and push Docker images to ECR
7. ✓ Initialize RDS schema (via db-init Lambda)
8. ✓ Set up Cognito users and admin group
9. ✓ Configure API Gateway CORS
10. ✓ Save dashboard credentials to Secrets Manager

### Option 2: Escalate Local IAM Permissions
**Why:** Allows local Terraform apply
**How:** AWS admin adds permissions to algo-developer user

**Required Permissions:**
- dynamodb:*
- ec2:Describe*
- s3:GetBucketPolicy
- events:DescribeRule
- iam:GetRole
- secretsmanager:GetSecretValue
- secretsmanager:ListSecrets
- lambda:ListFunctions

**After:** Can run locally
```bash
cd terraform
terraform plan -lock=false
terraform apply -lock=false
```

**Downside:** Still requires manual deployment of Lambda functions and images

### Option 3: Local Terraform + Manual AWS Deployment
**Not recommended:** Complex, error-prone, requires multiple manual steps

---

## CRITICAL DECISION: DATA MIGRATION STRATEGY

### Current Situation
- Local database: 184 tables, 10,594+ rows of data
- AWS RDS: Empty, waiting for schema

### Challenge
AWS RDS is in a **private VPC subnet** (not publicly accessible)
- Connection times out from external networks
- Cannot use pg_dump/psql from local machine directly

### Solution
**Use GitHub Actions deployment workflow:**
1. Lambda function (db-init) runs inside VPC
2. Can connect to RDS directly
3. Applies schema from source control
4. Initializes empty database

**Data Migration Strategy:**

**Phase 1 (Minimal - get system running):**
1. Terraform applies schema via db-init Lambda
2. AWS loaders start populating fresh data via EventBridge Scheduler
3. System runs on fresh AWS data (not local copy)
4. **Takes 6-12 hours** for data pipelines to populate all tables

**Phase 2 (Optional - preserve historical data):**
1. Export key historical data from local (trades, positions, snapshots)
2. Use Lambda or API to import into AWS RDS
3. Backfill decision metrics, P&L calculations

**Recommendation:** Phase 1 only
- Simpler deployment
- AWS loaders are designed to populate data
- Historical local data less critical than live forward data
- System can verify data freshness as it loads

---

## STEP-BY-STEP DEPLOYMENT INSTRUCTIONS

### PREREQUISITES
- [ ] All code committed to main branch
- [ ] GitHub repository has write access
- [ ] AWS account has deployment role configured

### EXECUTION

#### Step 1: Commit Code (if not already done)
```bash
git status
git add -A
git commit -m "Deploy: Full AWS infrastructure with 2x daily orchestration"
git push origin main
```

#### Step 2: Trigger Deployment
```bash
# Option A: Via GitHub CLI
gh workflow run deploy-all-infrastructure.yml -r main

# Option B: Via Web
# Navigate to: https://github.com/argie33/algo/actions
# Select: deploy-all-infrastructure.yml
# Click: Run workflow
# Leave defaults (all steps enabled)
```

#### Step 3: Monitor Deployment
```bash
# Option A: GitHub CLI
gh run watch

# Option B: Web dashboard
# https://github.com/argie33/algo/actions/runs/{RUN_ID}
# Watch logs in real time
```

#### Step 4: Verify Deployment
After workflow completes (success = green checkmark):

```bash
# Check Lambda functions deployed
aws lambda get-function --function-name algo-orchestrator-dev --region us-east-1

# Check RDS schema initialized
# Dashboard will verify automatically on first load

# Check data freshness
# Wait 2-4 hours for loaders to populate tables

# Verify dashboard works
# Dashboard will auto-connect to AWS API Gateway
```

---

## POST-DEPLOYMENT VERIFICATION

### Immediate Checks (5 minutes after deploy)
1. GitHub Actions shows green checkmark
2. All Terraform outputs are visible
3. No error messages in workflow logs

### Short-term Checks (30 minutes)
1. RDS database accessible: `terraform output rds_endpoint`
2. Lambda functions running: `aws lambda get-function --function-name algo-orchestrator-dev`
3. API Gateway deployed: Check Terraform outputs

### Medium-term Checks (2-4 hours)
1. Data loaders start running (EventBridge scheduler triggers)
2. Tables begin populating with fresh data
3. Dashboard shows updated signals and positions

### Full System Verification
1. Orchestrator runs at scheduled times (9:30 AM, 5:30 PM ET)
2. Trades execute in paper trading mode
3. Dashboard shows live data
4. Portfolio snapshots created after each run
5. Circuit breakers activate if needed

---

## ROLLBACK/TROUBLESHOOTING

### If Deployment Fails

**Check Workflow Logs:**
```bash
gh run list -w deploy-all-infrastructure.yml --limit 1
gh run view {RUN_ID} --log
```

**Common Issues:**

| Issue | Cause | Fix |
|-------|-------|-----|
| "Lambda: No such file" | ZIP not built | Rebuild Lambda ZIPs, commit, retry |
| "Terraform: Access Denied" | IAM permissions | AWS admin checks role policy |
| "db-init timeout" | RDS not ready | Wait 5 min, retry workflow |
| "CORS errors" | API Gateway not configured | Workflow configures automatically, check logs |

### If RDS Needs Reset
```bash
# AWS Console: RDS → Snapshots → Create snapshot
# Then restore from snapshot if needed
```

---

## NEXT STEPS AFTER SUCCESSFUL DEPLOYMENT

### 1. Configure Alpaca Credentials
```bash
# GitHub Secrets already configured
# AWS Secrets Manager will auto-populate
aws secretsmanager get-secret-value --secret-id algo/alpaca
```

### 2. Monitor First Orchestrator Run
- Check CloudWatch logs: `/aws/lambda/algo-orchestrator-dev`
- Expected: All 9 phases complete successfully

### 3. Verify Data Pipelines
```bash
# Check data freshness
SELECT MAX(updated_at) FROM stock_scores;  # Should be today
SELECT MAX(created_at) FROM algo_trades;   # Should be recent
```

### 4. Test API Endpoints
```bash
# Get API endpoint
API_URL=$(terraform -chdir=terraform output -raw api_gateway_endpoint)
curl $API_URL/api/health
curl $API_URL/api/scores
```

### 5. Access Dashboard
Dashboard will auto-connect to deployed API Gateway endpoint

---

## KEY DECISIONS MADE

1. **2x Daily Execution:** Morning (9:30 AM) + Evening (5:30 PM)
   - Matches trading hours
   - Reduces operational costs
   - Can expand to 4x daily later

2. **Paper Trading Mode:** Test live but don't trade with real money
   - Full system verification
   - No financial risk

3. **Database Strategy:** AWS data loaders provide fresh data
   - No need to migrate 6+ months of historical data
   - Forward-looking system optimized

4. **GitHub Actions Deployment:** Required due to IAM restrictions
   - Cannot deploy locally without elevated permissions
   - GitHub Actions has OIDC-based role with necessary permissions

---

## DEPLOYMENT CHECKLIST

- [ ] Code committed to main branch
- [ ] GitHub Actions workflow triggered
- [ ] Workflow completes with green checkmark
- [ ] Terraform outputs captured (Lambda names, API Gateway, CloudFront)
- [ ] RDS database schema initialized
- [ ] Lambda functions deployed and testable
- [ ] API Gateway CORS configured
- [ ] Cognito user created (Terraform step)
- [ ] Dashboard credentials stored in Secrets Manager
- [ ] First orchestrator run scheduled (EventBridge)
- [ ] Data loaders running (initial data load in progress)
- [ ] Dashboard accessible and showing data
- [ ] Trades executing in paper mode

---

## ESTIMATED TIMELINE

- **Total Deploy Time:** 10-15 minutes
- **Data Population:** 6-12 hours (loaders run on schedule)
- **Full System Ready:** 24 hours (one full orchestrator cycle)
- **Monitoring:** Ongoing (CloudWatch alarms configured)

---

**Status:** READY FOR DEPLOYMENT

**Recommended Action:** Execute Option 1 (GitHub Actions deployment)

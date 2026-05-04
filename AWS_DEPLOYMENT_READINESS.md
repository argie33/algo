# AWS Data Loading Deployment - Readiness Checklist

**Last Updated:** 2026-05-04  
**Status:** READY FOR DEPLOYMENT (GitHub Actions configured)

---

## What's Been Built

### Local Infrastructure (Complete)
- [x] OptimalLoader base class with watermark incremental loading
- [x] 65+ loader Python scripts (all migrated to OptimalLoader pattern)
- [x] EOD pipeline orchestration (`run_eod_loaders.sh`)
- [x] Data patrol and remediation engines
- [x] .env.local with database credentials

### AWS Infrastructure (Complete)
- [x] 80+ Docker images (one per loader)
- [x] CloudFormation templates for ECS + EventBridge
- [x] GitHub Actions CI/CD pipeline with phased deployment
- [x] Phase E: DynamoDB for incremental loading state
- [x] Phase D: Step Functions for orchestration

### GitHub Actions Deployment Pipeline (Complete)
- [x] Detect-changes job (identifies modified loaders)
- [x] Build Docker images and push to ECR
- [x] Deploy ECS task definitions
- [x] Deploy Phase E infrastructure (DynamoDB)
- [x] Deploy Phase D infrastructure (Step Functions)
- [x] Deployment summary reporting

---

## What's Required for Live Deployment

### 1. AWS Account Setup (REQUIRED)

**GitHub Secrets Required** (configure in repo settings):
```
AWS_ACCOUNT_ID             (your 12-digit account number)
AWS_ACCESS_KEY_ID          (IAM user key for bootstrap)
AWS_SECRET_ACCESS_KEY      (IAM user secret for bootstrap)
FRED_API_KEY               (Federal Reserve data API key)
APCA_API_KEY_ID            (Alpaca trading API key)
APCA_API_SECRET_KEY        (Alpaca trading secret)
```

**AWS IAM Role Required:**
- Role name: `GitHubActionsDeployRole`
- Trust policy: GitHub OIDC provider (set up by bootstrap workflow)
- Permissions: CloudFormation, ECR, ECS, Lambda, DynamoDB, Secrets Manager

**AWS Resources Required:**
- ECR repository: `stocks-app-registry`
- ECS cluster: `stocks-cluster`
- RDS instance: `stocks` (already exists, verified 2026-05-04)
- VPC with private subnets for ECS tasks

### 2. CloudFormation Templates to Deploy

These run automatically via GitHub Actions:

| Template | Phase | Purpose |
|----------|-------|---------|
| `template-bootstrap.yml` | Bootstrap | Sets up OIDC + IAM role |
| `template-core.yml` | Core | VPC, IAM, RDS, CloudWatch |
| `template-app-stocks.yml` | App | RDS configuration |
| `template-app-ecs-tasks.yml` | Phase E | ECS task definitions + CloudWatch logs |
| `template-eventbridge-scheduling.yml` | Phase E | EventBridge rules for scheduling |
| `template-step-functions.yml` | Phase D | Step Functions state machine |

---

## Deployment Flow (GitHub Actions)

```
1. Code Push to main
   ↓
2. detect-changes job
   - Identify changed loaders
   - Create build matrix
   ↓
3. deploy-infrastructure job (NOW ENABLED)
   - Deploy core CloudFormation stack
   ↓
4. execute-loaders jobs (parallel batches, max 5)
   - Build Docker image for changed loader
   - Push to ECR
   - Deploy ECS task definition
   ↓
5. deploy-phase-e-infrastructure
   - Deploy DynamoDB stack
   - Deploy EventBridge rules
   ↓
6. deploy-phase-d-step-functions
   - Deploy Step Functions orchestrator
   ↓
7. deployment-summary
   - Report final status
```

**Total deployment time:** 20-30 minutes

---

## How to Trigger Deployment

### Option 1: Automatic (on code push to main)
```bash
git add .
git commit -m "Deploy loaders to AWS"
git push origin main
# GitHub Actions runs automatically
```

### Option 2: Manual trigger
```bash
# Via GitHub UI:
# 1. Go to Actions tab
# 2. Select "Data Loaders Pipeline"
# 3. Click "Run workflow"
# 4. Select loaders (e.g., "pricedaily,buyselldaily")
# 5. Click "Run workflow"
```

### Option 3: Repository dispatch
```bash
# From CLI (if configured):
gh workflow run deploy-app-stocks.yml \
  -f loaders="pricedaily,buyselldaily" \
  -f environment=prod
```

---

## Data Loading in AWS

### EventBridge Scheduling (Automatic)
Once deployed, loaders run on schedule:

```
Daily @ 5:30 PM ET (22:30 UTC):
  - load_eod_bulk.py (prices)
  - loadtechnicalsdaily.py (technical indicators)
  - loadbuyselldaily.py (buy/sell signals)
  - load_algo_metrics_daily.py (computed metrics)
  - algo_orchestrator.py (trading decisions)

Weekly (Saturday 8 AM ET):
  - Price aggregations (weekly/monthly)
  - Sentiment scores
  - Analyst ratings

Monthly (1st of month):
  - Growth metrics
  - Fundamental statements
```

### Manual Execution in AWS
```bash
# Trigger a specific loader via AWS CLI
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition loadpricedaily:1 \
  --launch-type EC2
```

---

## Verification Steps

### 1. Verify GitHub Actions
```bash
# Check workflow status
gh workflow view "Data Loaders Pipeline"

# View recent runs
gh run list --workflow=deploy-app-stocks.yml --limit 5
```

### 2. Verify AWS Deployment
```bash
# Check CloudFormation stacks
aws cloudformation describe-stacks \
  --region us-east-1 \
  --query 'Stacks[?StackStatus!=`DELETE_COMPLETE`].[StackName,StackStatus]' \
  --output table

# Check ECS task definitions
aws ecs list-task-definitions \
  --family-prefix load \
  --region us-east-1

# Check ECR images
aws ecr list-images \
  --repository-name stocks-app-registry \
  --region us-east-1
```

### 3. Verify Data Loading
```bash
# SSH into RDS and check latest data
psql -h <RDS_HOST> -U stocks -d stocks -c \
  "SELECT MAX(date) FROM price_daily;"

# Check EventBridge rules
aws events list-rules \
  --name-prefix daily \
  --region us-east-1
```

---

## Current Data State (as of 2026-05-04)

| Table | Latest Data | Row Count |
|-------|-------------|-----------|
| price_daily | 2026-05-01 | 21.7M |
| buy_sell_daily | 2026-05-01 | 823K |
| technical_data_daily | 2026-05-01 | 19.1M |

**Last local EOD load:** 2026-05-01 (via run_eod_loaders.sh)  
**Next AWS automated load:** 2026-05-06 at 5:30 PM ET (after next market close)

---

## Troubleshooting

### GitHub Actions workflow fails
1. Check `.github/workflows/deploy-app-stocks.yml` for syntax errors
2. Verify GitHub Secrets are set correctly
3. Check workflow logs for specific error
4. Common issues:
   - Missing AWS_ACCOUNT_ID secret
   - IAM role doesn't have required permissions
   - ECR repository doesn't exist

### CloudFormation stack deployment fails
1. Check AWS CloudFormation console for stack events
2. Look for validation errors in template
3. Verify RDS credentials in Secrets Manager
4. Check VPC/subnet configuration

### Loader doesn't execute in ECS
1. Verify ECS task definition has correct image URI
2. Check ECS task logs in CloudWatch
3. Verify RDS security group allows ECS subnet
4. Confirm database credentials in AWS Secrets Manager

### Data not loading after scheduled run
1. Check EventBridge rule is enabled
2. Verify Step Functions execution status
3. Check ECS task CloudWatch logs
4. Confirm RDS connection and permissions

---

## Next Steps

1. **Configure GitHub Secrets** (if not already done)
   - Add AWS_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
   - Add FRED_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY

2. **Run Bootstrap Workflow** (one-time setup)
   - Triggers when any code is pushed (already configured)
   - Sets up OIDC provider and IAM role

3. **Push Workflow Fix** (DONE - removed `&& false`)
   - infrastructure job is now enabled
   - Next push will trigger full deployment

4. **Monitor First Deployment**
   - Watch GitHub Actions for success
   - Verify CloudFormation stacks in AWS
   - Check ECS task definitions
   - Confirm EventBridge rules

5. **Schedule Manual Test Load** (optional)
   - Manually trigger a loader via GitHub Actions
   - Verify data appears in RDS
   - Check CloudWatch logs for success

---

## Cost Implications

**Monthly cost estimate (post-optimization):**
- ECS on-demand: $80-120
- RDS (existing): $200-300
- S3 staging: $5-10
- Lambda (infrequent): $0-5
- **Total: ~$300-400/month** (vs $1,300 before optimization)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│  GitHub Commit                                          │
│  (push to main)                                         │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions CI/CD Pipeline                          │
│  - Detect changes                                       │
│  - Build Docker images                                  │
│  - Push to ECR                                          │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  AWS CloudFormation                                     │
│  - Deploy ECS task definitions                          │
│  - Deploy EventBridge rules                             │
│  - Deploy Step Functions                                │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  EventBridge Scheduler                                  │
│  (runs 5:30 PM ET daily)                                │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  ECS Tasks (Docker containers)                          │
│  - loadpricedaily                                       │
│  - loadbuyselldaily                                     │
│  - loadtechnicalsdaily                                  │
│  - ... (all loaders)                                    │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│  RDS PostgreSQL                                         │
│  (data insertion via optimized loaders)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Done ✓

- [x] OptimalLoader pattern applied to all loaders
- [x] Docker images created for all loaders
- [x] GitHub Actions pipeline configured
- [x] CloudFormation templates created
- [x] Infrastructure deployment job enabled
- [x] Documentation complete

**Status:** Ready to deploy. Push code to trigger GitHub Actions.

# AWS Deployment - Step-by-Step Checklist

## Current Status
```
❌ Bootstrap Stack: NOT DEPLOYED
❌ Infrastructure: NOT DEPLOYED
❌ Data Loaders: NOT EXECUTED
✅ Application Code: READY (all loaders syntax-validated)
✅ GitHub Actions: CONFIGURED
```

---

## Prerequisites Needed

### What You Have
- ✅ GitHub repository with workflows configured
- ✅ AWS Account (account ID: 626216981288)
- ✅ All 39 loaders ready to go
- ✅ CloudFormation templates ready
- ✅ Docker images prepared

### What You Need
1. **AWS Access Key ID** (from your AWS IAM user)
2. **AWS Secret Access Key** (from your AWS IAM user)
3. **GitHub repository** (to add secrets to)

---

## Deployment Steps

### STEP 1: Add AWS Credentials to GitHub Secrets
```bash
1. Go to: https://github.com/YOUR_ORG/YOUR_REPO/settings/secrets/actions
2. Click "New repository secret"
3. Add two secrets:
   - Name: AWS_ACCESS_KEY_ID
     Value: (your AWS access key)
   - Name: AWS_SECRET_ACCESS_KEY
     Value: (your AWS secret key)
   - Name: AWS_ACCOUNT_ID
     Value: 626216981288
   - Name: FRED_API_KEY
     Value: (your FRED API key if you have one)
```

### STEP 2: Trigger Bootstrap Stack Deployment
```bash
# Option A: Via GitHub UI
1. Go to Actions → "Bootstrap OIDC Provider & Deploy Role"
2. Click "Run workflow" → "Run workflow"
3. Wait ~2 minutes for completion
4. Check workflow logs for success

# Option B: Via Git commit
git push origin main
# Workflow will auto-trigger
```

**What It Does:**
- Creates OIDC provider for GitHub Actions federation
- Creates GitHubActionsDeployRole with AdministratorAccess
- Enables future deployments without exposing static credentials

### STEP 3: Deploy Infrastructure (RDS, ECS, etc.)
Once bootstrap completes:
```bash
# Option A: Via GitHub UI
1. Go to Actions → "Deploy Infrastructure"
2. Click "Run workflow" → "Run workflow"
3. Wait ~15-20 minutes for completion

# Option B: Via Git commit (automatic)
git commit -m "trigger: deploy infrastructure"
git push origin main
```

**What It Deploys:**
- VPC with public/private subnets
- RDS PostgreSQL database (stocks database)
- ECS cluster for running data loaders
- CloudWatch monitoring
- Secrets Manager for API keys

**Monitor Progress:**
```bash
# Check AWS CloudFormation in console:
# https://console.aws.amazon.com/cloudformation/home?region=us-east-1

# Or via AWS CLI:
aws cloudformation describe-stacks \
  --stack-name stocks-app-stack \
  --region us-east-1
```

### STEP 4: Run Data Loaders
Once infrastructure is ready:

**Option A: Run Phase 1 (Core Data)**
```bash
# Via GitHub Actions UI:
1. Go to Actions → "Data Loaders Pipeline"
2. Click "Run workflow"
3. Input loaders: "stocksymbols,dailycompanydata,marketindices"
4. Environment: prod
5. Click "Run workflow"
6. Wait ~10 minutes

# Or commit to trigger:
git add load*.py
git commit -m "data: run phase 1 loaders"
git push
```

**Option B: Run Phase 2 (Prices)**
```
loaders: "pricedaily,priceweekly,pricemonthly,etfpricedaily,etfpriceweekly"
```

**Option C: Run Phase 3 (Signals)**
```
loaders: "buyselldaily,buysellweekly,buysellmonthly,buysell_etf_daily,buysell_etf_weekly"
```

**Option D: Run Phase 4-5 (Everything)**
```
Run in separate batches (max 5 loaders per batch):
- Fundamentals: "annualbalancesheet,quarterlybalancesheet,annualincomestatement,quarterlyincomestatement,annualcashflow"
- Earnings: "earningshistory,earningsrevisions,earningssurprise,stockscores,factormetrics"
- Market: "market,econdata,commodities,seasonality,analystsentiment"
```

---

## What Each Workflow Does

### bootstrap-oidc.yml
- **Triggers**: Any push to any branch
- **Uses**: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
- **Creates**: OIDC provider + GitHubActionsDeployRole
- **Runs**: ~2 minutes
- **After**: Subsequent workflows use OIDC (no static keys needed)

### deploy-infrastructure.yml
- **Triggers**: Changes to template-app-stocks.yml or manual trigger
- **Uses**: OIDC role assumption (no static keys)
- **Deploys**: VPC, RDS, ECS, Secrets Manager
- **Runs**: ~15-20 minutes
- **Monitoring**: CloudFormation in AWS console

### deploy-app-stocks.yml
- **Triggers**: Changes to load*.py files or manual trigger
- **Uses**: OIDC role assumption
- **Runs**: Data loader ECS tasks
- **Batch Size**: Max 5 loaders per execution
- **Duration**: Depends on loader complexity (5-30 min per batch)

---

## GitHub Actions Monitoring

### Check Workflow Status
```bash
# SSH into your repo and run:
gh run list --branch main --status completed --limit 10

# Or use GitHub UI:
# Repository → Actions → View all workflows
```

### Check Loader Logs
```bash
# After data loaders complete, check ECS logs:
aws logs get-log-events \
  --log-group-name /ecs/stocks-loader \
  --log-stream-name ecs/stocks-loader/task-id \
  --region us-east-1
```

---

## Troubleshooting

### Bootstrap Fails with "AccessDenied"
**Problem**: IAM user doesn't have CloudFormation permissions
**Solution**: 
```bash
# Verify IAM user has these permissions:
- cloudformation:CreateStack
- cloudformation:UpdateStack
- cloudformation:DescribeStacks
- iam:CreateRole
- iam:CreateOIDCProvider
- iam:AttachRolePolicy
```

### Infrastructure Fails to Deploy
**Problem**: Role or permissions issue
**Solution**:
```bash
# Verify bootstrap completed successfully
# Check CloudFormation console for stocks-oidc-bootstrap stack
# It should be in CREATE_COMPLETE status
```

### Loaders Won't Start
**Problem**: ECS task definition not deployed
**Solution**:
```bash
# Re-run deploy-infrastructure workflow:
# Actions → Deploy Infrastructure → Run workflow
```

### CloudFormation Stack Stuck
**Problem**: Stack in UPDATE_ROLLBACK_COMPLETE
**Solution**:
```bash
# Manually continue stack update:
aws cloudformation continue-update-rollback \
  --stack-name stocks-app-stack \
  --region us-east-1
```

---

## After Deployment

### Verify Everything Works
```bash
# Check API health:
curl http://your-api-url/api/health

# Check database:
aws rds describe-db-instances \
  --db-instance-identifier stocks \
  --region us-east-1

# Check loader data:
aws rds-data execute-statement \
  --resource-arn "arn:aws:rds:us-east-1:626216981288:db:stocks" \
  --database "stocks" \
  --sql "SELECT COUNT(*) FROM stock_symbols"
```

### Monitor Data Loading Progress
```bash
# CloudWatch Logs:
# https://console.aws.amazon.com/cloudwatch/

# Or via CLI:
aws logs tail /ecs/stocks-loader --follow
```

---

## Time Estimates

| Step | Duration | Notes |
|------|----------|-------|
| Bootstrap Stack | 2-3 min | One-time setup |
| Infrastructure Deploy | 15-20 min | RDS database creation takes most time |
| Phase 1 Loaders | 10-15 min | Core metadata (symbols, company data) |
| Phase 2 Loaders | 20-30 min | Price history (large datasets) |
| Phase 3 Loaders | 15-20 min | Trading signals |
| Phase 4 Loaders | 30-40 min | Fundamentals (balance sheets, etc.) |
| Phase 5 Loaders | 20-30 min | Earnings, scores, sentiment |
| **Total** | **~2 hours** | From bootstrap to fully loaded system |

---

## Success Indicators

✅ Bootstrap stack in CREATE_COMPLETE
✅ Infrastructure stack in CREATE_COMPLETE
✅ RDS database accessible
✅ ECS cluster has running tasks
✅ Data appearing in CloudWatch logs
✅ Database queries returning rows
✅ API endpoints responding with data


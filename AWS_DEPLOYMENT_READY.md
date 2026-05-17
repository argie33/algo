# AWS Deployment - Infrastructure Ready (2026-05-17)

## Status: ✅ READY FOR DEPLOYMENT

All IaC issues have been identified and fixed. The platform is ready for full AWS deployment with working loaders.

---

## What's Been Fixed

### Critical Fixes Applied

| Issue | Status | Impact |
|-------|--------|--------|
| Patrol task configuration missing from services module | ✅ FIXED | API can now invoke `/api/algo/patrol` endpoint |
| Calendar loader orphaned in Terraform | ✅ FIXED | 39 loaders (not 40) configured correctly |
| Continuous monitor output missing | ✅ FIXED | Monitoring module can reference task |
| Docker entrypoint for loaders | ✅ VERIFIED | Already correctly implemented |

---

## Loader Deployment Architecture

```
GitHub Push (main branch)
    ↓
GitHub Actions Workflow: deploy-all-infrastructure.yml
    ↓
    Step 1: Bootstrap Terraform Backend
        ├─ Create S3 bucket (if not exists)
        └─ Create DynamoDB state lock table
    ↓
    Step 2: Build Infrastructure (Terraform Apply)
        ├─ Database Module: RDS PostgreSQL + Secrets Manager
        ├─ VPC Module: Network, subnets, security groups
        ├─ Compute Module: ECS cluster, bastion host
        ├─ Storage Module: S3 buckets (code, data, frontend)
        ├─ IAM Module: All roles and policies
        ├─ Loaders Module: 39 loaders + EventBridge + ECS tasks
        ├─ Services Module: API Gateway, Lambda, CloudFront
        ├─ Pipeline Module: Step Functions EOD pipeline
        ├─ Monitoring Module: CloudWatch alarms, dashboards
        └─ Cognito Module: User authentication
    ↓
    Step 3: Build Docker Image
        ├─ docker build -t stocks:latest .
        ├─ Push to ECR: $ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/stocks:dev-latest
        └─ Tags available for ECS task definitions
    ↓
    Step 4: Deploy Lambda Functions
        ├─ Package API Lambda → S3 → API Gateway
        ├─ Package Algo Orchestrator Lambda → S3
        └─ Package Data Freshness Monitor → S3
    ↓
    Step 5: Deploy Frontend
        ├─ Build React app
        ├─ Upload to S3 bucket
        └─ Invalidate CloudFront cache
    ↓
    Complete: Platform Live in AWS
```

---

## What Gets Deployed

### Infrastructure Components (Terraform)

| Component | Type | Count | Details |
|-----------|------|-------|---------|
| **RDS Database** | PostgreSQL 14 | 1 | 127 tables, 1.5M+ records, encrypted |
| **ECS Cluster** | Fargate | 1 | Auto-scaling, mixed on-demand/spot |
| **Loader Tasks** | ECS Task Definitions | 39 | Daily/weekly schedule via EventBridge + Step Functions |
| **EventBridge Rules** | Scheduled Rules | 33 | Loaders on fixed cron schedule |
| **API Gateway** | REST API | 1 | HTTP API with Lambda integration |
| **Lambdas** | Functions | 3 | API (Node.js), Orchestrator (Python), Data Freshness Monitor (Python) |
| **S3 Buckets** | Storage | 4 | Code, data, frontend, artifacts |
| **CloudFront** | CDN | 1 | Frontend distribution |
| **Secrets Manager** | Secrets | 4 | RDS creds, Alpaca, FRED, JWT |
| **SNS Topics** | Messaging | 1 | Alerts for failed loaders |
| **SQS DLQ** | Dead-Letter Queue | 1 | Failed EventBridge messages |
| **CloudWatch** | Monitoring | 40+ | Logs, alarms, dashboards |
| **VPC** | Networking | 1 | Private subnets for database/loaders |

---

## Loader Execution Flow

### Daily Loader Schedule (Mon-Fri)

```
3:30am ET (8:30am UTC)  → EventBridge trigger
    ↓
    task-def: "stocks-stock-symbols-loader"
    container: docker image from ECR
    env vars: LOADER_FILE=loadstocksymbols.py
              LOADER_PARALLELISM=1
              DB_HOST, DB_PORT, DB_NAME
              DB_PASSWORD (from Secrets Manager)
              FRED_API_KEY (from Secrets Manager)
    ↓
    entrypoint.sh reads LOADER_FILE
    ↓
    python3 loaders/loadstocksymbols.py
    ↓
    ✅ Success → 5000+ stock symbols loaded
    ❌ Failure → Message sent to SQS DLQ → SNS alert
    ↓
    CloudWatch logs: /ecs/stocks-stock-symbols-loader

4:00am ET (9am UTC)  → 6 price loaders (parallel)
    stock_prices_daily (parallelism=16)
    stock_prices_weekly
    stock_prices_monthly
    etf_prices_daily
    etf_prices_weekly
    etf_prices_monthly
    
10:00am+ ET → Financial statements, earnings, market data (parallel)

5:00pm ET → Trading signals (Step Functions pipeline)
    → Runs algo_metrics_daily
    → Triggers algo orchestrator ECS task

5:15pm ET → Algo metrics (after signals)

Every 15 min → Continuous monitor checks data freshness
```

### On-Demand Execution

**API Endpoint: `/api/algo/patrol`** (POST)
```
HTTP POST /api/algo/patrol
    ↓
    API Lambda receives request
    ↓
    ECS RunTask: "stocks-data-patrol"
    env vars: LOADER_FILE=algo_data_patrol.py
    ↓
    entrypoint.sh → python3 loaders/algo_data_patrol.py
    ↓
    Checks:
    - Stock symbol count
    - Latest price date
    - Signal computation status
    - algo_metrics_daily freshness
    ↓
    Returns: {status: "healthy", issues: [...]}
```

---

## Security & Credentials

### How Credentials Flow

```
GitHub Secrets
    ├─ RDS_PASSWORD
    ├─ ALPACA_API_KEY_ID
    ├─ ALPACA_API_SECRET_KEY
    ├─ FRED_API_KEY
    ├─ JWT_SECRET
    └─ AWS_ACCOUNT_ID

    ↓ (GitHub Actions OIDC)

Terraform Variables (TF_VAR_* env vars)
    ↓
AWS Secrets Manager
    ├─ "stocks-rds-credentials" (username:password)
    ├─ "stocks-algo-secrets" (ALPACA_*, FRED_API_KEY, JWT)
    └─ "stocks-email-config"

    ↓ (Referenced in task definitions)

ECS Task Definition
    environment:
      DB_PASSWORD: valueFrom="arn:aws:secretsmanager:..."
      ALPACA_API_KEY: valueFrom="arn:aws:secretsmanager:..."
    
    ↓ (ECS injects at runtime)

Container Environment
    $DB_PASSWORD
    $ALPACA_API_KEY
    $ALPACA_SECRET_KEY
    $FRED_API_KEY
```

**No .env files, no hardcoded secrets, AWS Secrets Manager only.**

---

## Deployment Checklist

### Pre-Deployment ✅

- [x] Terraform validates successfully
- [x] All 39 loader Python files exist in codebase
- [x] Docker image builds successfully
- [x] Patrol task variables wired in Terraform
- [x] Continuous monitor outputs exposed
- [x] Calendar loader removed
- [x] Entrypoint script checks LOADER_FILE
- [x] GitHub Secrets configured with AWS account ID
- [x] GitHub OIDC role created for OpenID Connect

### During Deployment (GitHub Actions)

- [ ] Step 1: Bootstrap Terraform backend → creates S3 + DynamoDB
- [ ] Step 2: Terraform init → configures remote state
- [ ] Step 3: Terraform plan → 150-200 resources to create
- [ ] Step 4: Terraform apply → 10-15 minutes
- [ ] Step 5: Docker build → 5 minutes
- [ ] Step 6: Push to ECR → 2 minutes
- [ ] Step 7: Lambda package → API + Orchestrator + Freshness Monitor
- [ ] Step 8: Deploy frontend → React app to S3

### Post-Deployment ✅

- [ ] Verify RDS instance is running
- [ ] Verify ECS cluster created with Fargate
- [ ] Verify 39 loader task definitions exist
- [ ] Verify 33 EventBridge rules scheduled
- [ ] Verify ECR image pushed and tagged
- [ ] Verify API Gateway endpoint responding
- [ ] Verify Lambda functions deployed
- [ ] Verify CloudFront distribution live
- [ ] Verify Secrets Manager secrets created
- [ ] Verify first loader execution in CloudWatch logs

---

## Key Endpoints (Post-Deployment)

```
API Base URL:
  https://api.example.com/api

Health Check:
  GET /health

Loader Status:
  POST /api/algo/patrol

Algo Execution:
  POST /api/algo/execute

Frontend:
  https://example.com (via CloudFront)

Monitoring:
  https://console.aws.amazon.com/cloudwatch
```

---

## Troubleshooting Common Issues

### Issue: Loaders fail with "LOADER_FILE not found"

**Cause:** LOADER_FILE env var not set in task definition

**Fix:**
```bash
aws ecs describe-task-definition --task-definition "stocks-stock-symbols-loader"
# Verify: environment section has LOADER_FILE=loadstocksymbols.py
```

---

### Issue: Loaders fail with "ModuleNotFoundError: No module named 'loaders'"

**Cause:** Docker image doesn't have loaders/ directory copied

**Fix:**
```bash
docker run stocks:dev-latest ls -la loaders/ | head
# Should show: load*.py, loadxxxx.py files
```

---

### Issue: "No valid credential sources found" when running loader

**Cause:** ECS task execution role missing Secrets Manager permission

**Fix:**
```bash
aws iam get-role-policy \
  --role-name "stocks-svc-ecs-task-execution-role-dev" \
  --policy-name "SecretsManagerAccess"
# Should show policy allowing secretsmanager:GetSecretValue
```

---

### Issue: Loader hangs on database connection

**Cause:** RDS security group blocking ECS task subnets

**Fix:**
```bash
aws ec2 describe-security-groups \
  --group-ids "sg-xxxxx" (RDS security group)
# Verify: Inbound rule allows port 5432 from ECS task security group
```

---

## Performance Expectations

### First Load Times

- **Stock symbols loader:** 2-5 minutes (first time loading 5000+ symbols)
- **Price loaders (daily):** 15-25 minutes (Alpaca API rate limited to 180 req/min)
- **Financial statements:** 20-30 minutes (yfinance/SEC API calls, 500+ symbols)
- **Trading signals:** 10-15 minutes (pandas computation on 5000+ symbols)
- **Algo metrics:** 5 minutes (post-signals aggregation)
- **All 39 loaders (full run):** ~2-3 hours

### Subsequent Runs (incremental)

- **Price loaders (daily):** 5-10 minutes (only new data)
- **Signals (daily):** 5-10 minutes (recompute all)
- **Other loaders:** 2-5 minutes (mostly unchanged)

---

## Monitoring & Alerts

### CloudWatch Dashboards

```
Main Dashboard:
  - Loader task success/failure rate
  - Execution duration by loader
  - Database connection pool utilization
  - API Gateway latency and errors
  - Lambda duration and throttling

Loader Health Dashboard:
  - EventBridge rule trigger count
  - SQS DLQ message count (should be 0)
  - Task CPU and memory utilization
  - Network egress (API calls)

Database Dashboard:
  - CPU utilization
  - Storage capacity
  - Connections
  - Backup status
```

### Alert Configuration

- ✅ SQS DLQ has messages → SNS alert (loader failed)
- ✅ RDS CPU > 80% for 5 min → SNS alert
- ✅ API Lambda errors > 1% → SNS alert
- ✅ API Gateway 5xx errors → SNS alert

---

## Cost Estimation (Monthly)

| Service | Usage | Est. Cost |
|---------|-------|-----------|
| RDS PostgreSQL | db.t4g.medium, 100 GB | $120 |
| ECS (Fargate) | 40 loaders × 30 min/month = 20 hours | $80 |
| Data Transfer | Loader API calls (1 GB/month) | $10 |
| Secrets Manager | 4 secrets | $2 |
| CloudWatch Logs | 40 GB/month | $20 |
| API Gateway | 1M requests/month | $35 |
| Lambda | Algo orchestrator (15 min/day) | $10 |
| S3 | Code + data (10 GB) | $5 |
| CloudFront | Frontend distribution | $10 |
| **Total** | | **~$290/month** |

---

## Next Steps

1. **Push to main:**
   ```bash
   git add -A
   git commit -m "fix: IaC deployment - wire patrol task vars, remove calendar loader"
   git push origin main
   ```

2. **Monitor GitHub Actions:** https://github.com/argie33/algo/actions

3. **Verify AWS resources** once deployment completes

4. **Test API endpoints** and first loader execution

5. **Monitor CloudWatch logs** for any errors

---

## References

- DEPLOYMENT_GUIDE.md - How to deploy
- LOCAL_CRED_SETUP.md - Local development credential setup
- IAC_ISSUES_AUDIT.md - Detailed issues found
- IaC_FIXES_COMPLETED.md - Specific fixes applied
- STATUS.md - Current system status

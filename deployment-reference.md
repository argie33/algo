# Deployment Reference

## Quick Start (Master Orchestrator)

Deploy all infrastructure in dependency order:
```bash
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo
```

This automatically:
1. Deploys bootstrap (GitHub OIDC, one-time only)
2. Deploys core (VPC, networking)
3. Deploys app-stocks (RDS, ECS, Secrets)
4. Deploys app-ecs-tasks (39 loader task definitions)
5. Deploys webapp (REST API Lambda)
6. Deploys algo-orchestrator (Trading engine + EventBridge)

**Deployment time:** ~20-30 minutes total

---

## Stack Dependency Chain

```
stocks-bootstrap (one-time, skip if exists)
    ↓
stocks-core (VPC, subnets, ECR, S3)
    ↓
stocks-app-stocks (RDS, ECS cluster, Secrets)
    ├─→ stocks-app-ecs-tasks (ECS task defs for 39 loaders)
    ├─→ stocks-webapp-lambda (REST API)
    └─→ stocks-algo-orchestrator (Algo engine, EventBridge)
```

## Manual Deploy (If Needed)

Deploy individual stacks in order:
```bash
gh workflow run deploy-core.yml
gh workflow run deploy-app-infrastructure.yml
gh workflow run deploy-app-stocks.yml
gh workflow run deploy-webapp.yml
gh workflow run deploy-algo-orchestrator.yml
```

Or from the console:
```bash
cd aws
aws cloudformation deploy --template-file template-core.yml \
  --stack-name stocks-core --region us-east-1 --capabilities CAPABILITY_IAM
```

---

## 6 CloudFormation Templates (What They Create)

### 1. template-bootstrap.yml (One-Time)
**Purpose:** GitHub OIDC provider
**Resources:** IAM role for GitHub Actions
**Deploy:** `gh workflow run bootstrap-oidc.yml`
**Note:** Only run once; skip on subsequent deployments

### 2. template-core.yml
**Purpose:** Foundation networking
**Creates:**
- VPC (10.0.0.0/16)
- 3 public subnets (for NAT, bastion, load balancers)
- 3 private subnets (for RDS, ECS, Lambda)
- 7 VPC endpoints (S3, Secrets Manager, DynamoDB, CloudWatch, EventBridge, SQS, SNS)
- ECR registry (for Docker images)
- S3 buckets (code, templates, logs, frontend, data)

**Exports:** 9 values (VPC ID, subnet IDs, SG IDs, ECR URI)

### 3. template-app-stocks.yml
**Purpose:** Database, cluster, secrets
**Creates:**
- RDS PostgreSQL (db.t3.micro, 61GB storage, 5-day backups)
- ECS cluster (stocks-data-cluster)
- Secrets Manager (DB credentials, Alpaca API keys)
- CloudWatch log groups (7-day retention + S3 archive)
- IAM roles for ECS and Lambda

**Exports:** 8 values (RDS endpoint, cluster ARN, secret ARNs)

### 4. template-app-ecs-tasks.yml
**Purpose:** Data loader task definitions
**Creates:** 39 ECS task definitions
- 18 stock loaders (symbols, daily/weekly/monthly price, scores, signals)
- 18 ETF loaders (SPY, QQQ, IWM versions)
- 3 multi-loader tasks (run all stocks, all ETFs, all at once)

**Each task:** 512 MB memory, 256 CPU units, auto-retries

### 5. template-webapp-lambda.yml
**Purpose:** REST API and frontend
**Creates:**
- Lambda function (Node.js 20, ARM64, SnapStart)
- API Gateway (HTTP API, CORS enabled)
- CloudFront distribution (frontend CDN)
- Cognito user pool (auth)
- IAM execution role

**Endpoints:** `/api/stocks/*`, `/api/signals/*`, `/api/portfolio/*`

### 6. template-algo-orchestrator.yml
**Purpose:** Trading engine
**Creates:**
- Lambda function (Python 3.11, 1GB memory, 5-minute timeout)
- EventBridge Scheduler (daily 5:30pm ET, weekdays only)
- SQS DLQ (for failed executions)
- SNS topic (critical alerts)
- IAM execution role

**Runs:** Every weekday at 5:30pm ET (market close + 30 min)

---

## 23 GitHub Workflows

### Deployment Workflows
- `deploy-all-infrastructure.yml` — Master orchestrator (runs all in order)
- `bootstrap-oidc.yml` — GitHub OIDC (one-time)
- `deploy-core.yml` — VPC and networking
- `deploy-app-infrastructure.yml` — RDS, ECS, Secrets
- `deploy-app-stocks.yml` — Loader task definitions
- `deploy-webapp.yml` — REST API Lambda
- `deploy-algo-orchestrator.yml` — Trading engine

### CI/Testing Workflows
- `ci-fast-gates.yml` — Linting, unit tests (5 min)
- `ci-backtest-regression.yml` — Backtest validation (slow, 20 min)

### Cleanup Workflows
- `cleanup-orphaned-resources.yml` — Delete ECR images, unused IAM roles
- `cleanup-vpc.yml` — Deep clean VPC (deletes all resources + RDS)
- `cleanup-all-stacks.yml` — Nuclear option (full stack deletion)

### Monitoring Workflows
- `check-stack-status.yml` — Read-only health check
- `debug-oidc-trust-policy.yml` — Diagnose GitHub OIDC issues

---

## GitHub Secrets Required

Set these in GitHub repository settings (Settings → Secrets and variables → Actions):

```
AWS_ACCESS_KEY_ID        — AWS IAM access key
AWS_SECRET_ACCESS_KEY    — AWS IAM secret key
AWS_ACCOUNT_ID           — 12-digit AWS account ID
SLACK_WEBHOOK_URL        — (Optional) for alerts
```

---

## Deployment Troubleshooting

### Deployment Stuck/Hung
1. Check workflow logs: https://github.com/argie33/algo/actions
2. Look for the FIRST error (scroll to top)
3. Common issues:
   - **"Secrets not set"** → Add GitHub secrets (see above)
   - **"Insufficient permissions"** → Verify IAM user has CloudFormation, EC2, RDS, Lambda, ECS permissions
   - **"Stack already exists in bad state"** → Cleanup workflow auto-handles this
   - **"OIDC role not found"** → Run `bootstrap-oidc.yml` first

### RDS Connection Failed
1. Verify RDS is in private subnets:
   ```bash
   aws ec2 describe-subnets --region us-east-1 --query 'Subnets[?Tags[?Key==`Name`]].CidrBlock'
   ```
2. Check security group allows 5432:
   ```bash
   aws ec2 describe-security-groups --region us-east-1 --query 'SecurityGroups[?GroupName==`*rds*`]'
   ```
3. Test from Bastion via Session Manager (see tools-and-access.md)

### Lambda Function Not Triggering
1. Check EventBridge Scheduler rules:
   ```bash
   aws scheduler list-schedules --region us-east-1 --query 'Schedules[?contains(GroupName, `stocks`)]'
   ```
2. Verify Lambda execution role has required permissions:
   ```bash
   aws iam get-role --role-name algo-orchestrator-role --query 'Role.AssumeRolePolicyDocument'
   ```
3. Check CloudWatch logs:
   ```bash
   aws logs tail /aws/lambda/algo-orchestrator --follow
   ```

### Deployment Cost Unexpected
- Review CloudFormation stack outputs to see what was created
- Check for duplicate stacks: `aws cloudformation list-stacks --region us-east-1`
- Verify no orphaned resources: `cleanup-orphaned-resources.yml`
- See cost breakdown in algo-tech-stack.md

---

## Manual Resource Cleanup

If a deployment fails and leaves resources orphaned:

**Option 1: Cleanup Workflow (Recommended)**
```bash
gh workflow run cleanup-orphaned-resources.yml
```

**Option 2: Manual Cleanup**
```bash
# List and delete ECR images
aws ecr list-images --repository-name stocks-app-registry --region us-east-1
aws ecr batch-delete-image --repository-name stocks-app-registry --image-ids imageTag=<TAG> --region us-east-1

# Delete stack (keeps RDS for safety)
aws cloudformation delete-stack --stack-name stocks-core --region us-east-1
```

**Option 3: Full Nuclear Cleanup (Loses Everything Except Backups)**
```bash
gh workflow run cleanup-all-stacks.yml
```

---

**Last Updated:** 2026-05-07

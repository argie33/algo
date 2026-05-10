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

---

## Infrastructure Modules (Terraform)

### 1. template-bootstrap.yml (One-Time)
**Purpose:** GitHub OIDC provider
**Resources:** IAM role for GitHub Actions
**Deploy:** `gh workflow run bootstrap-oidc.yml`
**Note:** Only run once; skip on subsequent deployments

### 1. VPC Module (terraform/modules/vpc)
- VPC (10.0.0.0/16)
- 3 public subnets, 3 private subnets across 3 AZs
- Security groups (RDS, ECS, Lambda, bastion)
- VPC endpoints (S3, Secrets, DynamoDB, CloudWatch, EventBridge, SQS, SNS)
- Bastion host for SSH access
- NAT Gateway (optional)

### 2. Database Module (terraform/modules/database)
- RDS PostgreSQL (db.t3.micro, 20GB auto-scaling)
- Secrets Manager (DB credentials, email config, Alpaca secrets)
- Parameter group (PostgreSQL 14 optimization)
- Enhanced monitoring & alarms
- DynamoDB table for watermarks (incremental loading)

### 3. Compute Module (terraform/modules/compute)
- ECR repository (Docker images)
- ECS cluster (Fargate + Spot capacity)
- CloudWatch log groups (30-day retention)
- Capacity providers (on-demand, spot pricing)

### 4. Loaders Module (terraform/modules/loaders)
- 40 ECS task definitions (data loaders)
- EventBridge rules (staggered daily schedule, 3:30am-10:25pm ET)
- CloudWatch alarms (failed tasks, stale data)
- SQS dead-letter queue (failed executions)

### 5. Services Module (terraform/modules/services)
- Lambda functions (REST API, Algo orchestrator)
- API Gateway (HTTP, CORS, JWT auth)
- CloudFront distribution (frontend CDN)
- Cognito user pool (authentication)
- EventBridge Scheduler (5:30pm ET weekdays)

### 6. IAM Module (terraform/modules/iam)
- ECS task execution role
- ECS task role (S3, Secrets, RDS)
- Lambda roles (API, Algo)
- GitHub Actions OIDC role
- Service principal roles

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

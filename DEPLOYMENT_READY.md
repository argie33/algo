# AWS Infrastructure Deployment — Ready to Deploy

**Status:** ✅ All infrastructure templates and workflows configured for deployment

**Last Updated:** 2026-05-05  
**Deployment Order:** 6 CloudFormation stacks (dependencies enforced)

---

## What's Ready

### ✅ Templates (6 configured and renamed)
- `template-bootstrap.yml` → Stack: `stocks-oidc`
- `template-core.yml` → Stack: `stocks-core`
- `template-data-infrastructure.yml` → Stack: `stocks-data`
- `template-loader-tasks.yml` → Stack: `stocks-loaders`
- `template-webapp.yml` → Stack: `stocks-webapp-dev`
- `template-algo.yml` → Stack: `stocks-algo-dev`

### ✅ Workflows (7 configured with static credentials)
- `.github/workflows/bootstrap-oidc.yml` (one-time setup)
- `.github/workflows/deploy-core.yml` (root infrastructure)
- `.github/workflows/deploy-data-infrastructure.yml` (RDS, ECS cluster)
- `.github/workflows/deploy-loaders.yml` (62 data loader tasks)
- `.github/workflows/deploy-webapp.yml` (Lambda API, frontend)
- `.github/workflows/deploy-algo.yml` (Algo orchestrator Lambda)
- `.github/workflows/deploy-all-infrastructure.yml` (master orchestrator)

### ✅ Authentication
- All workflows configured to use **static AWS credentials** (`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`)
- GitHub Secrets required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID`
- OIDC provider (stocks-oidc) configured in bootstrap template, not used by workflows

### ✅ Architecture Standards Applied
- One export prefix per template (StocksOidc-, StocksCore-, StocksApp-, StocksLoaders-, etc.)
- Secrets stored in AWS Secrets Manager, not as environment variables
- All resources tagged with Project, Environment, ManagedBy, Stack
- Stack naming: `stocks-{component}[-{env}]` (no `-stack` suffix)
- Pre-flight checks and rollback-on-failure jobs in all deployment workflows

---

## Deployment Sequence (automatic via orchestrator)

1. **Bootstrap** (stocks-oidc) — Creates OIDC provider for GitHub Actions
2. **Core** (stocks-core) — VPC, subnets, ECR registry, S3 buckets, IAM roles
3. **Data Infrastructure** (stocks-data) — RDS PostgreSQL, ECS cluster, secrets, ECS execution role
4. **Parallel deployment** (all depend on stocks-data):
   - **Loaders** (stocks-loaders) — 62 ECS task definitions + 4 EventBridge scheduled rules
   - **Webapp** (stocks-webapp-dev) — Lambda REST API, CloudFront, Cognito
   - **Algo** (stocks-algo-dev) — Algo Lambda function + EventBridge Scheduler

---

## How to Deploy

### Option A: Full Orchestration (Recommended)
Trigger the master orchestrator workflow that deploys all 6 stacks in the correct order:

```bash
# Via GitHub CLI
gh workflow run deploy-all-infrastructure.yml --repo argeropolos/algo -f skip_bootstrap=false

# Via GitHub UI
1. Go to: https://github.com/argeropolos/algo/actions
2. Click "Deploy All Infrastructure (Master Orchestrator)"
3. Click "Run workflow"
4. Set "Skip OIDC bootstrap" to "false" (first deployment)
5. Click "Run workflow" button
```

Workflow will:
- Deploy stocks-oidc (OIDC provider)
- Deploy stocks-core (core infrastructure)
- Deploy stocks-data (data layer)
- Deploy stocks-loaders, stocks-webapp-dev, stocks-algo-dev in parallel
- Display summary of all 6 stacks deployed

**Estimated time:** 15-20 minutes for full deployment

### Option B: Individual Stack Deployment
Deploy stacks one at a time (useful for debugging):

```bash
# Deploy core first
gh workflow run deploy-core.yml --repo argeropolos/algo

# Then data infrastructure
gh workflow run deploy-data-infrastructure.yml --repo argeropolos/algo

# Then any of the dependent stacks
gh workflow run deploy-loaders.yml --repo argeropolos/algo
gh workflow run deploy-webapp.yml --repo argeropolos/algo
gh workflow run deploy-algo.yml --repo argeropolos/algo
```

---

## Verify Deployment Success

After deployment completes:

### 1. Check CloudFormation Stacks
```bash
aws cloudformation describe-stacks \
  --region us-east-1 \
  --query 'Stacks[*].[StackName,StackStatus]' \
  --output table

# Expected output (all should show CREATE_COMPLETE or UPDATE_COMPLETE):
# StackName           StackStatus
# stocks-oidc         CREATE_COMPLETE
# stocks-core         CREATE_COMPLETE
# stocks-data         CREATE_COMPLETE
# stocks-loaders      CREATE_COMPLETE
# stocks-webapp-dev   CREATE_COMPLETE
# stocks-algo-dev     CREATE_COMPLETE
```

### 2. Check Data Loaders
```bash
# View loader task definitions
aws ecs list-task-definition-families \
  --region us-east-1 \
  --query 'taskDefinitionFamilies[?contains(@, `loader`)]' \
  --output text | wc -l
# Expected: 64 task definition families (62 data loaders + 2 new ones)

# View EventBridge rules for scheduled loaders
aws events list-rules \
  --name-prefix "Stocks" \
  --region us-east-1 \
  --query 'Rules[*].[Name,ScheduleExpression]' \
  --output table
# Expected: 4 rules (MarketIndices, EconData, SectorRanking, FearGreed)
```

### 3. Check Webapp Endpoint
```bash
# Get CloudFront distribution URL
aws cloudformation describe-stacks \
  --stack-name stocks-webapp-dev \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' \
  --output text

# Open URL in browser — should display frontend dashboard
```

### 4. Check Algo Lambda
```bash
# Verify algo Lambda function exists
aws lambda get-function \
  --function-name stocks-algo-dev-AlgoLambda \
  --region us-east-1 \
  --query 'Configuration.FunctionArn' \
  --output text

# Check EventBridge Scheduler for algo jobs
aws scheduler list-schedules \
  --region us-east-1 \
  --name-prefix "stocks-algo" \
  --query 'Schedules[*].[Name,ScheduleExpression]' \
  --output table
```

---

## GitHub Secrets Required

Before deploying, ensure these secrets are configured in the repository:

| Secret | Purpose | Source |
|--------|---------|--------|
| `AWS_ACCESS_KEY_ID` | AWS API access (static credential) | AWS IAM User |
| `AWS_SECRET_ACCESS_KEY` | AWS API secret (static credential) | AWS IAM User |
| `AWS_ACCOUNT_ID` | AWS account ID for role ARN construction | AWS Account settings |

**How to set:**
1. Go to: https://github.com/argeropolos/algo/settings/secrets/actions
2. Click "New repository secret"
3. Add each of the 3 secrets above

---

## Troubleshooting

### Deployment Fails with "Invalid AWS Credentials"
- Verify secrets are correct in GitHub Settings → Secrets
- Verify AWS credentials have CloudFormation, EC2, RDS, Lambda, IAM, and S3 permissions
- Try deploying a single stack first: `deploy-core.yml`

### Deployment Fails with "Stack already exists"
- Check if stack was partially created in previous failed attempt
- Delete the failed stack: `aws cloudformation delete-stack --stack-name {stack-name}`
- Wait for deletion to complete: `aws cloudformation wait stack-delete-complete --stack-name {stack-name}`
- Retry deployment

### Webapp Lambda Returns 500 Errors
- Check Lambda CloudWatch logs: `aws logs tail /aws/lambda/stocks-webapp-dev-ApiFunction --follow`
- Verify RDS database connection in CloudWatch Logs
- Check that `stocks-data` stack is fully deployed

### Loaders Not Running
- Verify EventBridge rules are active: `aws events list-rules --region us-east-1`
- Check ECS cluster has tasks running: `aws ecs list-tasks --cluster stocks-data --region us-east-1`
- View task logs: `aws logs tail /ecs/loader-name --follow`

---

## Post-Deployment Checklist

- [ ] All 6 CloudFormation stacks deployed (CREATE_COMPLETE or UPDATE_COMPLETE)
- [ ] Data loaders running on schedule (check CloudWatch Logs)
- [ ] Webapp frontend accessible via CloudFront URL
- [ ] Sample API call returns data from RDS
- [ ] Algo Lambda scheduled (check EventBridge Scheduler)
- [ ] Database has fresh data (run: `SELECT COUNT(*) FROM stocks;`)

---

## Next Steps After Successful Deployment

1. **Monitor loaders** — Check CloudWatch Logs for each loader running successfully
2. **Verify data freshness** — Query RDS database for recent stock data
3. **Test webapp** — Load frontend, verify charts display data
4. **Enable alerts** — Set up CloudWatch alarms for Lambda errors, RDS CPU
5. **Configure backup** — Enable RDS automated backups to S3
6. **Document API endpoints** — Share webapp API URL with frontend team

---

## Architecture Summary

**Deployment stack count:** 6  
**ECS task definitions:** 64 (62 data loaders + 2 new)  
**EventBridge scheduled rules:** 4 (data loader schedules)  
**Lambda functions:** 3 (Webapp API, Algo orchestrator, + 2 new in loaders)  
**RDS database:** 1 (PostgreSQL with TimescaleDB)  
**S3 buckets:** 5 (Code, Artifacts, Templates, CloudFront logs, Algo artifacts)  
**Estimated monthly cost:** $65-90 (VPC NATing + RDS + ECS Fargate)

See `CLAUDE.md` for full architectural documentation and deployment principles.

# AWS Infrastructure Deployment — Current Status

**Date:** 2026-05-06 01:27 UTC  
**Stage:** Testing core infrastructure deployment  
**Workflow Status:** https://github.com/argeropolos/algo/actions/runs/25411687355 (in progress)

---

## ✅ Completed Tasks

### Templates
- ✅ Renamed 4 templates per architecture plan
  - `template-data-infrastructure.yml` (was template-app-stocks.yml)
  - `template-loader-tasks.yml` (was template-app-ecs-tasks.yml)
  - `template-webapp.yml` (was template-webapp-lambda.yml)
  - `template-algo.yml` (was template-algo-orchestrator.yml)
- ✅ All 6 templates have proper architecture headers
- ✅ 62 ECS task definitions in loader template
- ✅ Template syntax verified

### Workflows
- ✅ Converted ALL 10 workflows from OIDC role-to-assume to static credentials
  - All now use: `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
  - Removed all `AWS_ROLE_ARN` environment variables
  - Removed all `role-session-name` parameters
- ✅ All deploy workflows configured as reusable workflows (`workflow_call`)
- ✅ All workflows have pre-flight dependency checks
- ✅ All workflows have rollback-on-failure jobs

### Infrastructure Fixes
- ✅ Fixed deploy-core.yml to handle CloudFormation `REVIEW_IN_PROGRESS` state
  - Detects stuck stacks and deletes them before deployment
  - Prevents changeset approval hangs
  - Applies to both deploy and rollback steps
- ✅ Master orchestrator workflow (deploy-all-infrastructure.yml) configured
  - Deploys all 6 stacks in correct dependency order
  - Enforces pre-flight checks and rollback cleanup

### Commits
```
d8dbf2c47 Fix: handle CloudFormation REVIEW_IN_PROGRESS state in deploy-core
2ef43a66a Fix: finish converting all workflows to static AWS credentials
db1ba3cf4 Fix: use static credentials instead of OIDC in deploy-core
```

---

## 🔄 Current Task: Testing deploy-core

**Workflow Run:** 25411687355  
**Status:** IN PROGRESS  
**What it's testing:**
1. AWS credentials validation
2. CloudFormation hook cleanup
3. Core infrastructure deployment (VPC, subnets, ECR, S3, Bastion)
4. Stack status verification
5. Stack output export verification

**Expected result:** `stocks-core` stack in `CREATE_COMPLETE` state with 9 exports:
- StocksCore-VpcId
- StocksCore-PublicSubnet1Id, StocksCore-PublicSubnet2Id
- StocksCore-ContainerRepositoryUri
- StocksCore-CfTemplatesBucketName
- StocksCore-CodeBucketName
- StocksCore-AlgoArtifactsBucketName (NEW)
- StocksCore-BastionSecurityGroupId
- StocksCore-VpcEndpointSecurityGroupId

---

## 📋 Deployment Queue (Ready to Deploy)

Once deploy-core succeeds, follow this sequence:

### Phase 2: Data Infrastructure
- **Workflow:** deploy-data-infrastructure.yml
- **Stack:** stocks-data
- **Creates:** RDS PostgreSQL, ECS cluster, Secrets Manager, task execution role
- **Depends on:** stocks-core
- **Expects:** 8 exports (DBEndpoint, DBPort, DBName, SecretArn, etc.)

### Phase 3: Parallel Deployments (all depend on stocks-data)

#### 3a. Loaders
- **Workflow:** deploy-loaders.yml
- **Stack:** stocks-loaders
- **Creates:** 62 ECS task definitions + 4 EventBridge scheduled rules
- **EventBridge Rules:** MarketIndices, EconData, SectorRanking, FearGreed (evening schedule)
- **Expects:** StocksLoaders-* exports

#### 3b. Webapp
- **Workflow:** deploy-webapp.yml
- **Stack:** stocks-webapp-dev
- **Creates:** Lambda API, CloudFront, Cognito, API Gateway
- **Expects:** CloudFront URL in outputs

#### 3c. Algo
- **Workflow:** deploy-algo.yml
- **Stack:** stocks-algo-dev
- **Creates:** Algo orchestrator Lambda + EventBridge Scheduler
- **Expects:** Lambda ARN, Scheduler ARN

---

## 🛠️ GitHub Secrets Required

Before any workflow can succeed, these must be set in repository settings:

| Secret | Status | Source |
|--------|--------|--------|
| `AWS_ACCESS_KEY_ID` | ⚠️ **REQUIRED** | AWS IAM credentials (static key) |
| `AWS_SECRET_ACCESS_KEY` | ⚠️ **REQUIRED** | AWS IAM credentials (static key) |
| `AWS_ACCOUNT_ID` | ⚠️ **REQUIRED** | AWS account ID (12 digits) |

**How to set:**
1. Go to: https://github.com/argeropolos/algo/settings/secrets/actions
2. Click "New repository secret"
3. Add each of the 3 secrets

⚠️ **Deployment will fail without these secrets.**

---

## 📊 Architecture Summary

**Total Resources:**
- 6 CloudFormation stacks
- 1 VPC with 2 public + 2 private subnets
- 1 RDS PostgreSQL instance (public, no encryption)
- 1 ECS cluster
- 62 ECS task definitions (data loaders)
- 3 Lambda functions (Webapp API, Algo orchestrator, + 2 scheduled in loaders)
- 5 S3 buckets (Code, Templates, Artifacts, CloudFront logs, Algo artifacts)
- 1 CloudFront distribution (frontend)
- 1 Cognito user pool (authentication)
- 4 EventBridge rules (scheduled data loaders)

**Estimated Monthly Cost:** $65-90  
(VPC NAT: $32-45, RDS: $20-30, ECS/Lambda: $10-20)

---

## 🚀 Quick Start (After deploy-core Succeeds)

```bash
# Option 1: Deploy everything automatically
gh workflow run deploy-all-infrastructure.yml --repo argeropolos/algo

# Option 2: Deploy individually (for debugging)
gh workflow run deploy-data-infrastructure.yml --repo argeropolos/algo
gh workflow run deploy-loaders.yml --repo argeropolos/algo
gh workflow run deploy-webapp.yml --repo argeropolos/algo
gh workflow run deploy-algo.yml --repo argeropolos/algo
```

---

## ✅ Post-Deployment Verification

Once all stacks deploy, verify with:

```bash
# 1. Check all stacks deployed
aws cloudformation describe-stacks \
  --region us-east-1 \
  --query 'Stacks[*].[StackName,StackStatus]' \
  --output table

# 2. Verify data loaders running
aws logs tail /ecs/stock-symbols-loader --follow

# 3. Get webapp URL
aws cloudformation describe-stacks \
  --stack-name stocks-webapp-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`WebsiteURL`].OutputValue' \
  --output text

# 4. Verify database connection
psql -h <DB_ENDPOINT> -U stocks -d stocks -c "SELECT COUNT(*) FROM stocks;"

# 5. Check EventBridge rules
aws events list-rules --name-prefix Stocks
```

---

## 🐛 Troubleshooting

### Workflow Stuck in REVIEW_IN_PROGRESS
✅ **FIXED** - Now automatically deletes stuck stacks and retries

### AWS Credentials Invalid
- Verify secrets are set in repository settings
- Check credentials have CloudFormation, EC2, RDS, IAM, Lambda, S3 permissions
- Verify secrets are not expired

### Stack Deletion Fails
- Check CloudWatch logs for resource errors
- Manually delete stuck resources in AWS Console
- Retry deployment

### Webapp Returns 500 Errors
- Check Lambda CloudWatch logs: `/aws/lambda/stocks-webapp-dev-*`
- Verify RDS is accessible from Lambda VPC
- Check database connection string in Lambda environment

---

## 📝 Next Steps

1. **Monitor workflow 25411687355** — Should complete in ~5 minutes
2. **Check result** — stocks-core should be CREATE_COMPLETE
3. **Verify exports** — All 9 StocksCore-* exports should exist
4. **Trigger deploy-data-infrastructure.yml** — Deploy RDS and ECS cluster
5. **Deploy dependent stacks** — Loaders, Webapp, Algo (can be parallel)
6. **Verify endpoints** — Test API, loaders, frontend
7. **Monitor in production** — Set up CloudWatch alarms

See `DEPLOYMENT_READY.md` for complete deployment guide.

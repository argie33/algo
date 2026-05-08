# Infrastructure Deployment Guide

## Overview
This guide documents the correct order and prerequisites for deploying all AWS infrastructure via GitHub Actions workflows.

## Deployment Order (Dependencies)

### Phase 1: Bootstrap (Prerequisite for all other deployments)
**Workflow:** `deploy-bootstrap-oidc.yml`
**Purpose:** Create OIDC provider and GitHub Actions deployment role
**Status:** ✅ WORKING
**Prerequisites:** AWS credentials in GitHub secrets (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
**Manual trigger:** Yes (workflow_dispatch)

```
After this step, the GitHub Actions role GitHubActionsDeployRole will exist
with AdministratorAccess permissions.
```

---

### Phase 2: Core Infrastructure
**Workflow:** `deploy-core.yml`
**Purpose:** Create VPC, subnets, security groups, ECR registry
**Template:** `template-core-minimal.yml`
**Status:** ⚠️ NEEDS VERIFICATION
**Depends on:** Phase 1 (Bootstrap)
**Trigger:** Automatic on push to main (paths: template-core-minimal.yml, deploy-core.yml)

```
After this step, these resources will be exported:
- StocksCore-VpcId
- StocksCore-PublicSubnet1, StocksCore-PublicSubnet2
- StocksCore-PrivateSubnet1, StocksCore-PrivateSubnet2
- StocksCore-EcsTasksSecurityGroupId
- StocksCore-RdsSecurityGroupId
- StocksCore-EcrRepositoryUri
- StocksCore-CfTemplatesBucketName
```

---

### Phase 3: Application Infrastructure (RDS + ECS)
**Workflow:** `deploy-app-stocks.yml`
**Purpose:** Create RDS database, database credentials secret, ECS cluster
**Template:** `template-app-stocks.yml`
**Status:** ❌ BROKEN (needs review)
**Depends on:** Phase 2 (Core Infrastructure)
**Trigger:** Automatic on push to main

```
This step is CRITICAL - it creates:
- RDS PostgreSQL database instance
- Secrets Manager secret: stocks-db-secrets-{StackName}-{Region}-001
  (This secret is required by the algo-orchestrator Lambda)
- ECS cluster
- Task execution role

BLOCKERS:
- Cannot deploy until core infrastructure exports exist
- May be failing due to CloudFormation issues from Phase 2
```

---

### Phase 4A: Algo Orchestrator (Lambda + EventBridge)
**Workflow:** `deploy-algo-orchestrator.yml`
**Purpose:** Deploy Lambda function for algo execution, EventBridge scheduler
**Template:** `template-algo-lambda-minimal.yml`
**Status:** ⚠️ RECENTLY FIXED
**Depends on:** Phase 3 (Database & credentials secret)
**Trigger:** Automatic on push to main

```
RECENT FIX:
- Removed unused Alpaca credentials parameter
- Updated to find database secret using pattern matching (stocks-db-secrets-*)
- If database secret doesn't exist, uses placeholder ARN

This workflow:
1. Validates algo Python files exist
2. Builds Python dependencies
3. Packages Lambda code and uploads to S3
4. Deploys CloudFormation stack with:
   - Lambda function
   - IAM execution role
   - EventBridge rule (daily 5:30pm ET)
   - SNS alert topic
   - CloudWatch logs and alarms

The Lambda expects these environment variables:
- DATABASE_SECRET_ARN: ARN of stocks-db-secrets-* secret
- DRY_RUN_MODE: 'true' or 'false' (default: 'true')
- EXECUTION_MODE: 'paper' or 'live' (default: 'paper')
- ENVIRONMENT: 'dev', 'staging', or 'prod' (default: 'dev')
- ALERT_SNS_TOPIC_ARN: SNS topic for alerts
```

---

### Phase 4B: App ECS Loaders
**Workflow:** `deploy-app-stocks.yml` (same as Phase 3, but loads loader images)
**Purpose:** Deploy loader Docker images and ECS task definitions
**Status:** ❌ BROKEN
**Depends on:** Phase 3 + Phase 4A (can run in parallel after Phase 3)

---

### Phase 5: Web Application
**Workflow:** `deploy-webapp.yml`
**Purpose:** Deploy Lambda functions for web backend
**Status:** ❌ BROKEN
**Depends on:** Phase 3 (Database & infrastructure)

---

## Current Blockers

### Blocker 1: Core Infrastructure (Phase 2)
- **Status:** ⚠️ UNKNOWN - needs verification
- **Impact:** Prevents Phase 3+ from deploying
- **Fix:** Run `deploy-core.yml` and monitor CloudFormation events

### Blocker 2: Application Infrastructure (Phase 3)
- **Status:** ❌ BLOCKED by Phase 2
- **Impact:** Prevents Algo Orchestrator from deploying
- **Fix:** After Phase 2 succeeds, run `deploy-app-stocks.yml`

### Blocker 3: Algo Orchestrator (Phase 4A)
- **Status:** ⚠️ RECENTLY FIXED (code updated but not tested)
- **Impact:** Algo trading Lambda not deployed, algo tables not created
- **Fix:** Push changes to trigger workflow, monitor for CloudFormation errors

### Blocker 4: Loader Deployments (Phase 4B)
- **Status:** ❌ BLOCKED by Phase 3 and 4A
- **Impact:** Data loaders not running
- **Fix:** After Phase 3 and 4A succeed, re-run `deploy-app-stocks.yml` with loader image tags

---

## How to Manually Trigger Workflows

### Using GitHub CLI (if available):
```bash
gh workflow run bootstrap-oidc.yml -R argie33/algo
gh workflow run deploy-core.yml -R argie33/algo
gh workflow run deploy-app-stocks.yml -R argie33/algo -f environment=dev
gh workflow run deploy-algo-orchestrator.yml -R argie33/algo -f environment=dev -f dry_run=true
```

### Via GitHub Web UI:
1. Go to: https://github.com/argie33/algo/actions
2. Select workflow by name
3. Click "Run workflow" button (top right)
4. Enter inputs and click "Run workflow"

---

## Monitoring Deployment Progress

### Real-time monitoring:
- GitHub Actions logs: https://github.com/argie33/algo/actions
- AWS CloudFormation: https://console.aws.amazon.com/cloudformation/home?region=us-east-1
- AWS RDS: https://console.aws.amazon.com/rds/home?region=us-east-1
- AWS Lambda: https://console.aws.amazon.com/lambda/home?region=us-east-1
- AWS Secrets Manager: https://console.aws.amazon.com/secretsmanager/home?region=us-east-1

### Checking deployment status:
```bash
# Check CloudFormation stacks
aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?contains(StackName, `stocks`)].{Name:StackName,Status:StackStatus}' --output table

# Check RDS database
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[].{Name:DBInstanceIdentifier,Status:DBInstanceStatus}' --output table

# Check Lambda function
aws lambda get-function --function-name algo-orchestrator --region us-east-1 --query 'Configuration.{Name:FunctionName,Runtime:Runtime,LastModified:LastModified}' --output table

# Check EventBridge rule
aws events describe-rule --name algo-eod-orchestrator --region us-east-1
```

---

## If a Workflow Fails

### Step 1: Get the error message
1. Go to GitHub Actions > failed workflow
2. Click the failed job
3. Expand the failed step
4. Copy the error message

### Step 2: Identify the phase
- Bootstrap failure → Cannot proceed, need manual AWS setup
- Core failure → Fix core infrastructure
- App failure → May depend on core, check imports
- Algo failure → Check secrets exist, check database connectivity
- Loader failure → Check algo deployment succeeded first

### Step 3: Fix based on error type
- **CloudFormation syntax error** → Review the template
- **Missing resource** → Check earlier phases completed
- **Permission denied** → Check GitHub Actions role has permissions
- **Resource quota exceeded** → Request AWS quota increase
- **Timeout** → Increase timeout or simplify template

---

## Key Resources Exported by Each Phase

| Phase | Stack Name | Exports | Purpose |
|-------|-----------|---------|---------|
| 1 | stocks-oidc-bootstrap | StocksOidc-GitHubActionsDeployRoleArn | OIDC auth |
| 2 | stocks-core-stack | StocksCore-VpcId, -PublicSubnet*, -PrivateSubnet*, -EcrRepositoryUri | Networking |
| 3 | stocks-app-stack | StocksApp-SecretArn, -DBEndpoint, -DBPort, -DBName, -ClusterArn | Database |
| 4A | stocks-algo-orchestrator | N/A (local only) | Algo Lambda |
| 4B | stocks-app-loaders | N/A | Loader tasks |
| 5 | stocks-webapp | N/A | Web backend |

---

## Quick Reference: What Each Workflow Does

```
bootstrap-oidc.yml
├─ Creates OIDC provider
└─ Creates GitHubActionsDeployRole (AdministratorAccess)

deploy-core.yml
├─ Creates VPC & subnets
├─ Creates security groups
└─ Creates ECR registry & S3 bucket

deploy-app-stocks.yml
├─ Creates RDS PostgreSQL database
├─ Creates database credentials secret
├─ Creates ECS cluster
├─ Creates ECS task execution role
└─ Optionally deploys loader images

deploy-algo-orchestrator.yml
├─ Validates algo Python files
├─ Builds & packages Lambda function
├─ Uploads to S3
└─ Deploys Lambda + EventBridge + SNS

deploy-app-infrastructure.yml
├─ Creates additional app resources
└─ (Purpose unclear - needs review)

deploy-webapp.yml
├─ Creates Lambda functions for web backend
└─ Creates API Gateway

deploy-app-stocks-loaders.yml (if exists)
└─ Deploys specific loader containers
```

---

## Testing the Deployment Locally (Optional)

You can validate the CloudFormation templates without deploying:

```bash
# Validate template syntax
aws cloudformation validate-template --template-body file://template-algo-lambda-minimal.yml

# Validate all templates
for f in template-*.yml; do
  echo "Validating $f..."
  aws cloudformation validate-template --template-body file://$f
done
```

---

## Notes for Future Improvements

1. **Use CloudFormation stack policies** - Prevent accidental deletions
2. **Add stack tags** - Track costs and ownership
3. **Use DependsOn** - Make explicit dependencies in templates
4. **Add drift detection** - Detect manual changes to resources
5. **Create alarm notifications** - SNS alerts for failures
6. **Document manual setup steps** - Algopaca credentials if needed
7. **Consider nested stacks** - Reduce template size and complexity
8. **Add rollback triggers** - Auto-revert failed deployments

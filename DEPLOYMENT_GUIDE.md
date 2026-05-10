# AWS Infrastructure Deployment Guide

## Overview

The system uses **Terraform-as-Code (IaC)** for all AWS infrastructure, deployed automatically via GitHub Actions on push to `main`, or manually via workflow dispatch.

**Architecture:**
- RDS PostgreSQL database (dev: t3.micro, prod: multi-AZ)
- Lambda functions (db-init, API, orchestrator)
- EventBridge scheduler (orchestrator: 5:30pm ET weekdays)
- ECS for data loaders (docker-compose equivalent in cloud)
- IAM roles with least-privilege access
- VPC with public/private subnets
- CloudWatch monitoring & alarms

## Prerequisites

### 1. GitHub Secrets Configuration

Set these secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

**Required Secrets:**
```
AWS_ACCESS_KEY_ID              # AWS IAM user access key
AWS_SECRET_ACCESS_KEY          # AWS IAM user secret key
RDS_PASSWORD                   # Database password (min 8 chars, alphanumeric)
ALPACA_API_KEY_ID              # Alpaca paper trading API key
ALPACA_API_SECRET_KEY          # Alpaca API secret
ALERT_EMAIL_ADDRESS            # Email for CloudWatch alarms (optional)
JWT_SECRET                     # Secret for JWT tokens (optional)
FRED_API_KEY                   # Federal Reserve data API key (optional)
EXECUTION_MODE                 # "paper" for paper trading (default)
ORCHESTRATOR_DRY_RUN           # "false" to execute trades (default)
ORCHESTRATOR_LOG_LEVEL         # "INFO" for normal logging (default)
DATA_PATROL_ENABLED            # "true" to enable data validation (default)
DATA_PATROL_TIMEOUT_MS         # "30000" for data patrol timeout (default)
```

### 2. AWS Account Setup

1. Create AWS account or use existing
2. Create IAM user for GitHub Actions with permissions:
   - EC2 (VPC, security groups, subnets)
   - RDS (create/manage database)
   - Lambda (create/deploy functions)
   - IAM (create roles, users)
   - S3 (Terraform state, code)
   - ECR (container registry)
   - EventBridge (schedulers)
   - CloudWatch (logs, metrics)
   - SNS (notifications)
   - SES (email)

3. Store access key/secret in GitHub secrets

### 3. Verify Local Setup

```bash
# From repo root
cd terraform

# Validate configuration
terraform validate

# Check variable defaults
terraform variables
```

## Deployment Process

### Option A: Automatic Deployment (Recommended)

Push changes to `main` branch:

```bash
git add .
git commit -m "chore: Deploy to AWS"
git push origin main
```

GitHub Actions will automatically:
1. ✅ Run `deploy-all-infrastructure.yml` workflow
2. ✅ Execute `terraform apply` to create/update infrastructure
3. ✅ Build and push Docker images to ECR
4. ✅ Deploy Lambda functions
5. ✅ Deploy frontend code

**Monitor:**
- Go to `Actions` tab in GitHub repo
- Watch `Deploy All Infrastructure` workflow
- Check logs for any failures

### Option B: Manual Deployment

1. Go to GitHub repo > `Actions` tab
2. Select `Deploy All Infrastructure`
3. Click `Run workflow`
4. Optional: Uncheck `skip_terraform` if you want to deploy infrastructure
5. Click `Run workflow`

### Option C: Local Development (Docker)

For testing before AWS deployment:

```bash
# From repo root
cd algo

# Start local services
docker-compose up -d

# Run orchestrator locally
python3 test_orchestrator_direct.py

# Check logs
docker-compose logs postgres
docker-compose logs redis
```

## What Gets Deployed

### Infrastructure (Terraform)

- **VPC**: 10.0.0.0/16 with public/private subnets across 2 AZs
- **RDS PostgreSQL**: 
  - Dev: db.t3.micro (single-AZ)
  - Prod: db.t3.small (multi-AZ with backups)
  - Automatic schema initialization via Lambda
- **Lambda Functions**:
  - `stocks-db-init-dev`: Initialize database schema on first run
  - `stocks-api-dev`: FastAPI backend for web UI
  - `stocks-algo-dev`: Orchestrator execution (triggered by EventBridge)
  - `stocks-loaders-dev`: Data loading tasks
- **EventBridge Scheduler**: 5:30pm ET weekdays → orchestrator Lambda
- **IAM Roles**:
  - `algo-github-deployer`: GitHub Actions deployment
  - `algo-pipeline`: Pipeline/data loading (CloudFormation)
  - `algo-developer`: Local development
- **S3 Buckets**:
  - Terraform state (encrypted)
  - Code packages
  - Frontend assets
  - Data backups
- **CloudWatch**: Logs, metrics, alarms
- **SNS**: Email notifications for alerts

### Application Code (GitHub Actions)

- Lambda layer with dependencies (psycopg2, pandas, numpy, etc.)
- Orchestrator code deployment
- API backend deployment
- Frontend deployment to CloudFront

## Post-Deployment Validation

### 1. Check Infrastructure

```bash
# Access AWS Console
# Check RDS instance is running
# Check Lambda functions exist
# Check EventBridge rule is scheduled for 5:30pm ET

# Or via AWS CLI:
aws rds describe-db-instances --region us-east-1
aws lambda list-functions --region us-east-1
aws events describe-rule --name algo-orchestrator-schedule --region us-east-1
```

### 2. Check Database Schema

```bash
# Connect to RDS and verify tables exist
psql -h <rds-endpoint> -U stocks -d stocks
\dt  # List tables
```

### 3. Test Orchestrator Lambda

```bash
# Via AWS Console:
# Lambda > stocks-algo-dev > Test
# Use sample event: {"action": "run_orchestrator", "date": "2026-05-08"}

# Or via CLI:
aws lambda invoke \
  --function-name stocks-algo-dev \
  --payload '{"action":"run_orchestrator"}' \
  --region us-east-1 \
  response.json
cat response.json
```

### 4. Check Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/stocks-algo-dev --follow --region us-east-1

# View RDS logs (if enabled)
aws rds describe-db-log-files --db-instance-identifier algo-db-dev --region us-east-1
```

## Troubleshooting

### Terraform Apply Fails

1. Check secrets are set correctly:
   ```bash
   # In workflow logs, you should see:
   # TF_VAR_rds_password=***
   # TF_VAR_alpaca_api_key_id=***
   ```

2. Check Terraform state in S3:
   ```bash
   aws s3 ls s3://stocks-terraform-state/
   ```

3. Check AWS credentials have sufficient permissions

### Lambda Deployment Fails

1. Check psycopg2 binary compatibility in ECR image
2. Verify Lambda layer has all dependencies
3. Check CloudWatch logs for import errors

### Database Connection Fails

1. Check security group allows Lambda → RDS traffic
2. Verify RDS instance is running
3. Check credentials are correct in Secrets Manager
4. Verify Lambda has permission to read Secrets

### EventBridge Schedule Doesn't Trigger

1. Check rule exists: `algo-orchestrator-schedule`
2. Verify target Lambda function is correct
3. Check Lambda execution role has EventBridge permissions
4. Check CloudWatch Events logs

## Local Development Workflow

### Keep Local & AWS in Sync

```bash
# 1. Develop and test locally with Docker
docker-compose up -d
python3 test_orchestrator_direct.py

# 2. Make code changes
# ... edit files ...

# 3. Test locally again
python3 test_orchestrator_direct.py

# 4. Commit and push (triggers AWS deploy)
git add .
git commit -m "feat: Add new exit rule"
git push origin main

# 5. Monitor GitHub Actions
# ... check Deploy All Infrastructure workflow ...

# 6. Test in AWS (optional)
aws lambda invoke --function-name stocks-algo-dev response.json
```

## Environment Differences

| Aspect | Local | AWS Dev | AWS Prod |
|--------|-------|---------|----------|
| Database | Docker (local) | RDS Single-AZ | RDS Multi-AZ |
| Execution | Direct Python | Lambda | Lambda |
| Scheduling | Manual/pytest | EventBridge | EventBridge |
| Alpaca | Paper mode | Paper mode | Paper or Live |
| Logging | Console | CloudWatch | CloudWatch |
| Monitoring | Manual | CloudWatch alarms | CloudWatch alarms |

## Security Considerations

1. **Secrets**: Never commit passwords, API keys, or secrets to git
2. **IAM Least Privilege**: GitHub Actions role only has needed permissions
3. **RDS Encryption**: Enabled for prod, optional for dev
4. **VPC**: RDS in private subnet, only accessible from Lambda
5. **Backups**: Automatic daily backups with 7-day retention
6. **Networking**: VPC endpoints for AWS services (no internet exposure)

## Costs

**Estimated Monthly (Dev):**
- RDS t3.micro: ~$15-20
- Lambda: ~$1-5 (free tier often covers this)
- Data transfer: ~$5-10
- **Total: ~$25-35/month**

**Estimated Monthly (Prod):**
- RDS t3.small multi-AZ: ~$50-70
- Lambda: ~$5-10
- Data transfer: ~$10-20
- **Total: ~$65-100/month**

## Next Steps

1. ✅ Configure all GitHub secrets
2. ✅ Commit this guide and CLAUDE.md updates
3. ✅ Push to main (triggers deployment)
4. ✅ Monitor workflow in GitHub Actions
5. ✅ Verify infrastructure in AWS Console
6. ✅ Test orchestrator via Lambda
7. ✅ Configure CloudWatch alarms
8. ✅ Set up email notifications

## Support

For issues:
1. Check CloudWatch logs: `aws logs tail /aws/lambda/stocks-* --follow`
2. Check Terraform state: `aws s3 ls s3://stocks-terraform-state/`
3. Review GitHub Actions workflow logs
4. Check AWS Console for resource status

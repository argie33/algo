# Terraform Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the stocks analytics infrastructure using Terraform via GitHub Actions.

## Prerequisites Checklist

### 1. AWS Account & Credentials ✓

You need:
- AWS Account ID: `626216981288`
- AWS Access Key ID (for bootstrap)
- AWS Secret Access Key (for bootstrap)

### 2. GitHub Repository Secrets ✓

Configure these secrets in GitHub: Settings → Secrets and Variables → Actions

| Secret Name | Value | Notes |
|-------------|-------|-------|
| `AWS_ACCOUNT_ID` | `626216981288` | Used for OIDC role assumption |
| `AWS_ACCESS_KEY_ID` | Your access key | Used for bootstrap operations only |
| `AWS_SECRET_ACCESS_KEY` | Your secret key | Used for bootstrap operations only |
| `RDS_PASSWORD` | Your secure password | Min 8 chars, for database access |
| `SLACK_WEBHOOK` | Your Slack webhook URL | Optional: for deployment notifications |

### 3. Bootstrap Stack (One-Time Only)

The `stocks-oidc` CloudFormation stack must be created once to establish GitHub OIDC trust:

```bash
aws cloudformation deploy \
  --template-file bootstrap/oidc.yml \
  --stack-name stocks-oidc \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName=stocks \
    GitHubOrg=argeropolos \
    GitHubRepo=algo
```

This creates the `github-actions-role` IAM role that GitHub Actions uses.

## Deployment Process

### Option 1: Automatic via GitHub Actions (Recommended)

1. **Configure GitHub Secrets:**
   ```bash
   gh secret set AWS_ACCOUNT_ID --body "626216981288"
   gh secret set AWS_ACCESS_KEY_ID --body "your-access-key"
   gh secret set AWS_SECRET_ACCESS_KEY --body "your-secret-key"
   gh secret set RDS_PASSWORD --body "your-secure-password"
   gh secret set SLACK_WEBHOOK --body "https://hooks.slack.com/..." # optional
   ```

2. **Trigger Deployment:**
   ```bash
   git add terraform/
   git commit -m "Update: Terraform infrastructure"
   git push origin main
   ```

   The `terraform-apply.yml` workflow will automatically:
   - Bootstrap AWS prerequisites (S3 state bucket, DynamoDB locks)
   - Validate Terraform configuration
   - Plan changes (shows what will be created/modified)
   - Apply changes (creates/updates infrastructure)
   - Backup state to S3

3. **Monitor Deployment:**
   - Check GitHub Actions: https://github.com/argeropolos/algo/actions
   - Look for the `Terraform Apply` workflow
   - Review logs for any errors

### Option 2: Manual Terraform Commands (Advanced)

If you need to deploy locally:

```bash
cd terraform

# Initialize (downloads modules, configures state backend)
terraform init

# Validate syntax
terraform validate

# Plan changes (shows what will happen)
terraform plan -var="rds_password=YourSecurePassword123" -out=tfplan.bin

# Apply changes
terraform apply tfplan.bin

# View outputs
terraform output
```

## What Gets Deployed

### Core Infrastructure (Terraform Modules)

| Module | Resources | Purpose |
|--------|-----------|---------|
| `iam` | Roles, Policies | GitHub Actions, Bastion, ECS, Lambda permissions |
| `vpc` | VPC, Subnets, Security Groups, VPC Endpoints | Network isolation, 7 VPC endpoints |
| `storage` | S3 Buckets | Code, data, templates, logs, frontend |
| `database` | RDS PostgreSQL, Secrets Manager | Time-series data storage |
| `compute` | ECS Cluster, Bastion, ECR | Container orchestration, image registry |
| `loaders` | ECS Task Definitions, EventBridge | Data ingestion pipelines (18 loaders) |
| `services` | API Lambda, API Gateway, CloudFront, Cognito | REST API, frontend CDN, authentication |

### Total AWS Resources

- **VPC:** 1 VPC, 4 subnets, 5 security groups, 7 VPC endpoints
- **Database:** 1 RDS PostgreSQL, 3 Secrets Manager secrets, CloudWatch alarms
- **Compute:** 1 ECS cluster, 1 Bastion host, 1 ECR repository
- **Storage:** 6 S3 buckets with lifecycle policies
- **Services:** 1 API Lambda, 1 API Gateway, 1 CloudFront distribution, 1 Cognito pool
- **Scheduling:** 4 EventBridge rules, 1 EventBridge Scheduler schedule
- **IAM:** 8 IAM roles, 12 IAM policies

### Estimated Costs (Monthly)

- VPC: $0 (no NAT Gateway)
- RDS: $20-30 (db.t3.micro)
- ECS: $10-15 (Fargate)
- Lambda: $0-5 (minimal)
- S3: $1-5 (with lifecycle policies)
- CloudFront: $0.085/GB
- Data Transfer: $0-5
- **Total: $65-90/month**

## Troubleshooting

### Issue: "OIDC role not found"

**Solution:** Run the bootstrap CloudFormation stack:
```bash
aws cloudformation deploy \
  --template-file bootstrap/oidc.yml \
  --stack-name stocks-oidc \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

### Issue: "S3 state bucket not found"

**Solution:** The `bootstrap.sh` script creates it automatically. If it fails:
```bash
aws s3 mb s3://stocks-terraform-state --region us-east-1
aws s3api put-bucket-versioning \
  --bucket stocks-terraform-state \
  --versioning-configuration Status=Enabled \
  --region us-east-1
```

### Issue: "DynamoDB lock table doesn't exist"

**Solution:** Create it manually:
```bash
aws dynamodb create-table \
  --table-name stocks-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Issue: "Terraform state is locked"

**Solution:** Check who has it locked and unlock if needed:
```bash
# List locks
aws dynamodb scan --table-name stocks-terraform-locks --region us-east-1

# Force unlock (use with caution!)
terraform force-unlock <lock-id>
```

### Issue: "Variable validation failed"

Check `terraform.tfvars` for invalid values:
- `rds_password` must be 8+ characters
- `environment` must be dev, staging, or prod
- `github_repository` must be in format owner/repo

### Issue: "Module not found"

Re-initialize Terraform:
```bash
cd terraform
rm -rf .terraform/
terraform init -upgrade
```

## Deployment Outputs

After successful deployment, Terraform outputs important values:

```bash
terraform output
```

Key outputs:
- `api_url` - REST API endpoint
- `cloudfront_domain_name` - Frontend CDN domain
- `rds_endpoint` - Database endpoint
- `ecr_repository_url` - Container registry URL
- `ecs_cluster_arn` - ECS cluster ARN

## Rolling Back

If deployment fails and you need to rollback:

```bash
# Option 1: Re-run terraform apply after fixing the issue
git fix bug
git push origin main
# GitHub Actions automatically re-applies

# Option 2: Restore from S3 backup
aws s3 cp s3://stocks-terraform-state/backups/terraform.tfstate.1234567890.backup \
  s3://stocks-terraform-state/dev/terraform.tfstate \
  --region us-east-1

# Option 3: Delete infrastructure entirely
cd terraform
terraform destroy -var="rds_password=YourPassword"
```

## Best Practices

✅ **DO:**
- Always review `terraform plan` output before applying
- Keep `terraform.tfstate` backed up (automatic via GitHub Actions)
- Use meaningful commit messages when updating Terraform
- Monitor CloudWatch alarms after deployment
- Test in dev environment first

❌ **DON'T:**
- Manually modify AWS resources via Console (breaks Terraform state)
- Commit sensitive values (passwords, API keys) to Git
- Delete `.terraform` directory without running `terraform destroy` first
- Share `terraform.tfstate` file (contains sensitive data)

## Maintenance

### Weekly
- Review CloudWatch alarms for breaches
- Check S3 state bucket exists and is versioned

### Monthly
- Review AWS Cost Explorer for unexpected charges
- Audit IAM roles and policies

### Quarterly
- Update AWS provider version (`terraform get -upgrade`)
- Review and update resource configurations
- Test disaster recovery (redeploy from scratch)

## Support

For detailed troubleshooting, see `CLAUDE.md` in the project root, or consult the Terraform AWS provider documentation:
- https://registry.terraform.io/providers/hashicorp/aws/latest

---

**Last Updated:** 2026-05-07
**Status:** Ready for GitHub Actions Deployment

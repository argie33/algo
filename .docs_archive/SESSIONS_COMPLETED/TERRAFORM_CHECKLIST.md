# Terraform Deployment Checklist

## Status: Ready for Deployment ✅

The Terraform infrastructure code is now complete and ready to deploy via GitHub Actions.

## Quick Start (5 Steps)

### Step 1: Set GitHub Secrets

Run these commands from your local machine:

```bash
gh secret set AWS_ACCOUNT_ID --body "626216981288"
gh secret set AWS_ACCESS_KEY_ID --body "your-aws-access-key"
gh secret set AWS_SECRET_ACCESS_KEY --body "your-aws-secret-key"
gh secret set RDS_PASSWORD --body "YourSecurePassword123" # Min 8 characters
gh secret set SLACK_WEBHOOK --body "https://hooks.slack.com/..." # Optional
```

Verify secrets are set:
```bash
gh secret list
```

### Step 2: Create Bootstrap Stack (One-time)

Deploy the OIDC trust relationship for GitHub Actions:

```bash
# Export credentials
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Deploy bootstrap stack
aws cloudformation deploy \
  --template-file bootstrap/oidc.yml \
  --stack-name stocks-oidc \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

Verify the role was created:
```bash
aws iam get-role --role-name github-actions-role --region us-east-1
```

### Step 3: Commit and Push

```bash
git status
git add terraform/ .github/workflows/ TERRAFORM_DEPLOYMENT_GUIDE.md
git commit -m "Infrastructure: finalize Terraform deployment setup"
git push origin main
```

### Step 4: Monitor GitHub Actions

Go to: https://github.com/argeropolos/algo/actions

Watch the "Terraform Apply" workflow:
- Bootstrap AWS prerequisites (S3, DynamoDB)
- Initialize Terraform modules
- Validate configuration
- Plan infrastructure changes
- Apply infrastructure
- Backup state

Deployment time: ~15-20 minutes

### Step 5: Verify Deployment

After successful deployment, verify the infrastructure:

```bash
# Check outputs
aws cloudformation describe-stacks \
  --stack-name stocks-dev \
  --region us-east-1 \
  --query 'Stacks[0].Outputs' \
  --output table

# Check RDS is accessible (via bastion)
aws ssm start-session --target <bastion-instance-id> --region us-east-1
# Inside bastion:
psql -h <rds-endpoint> -U stocks -d stocks

# Check S3 buckets
aws s3 ls --region us-east-1 | grep stocks

# Check ECS cluster
aws ecs list-clusters --region us-east-1
```

## What Gets Deployed

### AWS Resources Created

| Resource Type | Count | Purpose |
|---------------|-------|---------|
| VPC | 1 | Network isolation |
| Subnets | 4 | 2 public + 2 private |
| Security Groups | 5 | Network access control |
| VPC Endpoints | 7 | Private AWS service access |
| RDS Database | 1 | PostgreSQL 15 (db.t3.micro) |
| Secrets Manager | 3 | DB credentials, email config, algo secrets |
| ECS Cluster | 1 | Container orchestration |
| ECS Task Defs | 18 | Data loaders (Fargate) |
| Bastion Host | 1 | SSH access to RDS (auto-shutdown) |
| ECR Repository | 1 | Container image registry |
| S3 Buckets | 6 | Code, data, logs, templates, frontend |
| Lambda Functions | 2 | API + Algo orchestrator |
| API Gateway | 1 | REST API endpoint |
| CloudFront | 1 | Frontend CDN distribution |
| Cognito Pool | 1 | User authentication |
| EventBridge Rules | 4 | Scheduled data loaders |
| EventBridge Schedule | 1 | Algo orchestrator schedule |
| CloudWatch Alarms | 3 | RDS monitoring (CPU, storage, connections) |
| IAM Roles | 8 | GitHub Actions, Bastion, ECS, Lambda |

### Total Infrastructure Cost

**Monthly: $65-90**
- RDS: $20-30
- ECS/Fargate: $10-15
- Lambda: $0-5
- S3 Storage: $1-5
- CloudFront: $0.085/GB
- VPC/Networking: $0 (no NAT Gateway)
- Data Transfer: $0-5

## Files Changed

### Added/Modified
- `terraform/variables.tf` - Added rds_password variable
- `terraform/main.tf` - Use rds_password variable instead of hardcoded value
- `terraform/versions.tf` - Cleaned up comments
- `.github/workflows/terraform-apply.yml` - Added TF_VAR_rds_password
- `.github/workflows/bootstrap.sh` - Verify/create S3 state backend and DynamoDB locks
- `TERRAFORM_DEPLOYMENT_GUIDE.md` - Comprehensive deployment guide

### Ready to Deploy
- All Terraform modules (iam, vpc, storage, database, compute, loaders, services)
- All GitHub Actions workflows (terraform-apply, terraform-plan, etc.)
- All backend configuration (S3 state + DynamoDB locks)

## Troubleshooting

### Error: "Role github-actions-role not found"
**Fix:** Run bootstrap stack first (Step 2)

### Error: "S3 bucket stocks-terraform-state doesn't exist"
**Fix:** The bootstrap.sh script creates it automatically on first run

### Error: "Variable validation failed: rds_password"
**Fix:** RDS password must be 8+ characters. Update the secret:
```bash
gh secret set RDS_PASSWORD --body "NewPassword123"
```

### Error: "Terraform state is locked"
**Fix:** State is locked by another deployment. Wait or force unlock:
```bash
# Check locks
aws dynamodb scan --table-name stocks-terraform-locks

# Force unlock (careful!)
terraform force-unlock <lock-id>
```

## Next Steps After Deployment

1. **Verify Infrastructure**
   - Check all stacks created in CloudFormation
   - Verify RDS is accessible
   - Confirm ECS tasks are running

2. **Configure Services**
   - Set Cognito callback URLs (currently localhost)
   - Configure API Gateway custom domain (optional)
   - Update CloudFront cache behaviors

3. **Deploy Applications**
   - Build and push container images to ECR
   - Deploy loader task definitions
   - Deploy API and Algo Lambda functions

4. **Monitor & Alerts**
   - Check CloudWatch alarms are working
   - Configure SNS email subscriptions
   - Review CloudWatch logs

## Documentation

For detailed information, see:
- `TERRAFORM_DEPLOYMENT_GUIDE.md` - Full deployment guide
- `CLAUDE.md` - Project-wide documentation
- `terraform/README.md` - Module architecture (if present)

## Support

If you encounter issues:
1. Check GitHub Actions logs: https://github.com/argeropolos/algo/actions
2. Review error messages in workflow output
3. Check CloudFormation events: `aws cloudformation describe-stack-events --stack-name stocks-dev`
4. Review Terraform logs: `terraform show tfplan.bin` (after local plan)

---

**Last Updated:** 2026-05-07
**Infrastructure Version:** Terraform 1.5.0+
**AWS Provider Version:** ~5.0

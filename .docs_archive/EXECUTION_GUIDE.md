# Terraform Deployment Execution Guide

## Quick Start (3 Simple Steps)

### Step 1: Commit Code (2 minutes)
```bash
git add .
git commit -m "Add: Terraform cleanup workflow and deployment guides"
git push origin main
```

### Step 2: Clean Up Stale Resources (10 minutes)
```bash
gh workflow run cleanup-stale-resources.yml
# Wait for completion
gh run list --workflow=cleanup-stale-resources.yml --limit 1
```

### Step 3: Deploy Terraform Infrastructure (30-40 minutes)
```bash
gh workflow run terraform-apply.yml
# Monitor deployment
gh run list --workflow=terraform-apply.yml --limit 1 -q
# View logs
gh run view <run-id> --log
```

---

## Expected Results

After ~50 minutes total:
- ✅ VPC with public/private subnets created
- ✅ RDS PostgreSQL database provisioned
- ✅ ECS cluster ready
- ✅ ECR repository created
- ✅ Lambda functions deployed
- ✅ API Gateway configured
- ✅ CloudFront distribution created
- ✅ All CloudWatch logs configured
- ✅ IAM roles and security groups in place

---

## Verify Success

```bash
# Check all resources created
aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs[?Tags[?Value==`stocks`]]' --output table
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus]' --output table
aws ecs list-clusters --region us-east-1 --query 'clusterArns' --output text
aws lambda list-functions --region us-east-1 --query 'Functions[*FunctionName]' --output text
```

---

## If Deployment Fails

1. Check GitHub Actions logs for the specific error
2. Review TERRAFORM_AUDIT_REPORT.md for known issues
3. Fix the Terraform code
4. Commit and push (workflow runs automatically)
5. Or manually trigger: `gh workflow run terraform-apply.yml`

The `rollback-on-failure` job automatically cleans up failed resources.

---

**Timeline:**
- Checkout + Setup: 2 min
- Bootstrap: 3 min
- Init: 3 min
- Validate: 1 min
- Plan: 5 min
- **Apply: 20-30 min** (mostly RDS creation)
- Total: ~45 min

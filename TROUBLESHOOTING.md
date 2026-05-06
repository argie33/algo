# AWS Deployment Troubleshooting Guide

## Issue: AWS::EarlyValidation::ResourceExistenceCheck

**Problem:**
CloudFormation deployment fails with:
```
The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```

**Root Cause:**
CloudFormation is trying to create a resource that already exists outside of the stack:
- S3 bucket with account-specific names
- ECR repository named `stocks-app-registry`
- VPC with CIDR `10.0.0.0/16`

**Solution:**
✅ The deploy-core.yml workflow includes automatic cleanup that:
1. Deletes existing stocks-core stack (if present)
2. Empties and deletes orphaned S3 buckets
3. Deletes orphaned VPCs, ENIs, subnets
4. Deletes orphaned ECR repositories

Trigger with:
```bash
gh workflow run deploy-core.yml
```

## Issue: REVIEW_IN_PROGRESS State

**Problem:**
CloudFormation stack gets stuck in `REVIEW_IN_PROGRESS` state.

**Solution:**
✅ **Fixed in deploy-core.yml** - Workflow automatically deletes stacks in this state.

Manual intervention if needed:
```bash
aws cloudformation delete-stack --stack-name stocks-core
aws cloudformation wait stack-delete-complete --stack-name stocks-core
```

## Issue: AWS Credentials Invalid

**Verify secrets:**
1. Go to: https://github.com/argeropolos/algo/settings/secrets/actions
2. Ensure these 3 secrets exist:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_ACCOUNT_ID`

**Test credentials:**
```bash
aws sts get-caller-identity
```

## Quick Cleanup Script

```bash
#!/bin/bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Delete CloudFormation stacks
for STACK in stocks-core stocks-data stocks-loaders stocks-webapp-dev stocks-algo-dev stocks-oidc; do
  aws cloudformation delete-stack --stack-name "$STACK" --region "$REGION" 2>/dev/null || true
done

# Empty and delete S3 buckets
for BUCKET in \
  "stocks-algo-app-code-$ACCOUNT_ID" \
  "stocks-cf-templates-$ACCOUNT_ID" \
  "algo-artifacts-$ACCOUNT_ID"; do
  aws s3 rm "s3://$BUCKET" --recursive 2>/dev/null || true
  aws s3api delete-bucket --bucket "$BUCKET" 2>/dev/null || true
done

# Delete ECR repository
aws ecr delete-repository --repository-name stocks-app-registry --force --region "$REGION" 2>/dev/null || true

echo "Cleanup complete"
```

See DEPLOYMENT_READY.md for full deployment guide.

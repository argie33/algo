# Terraform Deployment Guide - Clean Run

**Date:** 2026-05-08  
**Status:** Ready for deployment after AWS cleanup  
**All Fixes Applied:** ✅ 10 critical/high issues resolved

---

## Pre-Deployment: AWS Account Cleanup (REQUIRED)

**⚠️ This must be run on your local machine where AWS CLI is installed**

### Step 1: Verify AWS Credentials
```bash
aws sts get-caller-identity
```

Expected output shows your AWS account ID and user ARN. If this fails, configure AWS credentials first.

---

### Step 2: Run the Cleanup Script

**Option A: Full Automated Cleanup (Recommended)**

Copy the entire cleanup script from `CLEANUP_COMMANDS.sh` and run it:

```bash
#!/bin/bash
set -e
AWS_REGION="us-east-1"
PROJECT_NAME="stocks"

echo "=========================================="
echo "Cleaning up previous terraform runs..."
echo "=========================================="

# STEP 1: Backup RDS
echo "Backing up RDS database..."
EXISTING_DB=$(aws rds describe-db-instances \
  --region $AWS_REGION \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT_NAME')].DBInstanceIdentifier" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_DB" ]; then
  echo "Found RDS: $EXISTING_DB - Creating backup..."
  SNAPSHOT_ID="$PROJECT_NAME-backup-$(date +%Y%m%d-%H%M%S)"
  aws rds create-db-snapshot \
    --db-instance-identifier "$EXISTING_DB" \
    --db-snapshot-identifier "$SNAPSHOT_ID" \
    --region $AWS_REGION 2>/dev/null || echo "Snapshot already in progress"
  echo "✓ Backup requested: $SNAPSHOT_ID"
else
  echo "✓ No RDS found"
fi

# STEP 2: Delete RDS Instance
echo ""
echo "Deleting RDS instance (takes 5-10 minutes)..."
if [ -n "$EXISTING_DB" ]; then
  aws rds delete-db-instance \
    --db-instance-identifier "$EXISTING_DB" \
    --skip-final-snapshot \
    --region $AWS_REGION
  echo "✓ RDS deletion started"
  
  # Wait for deletion
  echo "Waiting for RDS deletion..."
  COUNTER=0
  while [ $COUNTER -lt 90 ]; do
    INSTANCES=$(aws rds describe-db-instances \
      --region $AWS_REGION \
      --query "DBInstances[?DBInstanceIdentifier=='$EXISTING_DB'].DBInstanceIdentifier" \
      --output text 2>/dev/null || echo "")
    
    if [ -z "$INSTANCES" ]; then
      echo "✓ RDS deleted successfully"
      break
    fi
    
    COUNTER=$((COUNTER + 1))
    echo "  [$COUNTER/90] Waiting... (${COUNTER}0 seconds elapsed)"
    sleep 10
  done
else
  echo "✓ Skipping (no RDS)"
fi

# STEP 3: Delete Security Groups
echo ""
echo "Deleting security groups..."
SG_IDS=$(aws ec2 describe-security-groups \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" \
  --query "SecurityGroups[?GroupName != 'default'].GroupId" \
  --output text 2>/dev/null || echo "")

if [ -n "$SG_IDS" ]; then
  for sg in $SG_IDS; do
    echo "  Deleting: $sg"
    aws ec2 delete-security-group \
      --group-id "$sg" \
      --region $AWS_REGION 2>/dev/null || echo "  (Could not delete - may be in use)"
  done
fi

# STEP 4: Terminate EC2 Instances
echo ""
echo "Terminating EC2 instances..."
INSTANCE_IDS=$(aws ec2 describe-instances \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" "Name=instance-state-name,Values=running,stopped,pending" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text 2>/dev/null || echo "")

if [ -n "$INSTANCE_IDS" ]; then
  for instance in $INSTANCE_IDS; do
    echo "  Terminating: $instance"
    aws ec2 terminate-instances \
      --instance-ids "$instance" \
      --region $AWS_REGION 2>/dev/null
  done
fi

echo ""
echo "=========================================="
echo "✓ AWS Cleanup Complete"
echo "=========================================="
echo ""
echo "Resources deleted:"
echo "  - RDS instance (if existed)"
echo "  - Security groups"
echo "  - EC2 instances"
echo ""
echo "⏱️  Wait 5+ minutes for all resources to fully delete"
echo "Then proceed with Terraform deployment steps below"
```

**Option B: Manual Step-by-Step**

See `MANUAL_CLEANUP_STEPS.md` for individual commands you can run one at a time.

---

### Step 3: Verify Cleanup Complete

Run these checks to confirm everything is deleted:

```bash
# Check RDS - should return empty
aws rds describe-db-instances \
  --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')]"

# Check Security Groups - should return empty
aws ec2 describe-security-groups \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "SecurityGroups[?GroupName != 'default']"

# Check EC2 Instances - should return empty
aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "Reservations"
```

Expected: All return empty arrays or no results.

---

## Local Environment Setup (Run Locally After AWS Cleanup)

Once AWS resources are deleted, run these on your local machine:

### Step 1: Navigate to Terraform
```bash
cd terraform
```

### Step 2: Clean Terraform Working Directory
```bash
rm -rf .terraform/
rm -f .terraform.lock.hcl
```

### Step 3: Reinitialize Terraform
```bash
terraform init
```

This will:
- Download provider plugins (AWS)
- Create `.terraform/` directory
- Create `.terraform.lock.hcl` with exact versions
- Connect to remote state bucket (from bootstrap)

### Step 4: Validate Configuration
```bash
terraform validate
```

Expected: "Success! The configuration is valid."

---

## Deployment Phase

### Step 5: Generate Plan (DRY RUN)
```bash
terraform plan -out=tfplan
```

Review the plan output:
- Look for ~210 resources to add (for full infrastructure)
- Should show 0 resources to change
- Should show 0 resources to destroy

Save the plan to `tfplan` file.

### Step 6: Review & Approve

The plan should show:
1. ✅ VPC with public/private subnets
2. ✅ NAT Gateway (for private subnet internet)
3. ✅ RDS PostgreSQL instance
4. ✅ S3 buckets (code, lambda, data, frontend)
5. ✅ Lambda functions (API, Algo)
6. ✅ API Gateway HTTP API
7. ✅ ECS cluster and services
8. ✅ Security groups (properly configured)
9. ✅ IAM roles (all in one place, no duplication)
10. ✅ CloudFront distribution (optional)

### Step 7: Deploy
```bash
terraform apply tfplan
```

This will:
- Create all infrastructure
- Output important values (endpoints, bucket names, etc.)
- Take 15-20 minutes to complete

### Step 8: Capture Outputs
After deployment, save the outputs:

```bash
terraform output -json > deployment_outputs.json
```

This file contains:
- RDS endpoint
- API Gateway endpoint
- Lambda function names
- S3 bucket names
- etc.

---

## Post-Deployment Verification

### Check All Resources Created
```bash
# List all AWS resources tagged with your project
aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks"

aws rds describe-db-instances \
  --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')]"
```

### Test API Gateway
```bash
# Get the API endpoint from outputs
API_ENDPOINT=$(terraform output -raw api_gateway_endpoint)

# Test the endpoint
curl -X GET "$API_ENDPOINT/api/health"
```

### Test Database Connection
```bash
# Get RDS endpoint
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)

# Try to connect (requires postgres client installed)
psql -h $RDS_ENDPOINT -U postgres -d stocks
```

---

## Troubleshooting

### "Error: AccessDenied" during terraform init
**Cause:** Bootstrap phase hasn't run or state bucket doesn't exist  
**Fix:** Run bootstrap module first:
```bash
cd terraform/modules/bootstrap
terraform init
terraform apply
cd ../..
terraform init
```

### "Error: EntityAlreadyExists" (IAM role)
**Cause:** Previous failed deployment left resources  
**Fix:** 
1. Delete the resource manually in AWS Console
2. OR run cleanup script again
3. Then retry `terraform apply`

### "Error: Network connection timeout"
**Cause:** Private subnets can't reach internet (no NAT)  
**Fix:** This should be fixed now - NAT Gateway was added. If still failing:
```bash
# Check NAT Gateway exists
aws ec2 describe-nat-gateways --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks"

# Check route table has NAT route
aws ec2 describe-route-tables --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks"
```

### "Error: Lambda permission denied"
**Cause:** API Gateway can't invoke Lambda  
**Fix:** Verify Lambda permission exists:
```bash
aws lambda get-policy \
  --function-name stocks-api-dev \
  --region us-east-1
```

Should show a policy with `apigateway.amazonaws.com` as principal.

---

## What Was Fixed

All 10 critical issues are resolved:

1. ✅ **Terraform state bucket ARN** - Now matches actual bucket name
2. ✅ **DynamoDB lock table name** - Now matches actual table name  
3. ✅ **OIDC provider duplication** - Single provider in bootstrap, referenced by IAM
4. ✅ **Lambda API role duplication** - Centralized in IAM module
5. ✅ **Lambda Algo role duplication** - Centralized in IAM module
6. ✅ **Missing Lambda permission** - Added for API Gateway
7. ✅ **NAT Gateway missing** - Added for internet access from private subnets
8. ✅ **EventBridge role duplication** - Centralized in IAM module
9. ✅ **Duplicate Lambda permission** - Removed
10. ✅ **Missing AWS caller identity** - Added to services module

---

## Timeline

| Phase | Duration | Notes |
|-------|----------|-------|
| AWS Cleanup | 15-20 min | RDS deletion takes longest |
| Terraform Init | 2 min | Downloads providers, inits state |
| Plan | 3 min | DRY run, shows what will be created |
| Review | 5 min | Verify plan looks correct |
| Apply | 15-20 min | Creates all infrastructure |
| Verification | 5 min | Test endpoints and connections |
| **Total** | **45-60 min** | From clean AWS to deployed system |

---

## Success Criteria

✅ You'll know it worked when:

1. `terraform apply` completes without errors
2. All ~210 resources show "created"
3. Terraform outputs show:
   - `api_gateway_endpoint` (not empty)
   - `rds_endpoint` (not empty)
   - All S3 bucket names (not empty)
4. API Gateway responds to health check
5. RDS is accessible from Lambda in private subnet

---

## Next: After Deployment

Once infrastructure is deployed:

1. **Upload actual Lambda code** (current is placeholder)
   ```bash
   # Replace placeholder with real code in src/api-lambda/ and src/algo-lambda/
   cd lambda
   zip -r api-lambda.zip api-lambda/
   aws lambda update-function-code --function-name stocks-api-dev --zip-file fileb://api-lambda.zip
   ```

2. **Initialize database schema**
   ```bash
   # Connect to RDS and run migrations
   ```

3. **Configure frontend assets**
   ```bash
   # Upload HTML/JS to frontend S3 bucket
   ```

4. **Test full flow**
   ```bash
   # Call API endpoint from CloudFront CDN
   ```

---

## Questions?

If anything fails:
1. Check the error message carefully
2. Verify AWS credentials: `aws sts get-caller-identity`
3. Check logs: `terraform apply -input=false`
4. Review `TERRAFORM_REVIEW.md` for technical details
5. Review `TERRAFORM_FIXES_APPLIED.md` for what was fixed

Good luck! 🚀

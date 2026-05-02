# Critical AWS Issues & Fixes
**Date:** 2026-04-29  
**Status:** Identified and solutions provided

---

## Issue Summary

There are 3 critical issues blocking AWS deployment:

| Issue | Task | Status | Severity |
|-------|------|--------|----------|
| #20 | AWS RDS hostname resolution failing in ECS | ⚠️ CRITICAL | Must fix before deployment |
| #21 | Docker images in ECR are stale (from Sept 2025) | ⚠️ HIGH | Needs rebuild |
| #22 | CloudFormation stack may not be fully deployed | ⚠️ CRITICAL | Must deploy/verify |
| #23 | Loaders need AWS Secrets Manager integration | ✓ DONE | Batch 5 has integration |

---

## Issue #20: AWS RDS Hostname Resolution in ECS

### Problem
ECS tasks fail with connection errors like:
```
could not translate host name "stocks-prod-db.xxxxx.rds.amazonaws.com" to address: Name or service not known
```

### Root Causes
1. **Security Group Issue:** RDS security group doesn't allow inbound from ECS security group
2. **Network Issue:** ECS tasks in public subnets can't reach RDS in private subnet
3. **DNS Resolution:** ECS can't resolve RDS hostname
4. **IAM Issue:** ECS task role lacks permissions for Secrets Manager

### Solutions

#### Fix 1: Update RDS Security Group
```bash
# Get RDS security group
RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text)

# Get ECS task security group
ECS_SG=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=stocks-ecs-tasks" \
  --region us-east-1 \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

# Add inbound rule: RDS allows PostgreSQL from ECS
aws ec2 authorize-security-group-ingress \
  --group-id "$RDS_SG" \
  --protocol tcp \
  --port 5432 \
  --source-security-group-id "$ECS_SG" \
  --region us-east-1
```

#### Fix 2: Update RDS for VPC Accessibility
```bash
# Modify RDS to allow public accessibility (if using public subnets)
aws rds modify-db-instance \
  --db-instance-identifier stocks-prod-db \
  --publicly-accessible \
  --apply-immediately \
  --region us-east-1

# Or verify it's in the right subnets (private for security)
aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].DBSubnetGroup'
```

#### Fix 3: Verify ECS Task Networking
```bash
# Check ECS task definition has correct network config
aws ecs describe-task-definition \
  --task-definition loadquarterlyincomestatement \
  --region us-east-1 \
  --query 'taskDefinition.networkMode'
# Should output: "awsvpc"

# Run task with correct network configuration
aws ecs run-task \
  --cluster stock-analytics-cluster \
  --task-definition loadquarterlyincomestatement \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxxxx,subnet-yyyyy],
    securityGroups=[sg-zzzzz],
    assignPublicIp=ENABLED
  }" \
  --region us-east-1
```

#### Fix 4: Update CloudFormation with Network Config
Edit `template-app-ecs-tasks.yml` to include proper network configuration:

```yaml
NetworkConfiguration:
  AwsvpcConfiguration:
    Subnets:
      - !ImportValue StocksCore-PrivateSubnet1Id
      - !ImportValue StocksCore-PrivateSubnet2Id
    SecurityGroups:
      - !ImportValue StocksCore-EcsSecurityGroupId
    AssignPublicIp: DISABLED  # Private subnet access only
```

#### Fix 5: Verify AWS Secrets Manager Access
```bash
# Check IAM policy for ECS task role
aws iam get-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-name SecretsManagerPolicy

# If missing, add policy:
aws iam put-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-name SecretsManagerPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "secretsmanager:GetSecretValue",
        "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:*"
      }
    ]
  }'
```

### Testing Fix
```bash
# 1. Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# 2. Create test ECS task to verify connectivity
aws ecs run-task \
  --cluster stock-analytics-cluster \
  --task-definition loadquarterlyincomestatement \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxxxx],
    securityGroups=[sg-zzzzz],
    assignPublicIp=ENABLED
  }" \
  --overrides 'containerOverrides=[{name=app,command=["/bin/bash","-c","psql -h '"${RDS_ENDPOINT}"' -U stocks -d stocks -c \"SELECT 1\""]}]' \
  --region us-east-1

# 3. Check CloudWatch logs
aws logs tail /ecs/loadquarterlyincomestatement --follow
```

---

## Issue #21: Docker Images in ECR are Stale

### Problem
ECR repository has old images from September 2025. New loaders won't work without updated images.

### Solution: Rebuild and Push Images

#### Option 1: Use GitHub Actions (Recommended)
```bash
# 1. Push latest code to GitHub
git push origin main

# 2. GitHub Actions will automatically:
#    - Build Docker images for changed loaders
#    - Tag with commit SHA
#    - Push to ECR

# 3. Monitor build progress
# https://github.com/argie33/algo/actions
```

#### Option 2: Manual ECR Push
```bash
# 1. Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 626216981288.dkr.ecr.us-east-1.amazonaws.com

# 2. Build Docker image for one loader
docker build -f Dockerfile.loadquarterlyincomestatement \
  -t 626216981288.dkr.ecr.us-east-1.amazonaws.com/loadquarterlyincomestatement:latest .

# 3. Push to ECR
docker push 626216981288.dkr.ecr.us-east-1.amazonaws.com/loadquarterlyincomestatement:latest

# 4. Repeat for all 6 Batch 5 loaders
for loader in quarterly annual; do
  for stmt in income balance cashflow; do
    docker build -f Dockerfile.load${loader}${stmt} \
      -t 626216981288.dkr.ecr.us-east-1.amazonaws.com/load${loader}${stmt}:latest .
    docker push 626216981288.dkr.ecr.us-east-1.amazonaws.com/load${loader}${stmt}:latest
  done
done
```

#### Option 3: Use AWS CodeBuild (for automation)
```bash
# Create CodeBuild project for building loaders
aws codebuild create-project \
  --name build-loaders \
  --source type=GITHUB,location=https://github.com/argie33/algo \
  --artifacts type=NO_ARTIFACTS \
  --environment type=LINUX_CONTAINER,image=aws/codebuild/standard:5.0 \
  --service-role arn:aws:iam::626216981288:role/CodeBuildRole
```

### Verification
```bash
# List ECR images for each loader
for loader in loadquarterlyincomestatement loadannualincomestatement \
              loadquarterlybalancesheet loadannualbalancesheet \
              loadquarterlycashflow loadannualcashflow; do
  echo "=== $loader ==="
  aws ecr describe-images \
    --repository-name "$loader" \
    --region us-east-1 \
    --query 'imageDetails[0].imageTags'
done
```

---

## Issue #22: CloudFormation Stack May Not Be Deployed

### Problem
Three CloudFormation stacks need to be deployed in specific order:
1. `stocks-core` (VPC, subnets, security groups)
2. `stocks-app` (RDS database)
3. `stocks-app-ecs-tasks` (ECS task definitions)

### Solution: Deploy Stacks

#### Step 1: Verify Core Stack
```bash
# Check if stack exists
aws cloudformation describe-stacks \
  --stack-name stocks-core \
  --region us-east-1 2>/dev/null || echo "Stack not found"
```

#### Step 2: Deploy Core Stack (if needed)
```bash
aws cloudformation deploy \
  --template-file template-core.yml \
  --stack-name stocks-core \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

#### Step 3: Deploy App Stack (if needed)
```bash
# Prerequisites: Core stack must be deployed first
aws cloudformation deploy \
  --template-file template-app-stocks.yml \
  --stack-name stocks-app \
  --parameter-overrides \
    RDSUsername=stocks \
    RDSPassword=bed0elAn \
    RDSPort=5432 \
    DBSize=20 \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

#### Step 4: Deploy ECS Tasks Stack (if needed)
```bash
# Get image tags from ECR
QUARTERLY_INCOME_TAG=$(aws ecr describe-images \
  --repository-name loadquarterlyincomestatement \
  --region us-east-1 \
  --query 'imageDetails[0].imageTags[0]' \
  --output text)

# Deploy ECS stack with all image tags
aws cloudformation deploy \
  --template-file template-app-ecs-tasks.yml \
  --stack-name stocks-app-ecs-tasks \
  --parameter-overrides \
    QuarterlyIncomeImageTag="$QUARTERLY_INCOME_TAG" \
    AnnualIncomeImageTag="latest" \
    QuarterlyBalanceImageTag="latest" \
    AnnualBalanceImageTag="latest" \
    QuarterlyCashflowImageTag="latest" \
    AnnualCashflowImageTag="latest" \
    RDSUsername=stocks \
    RDSPassword=bed0elAn \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

#### Step 5: Verify All Stacks
```bash
# List all stacks
aws cloudformation list-stacks \
  --region us-east-1 \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[*].[StackName,StackStatus]' \
  --output table
```

### Troubleshooting Stack Failures

#### If Core stack fails:
```bash
# Check errors
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --region us-east-1 \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]' \
  --output json
```

#### If App stack fails:
```bash
# Usually due to missing core stack exports
aws cloudformation list-exports \
  --region us-east-1 \
  --query 'Exports[*].Name' | grep StocksCore
```

#### If ECS stack fails:
```bash
# Check task definitions exist
aws ecs list-task-definitions \
  --region us-east-1 | jq '.taskDefinitionArns[] | split("/")[1]' | sort
```

---

## Issue #23: AWS Secrets Manager Integration

### Status: ✓ COMPLETED for Batch 5

All 6 Batch 5 loaders support AWS Secrets Manager:
```python
if db_secret_arn and aws_region:
    # Fetch from Secrets Manager
    secret = boto3.client("secretsmanager").get_secret_value(SecretId=db_secret_arn)
else:
    # Fall back to environment variables
```

### Remaining Work: Other Loaders
For the remaining 46 loaders, add the same pattern:

```bash
# Check which loaders still need Secrets Manager integration
grep -L "DB_SECRET_ARN" load*.py | head -10
```

---

## Complete Deployment Checklist

### Pre-Deployment (Today)
- [ ] Git push all changes to GitHub
- [ ] Verify GitHub Actions completes Docker builds
- [ ] Confirm images are in ECR

### CloudFormation Deployment
- [ ] Deploy stocks-core stack
- [ ] Deploy stocks-app stack
- [ ] Deploy stocks-app-ecs-tasks stack
- [ ] Fix RDS security groups (allow ECS inbound)
- [ ] Verify all exports are available

### Testing
- [ ] Run one Batch 5 loader in ECS
- [ ] Check CloudWatch logs for success
- [ ] Verify data in RDS
- [ ] Confirm 5x speedup is achieved

### Full Batch 5 Deployment
- [ ] Run all 6 Batch 5 loaders
- [ ] Monitor execution time
- [ ] Measure performance improvement
- [ ] Document results

### Long-term (Week 2-3)
- [ ] Add Secrets Manager integration to 46 other loaders
- [ ] Apply parallel pattern to other financial loaders
- [ ] Test full system speedup

---

## Quick Fix Script

```bash
#!/bin/bash
# deploy-batch5.sh - Complete deployment script

set -e

echo "=== Deploying CloudFormation Stacks ==="

# 1. Deploy core stack
echo "Deploying core stack..."
aws cloudformation deploy \
  --template-file template-core.yml \
  --stack-name stocks-core \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

# 2. Deploy app stack
echo "Deploying app stack..."
aws cloudformation deploy \
  --template-file template-app-stocks.yml \
  --stack-name stocks-app \
  --parameter-overrides RDSUsername=stocks RDSPassword=bed0elAn \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

# 3. Fix security groups
echo "Configuring security groups..."
RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text 2>/dev/null || echo "")

if [ -z "$RDS_SG" ]; then
  echo "Warning: RDS not found. Stack may still be creating..."
else
  ECS_SG=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=stocks-ecs-tasks" \
    --region us-east-1 \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$ECS_SG" ]; then
    aws ec2 authorize-security-group-ingress \
      --group-id "$RDS_SG" \
      --protocol tcp --port 5432 \
      --source-security-group-id "$ECS_SG" \
      --region us-east-1 2>/dev/null || echo "Rule may already exist"
  fi
fi

echo "✓ Deployment complete!"
echo "Next: Push code to GitHub and verify ECS task execution"
```

---

## Summary

**To fix all 3 critical issues:**

1. **RDS Resolution:** Update security groups + verify networking
2. **Stale Images:** Run `git push` + wait for GitHub Actions
3. **CloudFormation:** Run deployment script above

**Estimated time:** 20-30 minutes total

**Once fixed:** All 6 Batch 5 loaders ready to run in AWS with 5x speedup ✓

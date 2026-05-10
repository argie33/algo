# Manual AWS Resource Cleanup Steps

**AWS CLI is not available in this environment.**

Run these commands on your local machine where AWS CLI is installed (with proper credentials configured).

---

## Quick Start (Copy & Paste)

Run this entire script in one go:

```bash
#!/bin/bash

AWS_REGION="us-east-1"
PROJECT="stocks"

echo "Starting cleanup..."

# 1. Get RDS instance name
DB_ID=$(aws rds describe-db-instances \
  --region $AWS_REGION \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT')].DBInstanceIdentifier" \
  --output text 2>/dev/null)

# 2. Create backup
if [ -n "$DB_ID" ]; then
  echo "Backing up RDS: $DB_ID"
  aws rds create-db-snapshot \
    --db-instance-identifier "$DB_ID" \
    --db-snapshot-identifier "$PROJECT-backup-$(date +%s)" \
    --region $AWS_REGION
fi

# 3. Delete RDS
if [ -n "$DB_ID" ]; then
  echo "Deleting RDS instance: $DB_ID"
  aws rds delete-db-instance \
    --db-instance-identifier "$DB_ID" \
    --skip-final-snapshot \
    --region $AWS_REGION
  echo "Waiting for RDS deletion (5-10 minutes)..."
  sleep 300
fi

# 4. Delete security groups
echo "Deleting security groups..."
SG_IDS=$(aws ec2 describe-security-groups \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT" \
  --query "SecurityGroups[?GroupName != 'default'].GroupId" \
  --output text 2>/dev/null)

for sg in $SG_IDS; do
  echo "Deleting SG: $sg"
  aws ec2 delete-security-group --group-id $sg --region $AWS_REGION 2>/dev/null || true
done

# 5. Terminate EC2 instances
echo "Terminating EC2 instances..."
INSTANCES=$(aws ec2 describe-instances \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text 2>/dev/null)

for instance in $INSTANCES; do
  echo "Terminating: $instance"
  aws ec2 terminate-instances --instance-ids $instance --region $AWS_REGION 2>/dev/null
done

echo "✓ Cleanup complete!"
echo "✓ Resources will finish deleting in 5-10 minutes"
```

---

## Step-by-Step Manual Process

If you prefer to run commands one at a time:

### Step 1: Check for existing RDS
```bash
aws rds describe-db-instances \
  --region us-east-1 \
  --query "DBInstances[*].[DBInstanceIdentifier,Engine,EngineVersion,DBInstanceStatus]" \
  --output table
```

**Expected Output:** Should show `stocks-db` with PostgreSQL 13.7

---

### Step 2: Create RDS Backup (SAFETY)
```bash
aws rds create-db-snapshot \
  --db-instance-identifier stocks-db \
  --db-snapshot-identifier stocks-db-backup-2026-05-08 \
  --region us-east-1
```

**Wait for response:** Should show snapshot being created

---

### Step 3: Delete RDS Instance
```bash
aws rds delete-db-instance \
  --db-instance-identifier stocks-db \
  --skip-final-snapshot \
  --region us-east-1
```

**Expected:** Instance deletion request accepted

---

### Step 4: Wait for Deletion (CRITICAL!)
```bash
# Run this repeatedly until it returns empty result
aws rds describe-db-instances \
  --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')].{ID:DBInstanceIdentifier,Status:DBInstanceStatus}"
```

**Expected:** Returns empty array `[]` when fully deleted
**Time:** 5-10 minutes

---

### Step 5: Delete Security Groups
```bash
# Find security groups
aws ec2 describe-security-groups \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "SecurityGroups[?GroupName != 'default'].GroupId"

# Delete each one (replace GROUP_ID with actual ID)
aws ec2 delete-security-group --group-id GROUP_ID --region us-east-1
```

---

### Step 6: Verify Cleanup
```bash
# Should all return empty or only default SG
aws ec2 describe-security-groups \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "SecurityGroups[?GroupName != 'default']"

aws rds describe-db-instances \
  --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')]"

aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name:tag:Project,Values=stocks" \
  --query "Reservations[*].Instances"
```

**Expected:** All empty

---

## Common Issues & Fixes

### "Access Denied" Error
```
Error: User is not authorized to perform this action
```
**Fix:** Check your AWS credentials are configured
```bash
aws sts get-caller-identity
```

### "RDS Instance Not Found"
```
Error: DBInstance not found
```
**Fix:** It's already deleted (good!) or doesn't exist

### "Cannot Delete Security Group (in use)"
```
Error: resource is still referenced
```
**Fix:** Wait longer for RDS and EC2 to fully terminate, then retry

### "Snapshot Already Exists"
```
Error: DB snapshot already exists
```
**Fix:** That's OK, cleanup will still work

---

## Verification Checklist

After running cleanup, verify with:

```bash
# Check: No RDS instances with "stocks" in name
aws rds describe-db-instances --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')]" | jq 'length'
# Expected: 0

# Check: No EC2 instances with Project=stocks tag
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "Reservations" | jq 'length'
# Expected: 0

# Check: No security groups with Project=stocks tag (except default)
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query "SecurityGroups[?GroupName != 'default']" | jq 'length'
# Expected: 0
```

---

## Timeline

| Phase | Duration |
|-------|----------|
| Backup creation | 5 min |
| RDS deletion | 10 min |
| Wait | 5 min |
| SG deletion | 2 min |
| Verification | 2 min |
| **Total** | **~25 min** |

---

## Next: After Cleanup Completes

Once all resources are deleted:

```bash
cd terraform

# Reset terraform
rm -rf .terraform/
rm -f .terraform.lock.hcl

# Reinitialize
terraform init

# Validate
terraform validate

# Plan
terraform plan -out=tfplan

# Review plan (should show ~210 to add, 0 to change)

# Deploy
terraform apply tfplan
```

---

## Need Help?

If anything fails:
1. Check the error message carefully
2. Verify AWS credentials: `aws sts get-caller-identity`
3. Check CloudWatch for any hanging resources
4. Review `DEPLOYMENT_FAILURE_ANALYSIS.md` for more details

# 🔴 Terraform Deployment Failure - Recovery Plan

**Status:** Failure Analysis Complete  
**Root Causes Found:** 2 blocking issues  
**Cleanup Required:** YES (BEFORE retrying)

---

## 📋 Summary of Issues

### Issue #1: RDS Version Conflict
- **What Happened:** Previous deployment created RDS with PostgreSQL 13.7
- **What Terraform Wants:** PostgreSQL 15.3 (with postgres15 parameter group)
- **Why It Fails:** Can't change engine version inline - requires delete/recreate
- **Block Status:** ❌ BLOCKS `terraform apply`

### Issue #2: EC2 Capacity Exhausted
- **What Happened:** t3.micro not available in us-east-1b
- **Current Setting:** bastion_enabled = false (GOOD - won't be created)
- **If Bastion Enabled:** Would fail on EC2 capacity constraint
- **Block Status:** ✅ OK (because bastion disabled)

---

## 🧹 CLEANUP PROCEDURE (MUST DO FIRST)

### Phase 1: Backup Data (5 minutes)
```bash
# Create RDS snapshot (in case we need data later)
aws rds create-db-snapshot \
  --db-instance-identifier stocks-db \
  --db-snapshot-identifier stocks-db-final-backup-2026-05-08 \
  --region us-east-1

# Wait for completion
aws rds describe-db-snapshots \
  --db-snapshot-identifier stocks-db-final-backup-2026-05-08 \
  --region us-east-1 \
  --query 'DBSnapshots[0].Status'
```

**Expected:** Should show `available` within 5 minutes.

### Phase 2: Delete Conflicting Resources (10 minutes)
```bash
# DELETE the conflicting RDS instance
aws rds delete-db-instance \
  --db-instance-identifier stocks-db \
  --skip-final-snapshot \
  --region us-east-1

# DELETE EC2 instances (if any)
INSTANCES=$(aws ec2 describe-instances \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'Reservations[*].Instances[*].InstanceId' \
  --output text)

if [ -n "$INSTANCES" ]; then
  aws ec2 terminate-instances --instance-ids $INSTANCES --region us-east-1
fi
```

**Expected:** Resources deleted within 10 minutes.

### Phase 3: Clean Up Security Groups (5 minutes)
```bash
# Wait for EC2 to terminate
sleep 60

# DELETE security groups
SG_IDS=$(aws ec2 describe-security-groups \
  --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'SecurityGroups[?GroupName != `default`].GroupId' \
  --output text)

for sg in $SG_IDS; do
  aws ec2 delete-security-group --group-id $sg --region us-east-1 2>/dev/null || true
done
```

**Expected:** Security groups deleted.

### Phase 4: Verify Cleanup (2 minutes)
```bash
# Verify NO resources remain
echo "=== RDS Instances ==="
aws rds describe-db-instances --region us-east-1 \
  --query "DBInstances[?contains(DBInstanceIdentifier, 'stocks')].DBInstanceIdentifier"

echo "=== EC2 Instances ==="
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'Reservations[*].Instances[*].InstanceId' --output text

echo "=== Security Groups ==="
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'SecurityGroups[?GroupName != `default`].GroupId' --output text
```

**Expected:** All should return EMPTY (no resources found).

---

## 🔧 FIXES TO APPLY

### Fix #1: Verify Bastion is Disabled ✅
**File:** `terraform/variables.tf`  
**Current:** `bastion_enabled = false`  
**Status:** ✅ Already correct - no change needed

### Fix #2: Verify RDS Configuration ✅
**File:** `terraform/modules/database/main.tf`  
**Current:** `engine_version = "15.3"` with `postgres15` parameter group  
**Status:** ✅ Already correct - no change needed

### Fix #3: Clear Terraform Cache
**File:** `.terraform/` directory  
**Action:** Delete and reinitialize
```bash
cd terraform
rm -rf .terraform/
rm -f .terraform.lock.hcl
terraform init
```

---

## 📝 Re-Deployment Procedure

### Step 1: Cleanup (20 minutes total)
```bash
# Run the automated cleanup script
bash cleanup-aws-resources.sh

# Verify cleanup complete
echo "Checking AWS resources..."
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'Reservations' | jq 'length'
# Expected: 0
```

### Step 2: Terraform Reset (5 minutes)
```bash
cd terraform

# Clear cache
rm -rf .terraform/
rm -f .terraform.lock.hcl
rm -f tfplan

# Reinitialize
terraform init

# Validate
terraform validate
```

**Expected:** `Success! The configuration is valid.`

### Step 3: Generate Plan (10 minutes)
```bash
terraform plan \
  -var="bastion_enabled=false" \
  -var="environment=dev" \
  -out=tfplan
```

**Expected Output:**
```
Plan: 210 to add, 0 to change, 0 to destroy
```

**What should appear in plan:**
- ✅ S3 bucket: stocks-terraform-state-dev
- ✅ DynamoDB table: stocks-terraform-locks
- ✅ VPC, subnets, security groups
- ✅ RDS PostgreSQL 15.3 (NEW)
- ✅ ECS cluster
- ✅ Lambda functions
- ✅ API Gateway
- ✅ CloudFront

**What should NOT appear:**
- ❌ Bastion EC2 instance (bastion_enabled=false)
- ❌ Any "destroy" operations

### Step 4: Manual Review (5 minutes)
```bash
# Review the plan file
terraform show tfplan | head -100

# Specifically verify:
# 1. RDS engine is 15.3
# 2. No bastion instance
# 3. VPC in us-east-1 with azs us-east-1a and us-east-1b
# 4. No "destroy" operations
```

### Step 5: Deploy (20 minutes)
```bash
terraform apply tfplan
```

**What to watch for:**
- ✅ Bootstrap module creates state bucket
- ✅ State migrates from local to S3
- ✅ Resources created sequentially
- ✅ RDS database created and initialized
- ✅ No permission denied errors
- ✅ No capacity errors
- ✅ All resources in "Created" state

**If error occurs:**
```bash
# Check what went wrong
terraform state list

# If specific module failed, destroy just that
terraform destroy -target=module.compute  # for example
terraform apply tfplan
```

---

## ✅ Success Criteria

Deployment is **successful** when:

```
✅ terraform apply completed without errors
✅ AWS outputs shown (API endpoint, CloudFront domain, RDS endpoint)
✅ All 210+ resources created
✅ RDS instance: stocks-db (PostgreSQL 15.3)
✅ ECS cluster: stocks-ecs-dev
✅ State file: s3://stocks-terraform-state-dev/dev/terraform.tfstate
✅ No bastion EC2 instance created
```

---

## 🚨 If Deployment Fails Again

### Immediate Actions
```bash
# 1. Check what failed
terraform state list
terraform state show <failed_resource>

# 2. Get AWS error
aws ec2 describe-instances --filters "Name=tag:Project,Values=stocks" --region us-east-1
aws rds describe-db-instances --region us-east-1

# 3. Check CloudWatch logs
aws logs describe-log-groups --region us-east-1 | grep stocks

# 4. View terraform debug
export TF_LOG=DEBUG
terraform apply tfplan 2>&1 | tee terraform-debug.log
```

### Recovery Options
```bash
# Option A: Destroy specific failed module
terraform destroy -target=module.database
terraform apply tfplan

# Option B: Destroy everything and start fresh
terraform destroy -auto-approve
# Then repeat entire procedure from cleanup step

# Option C: Check AWS console for stuck resources
# Delete manually from AWS console, then retry terraform apply
```

---

## 📚 Documentation

- `DEPLOYMENT_FAILURE_ANALYSIS.md` - Detailed root cause analysis
- `cleanup-aws-resources.sh` - Automated cleanup script
- `TERRAFORM_VALIDATION_CHECKLIST.md` - Validation reference
- `DEPLOYMENT_READY.md` - Deployment reference

---

## ⏱️ Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Cleanup | 20 min | Must complete first |
| Terraform Reset | 5 min | Then do this |
| Plan | 10 min | Review carefully |
| Deploy | 20 min | Monitor closely |
| **Total** | **55 min** | |

---

## 🎯 Next Steps

1. ✅ **Read this entire document** (2 min)
2. ✅ **Run cleanup script** (20 min)
3. ✅ **Reset Terraform** (5 min)
4. ✅ **Generate plan** (10 min)
5. ✅ **Review plan** (5 min)
6. ✅ **Deploy** (20 min)
7. ✅ **Verify success** (5 min)

**TOTAL TIME: ~1 hour**

---

**IMPORTANT: Do NOT attempt to re-deploy until cleanup is complete!**

Start with the cleanup script, then follow the re-deployment procedure step-by-step.

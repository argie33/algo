# Terraform Deployment Failure Analysis

**Date:** 2026-05-08  
**Status:** Investigating root causes

---

## Issues Identified

### 🔴 ISSUE 1: RDS PostgreSQL Version Mismatch

**Error:** Conflict between existing RDS (13.7) and Terraform config (15.3)

**Root Cause:** 
- Existing RDS instance in AWS: PostgreSQL 13.7 (from previous failed deployment)
- Terraform configuration: PostgreSQL 15.3 (postgres15 parameter group)
- Terraform cannot upgrade DB engine in-place for some parameter groups

**Location:** 
- Database module: `terraform/modules/database/main.tf` line 29
- Parameter group: `postgres15` family (line 94)

**Impact:** ❌ Blocks terraform apply

**Fix Options:**
1. **DESTROY existing DB** (data loss) - Delete the RDS instance, let Terraform recreate
2. **CHANGE parameter group** - Downgrade to postgres13, let terraform manage
3. **SKIP DB creation** - Disable database module in variables, create manually later
4. **FORCE UPDATE** - Use AWS CLI to upgrade DB offline, then retry terraform

**Recommended:** Option 1 (Destroy & Recreate) since this is dev environment

---

### 🔴 ISSUE 2: EC2 Capacity Not Available

**Error:** AWS doesn't have `t3.micro` capacity in `us-east-1b`

**Root Cause:**
- Default bastion instance type: `t3.micro` (too small, capacity exhausted)
- Availability zone: `us-east-1b` (has no t3.micro available)
- Bastion might be created even though `bastion_enabled = false`

**Location:**
- Root variables: `terraform/variables.tf`
- Compute module: `terraform/modules/compute/variables.tf` line 110

**Impact:** ❌ EC2 launch fails if bastion is created

**Fix Options:**
1. **Use larger instance** - Change from `t3.micro` to `t3.small` (more reliable availability)
2. **Use different instance family** - Switch to `t4g.micro` (Graviton, different pool)
3. **Disable bastion** - Set `bastion_enabled = false` (already default)
4. **Use single AZ** - Change availability zones to just `us-east-1a`

**Recommended:** Option 3 (disable bastion) since it's not needed for initial deployment

---

## Cleanup Checklist

### Step 1: Identify Existing AWS Resources

```bash
# List RDS instances
aws rds describe-db-instances --region us-east-1 --query 'DBInstances[*].DBInstanceIdentifier'

# List EC2 instances
aws ec2 describe-instances --region us-east-1 --query 'Reservations[*].Instances[*].[InstanceId,State.Name,InstanceType]'

# List Terraform state bucket
aws s3 ls s3://stocks-terraform-state-dev/ 2>/dev/null || echo "State bucket may not exist"

# List incomplete resources (security groups, etc)
aws ec2 describe-security-groups --region us-east-1 --filters "Name=tag:Project,Values=stocks" --query 'SecurityGroups[*].[GroupId,GroupName,Tags[?Key==`Name`].Value|[0]]'
```

### Step 2: Delete Conflicting RDS Instance

```bash
# BACKUP first (critical!)
aws rds create-db-snapshot \
  --db-instance-identifier stocks-db \
  --db-snapshot-identifier stocks-db-backup-2026-05-08

# Wait for snapshot to complete
aws rds describe-db-snapshots \
  --db-snapshot-identifier stocks-db-backup-2026-05-08 \
  --query 'DBSnapshots[0].Status'

# DELETE the conflicting instance
aws rds delete-db-instance \
  --db-instance-identifier stocks-db \
  --skip-final-snapshot
```

### Step 3: Delete Partial Terraform Resources

```bash
# List all Terraform-managed resources
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:ManagedBy,Values=terraform" \
  --query 'Reservations[*].Instances[*].InstanceId' \
  --output text | xargs -I {} aws ec2 terminate-instances --instance-ids {} --region us-east-1

# Delete security groups
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:ManagedBy,Values=terraform" \
  --query 'SecurityGroups[*].GroupId' \
  --output text | while read sg; do
    aws ec2 delete-security-group --group-id $sg --region us-east-1 2>/dev/null || true
  done

# Delete VPC (if exists)
aws ec2 describe-vpcs --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'Vpcs[*].VpcId' \
  --output text | while read vpc; do
    # First delete associated resources
    aws ec2 describe-internet-gateways --region us-east-1 \
      --filters "Name=attachment.vpc-id,Values=$vpc" \
      --query 'InternetGateways[*].InternetGatewayId' \
      --output text | while read igw; do
        aws ec2 detach-internet-gateway --internet-gateway-id $igw --vpc-id $vpc --region us-east-1
        aws ec2 delete-internet-gateway --internet-gateway-id $igw --region us-east-1
      done
    # Delete VPC
    aws ec2 delete-vpc --vpc-id $vpc --region us-east-1 2>/dev/null || true
  done
```

### Step 4: Clean Terraform State

```bash
# ONLY if state bucket exists and has partial state
aws s3 rm s3://stocks-terraform-state-dev/dev/terraform.tfstate --region us-east-1 2>/dev/null || echo "State file doesn't exist (OK)"

# CAUTION: This removes ALL history
# Better option: Keep state but remove specific resources
```

### Step 5: Verify Cleanup

```bash
# Verify no resources remain
aws ec2 describe-instances --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" \
  --query 'Reservations[*].Instances' | jq 'length'
# Expected: 0

# Verify security groups deleted
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=tag:Project,Values=stocks" | jq '.SecurityGroups | length'
# Expected: 0 (default SG may remain, that's OK)

# Verify RDS deleted
aws rds describe-db-instances --region us-east-1 \
  --query 'DBInstances[?contains(DBInstanceIdentifier, `stocks`)].DBInstanceIdentifier'
# Expected: []
```

---

## Fixes to Apply

### Fix 1: Verify RDS Configuration

File: `terraform/modules/database/main.tf`

**Current:**
```
engine_version       = "15.3"
...
parameter_group_name   = "postgres15"
```

**Status:** ✅ Correct - PostgreSQL 15.3 with matching parameter group

**No change needed.**

---

### Fix 2: Disable Bastion (Not Needed)

File: `terraform/variables.tf`

**Current:**
```
variable "bastion_enabled" {
  default = false
}
```

**Status:** ✅ Already disabled

**Ensure terraform init is called with:**
```bash
terraform apply -var="bastion_enabled=false"
```

---

### Fix 3: Change Instance Type (Fallback)

File: `terraform/modules/compute/variables.tf` 

**IF bastion is enabled**, change from `t3.micro` to `t3.small`:

```hcl
variable "bastion_instance_type" {
  default     = "t3.small"  # Changed from t3.micro
  # ... rest of config
}
```

**Alternative:** Use `t3.nano` for cost, but less reliable availability

---

## Deployment Sequence (Fixed)

### 1. Clean Up (FIRST - MUST DO)

```bash
# Run cleanup script (from Step 1-5 above)
./cleanup.sh
```

### 2. Remove Terraform Lock (if needed)

```bash
# Delete DynamoDB lock if process hangs
aws dynamodb delete-item \
  --table-name stocks-terraform-locks \
  --key '{"LockID":{"S":"stocks-terraform-state-dev/dev/terraform.tfstate"}}' \
  --region us-east-1 2>/dev/null || echo "No lock entry (OK)"
```

### 3. Re-Initialize Terraform

```bash
cd terraform

# Remove cached terraform state
rm -rf .terraform/

# Fresh init (will download modules, refresh state)
terraform init

# Validate
terraform validate
```

### 4. Plan (with explicit overrides)

```bash
terraform plan \
  -var="bastion_enabled=false" \
  -var="environment=dev" \
  -var="project_name=stocks" \
  -out=tfplan
```

### 5. Apply (after review)

```bash
terraform apply tfplan
```

---

## Success Criteria

After cleanup and applying fixes:

✅ No RDS version conflicts  
✅ No EC2 capacity errors  
✅ All resources created successfully  
✅ State stored in S3: `stocks-terraform-state-dev/dev/terraform.tfstate`  
✅ All 210+ resources in "Created" state  

---

## Rollback if Still Fails

If deployment fails again:

```bash
# Check what failed
terraform show

# Destroy just the failed module
terraform destroy -target=module.database  # or module.compute, etc

# Fix the issue
# ... apply fix ...

# Re-apply
terraform apply tfplan
```

---

## Next Steps

1. **Run cleanup immediately** - Delete conflicting AWS resources
2. **Verify variables** - Ensure bastion_enabled=false
3. **Run terraform init fresh** - Clear any cached state
4. **Generate plan** - Review what will be created
5. **Apply** - Deploy with correct configuration

⚠️ **DO NOT attempt deployment until cleanup is complete!**

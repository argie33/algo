# Terraform Deployment Troubleshooting Guide

**Status:** Ready for issues. We will encounter problems. This is how we fix them.

## Expected Issues & Solutions

### Category 1: Secret/Variable Issues

**Problem: "Error: The argument 'db_password' is required"**
```
Solution:
1. Verify DB_PASSWORD secret exists in GitHub
2. Check workflow passes it as TF_VAR_db_password
3. Run: terraform apply -var="db_password=XXXX"
```

**Problem: "Invalid or missing AWS credentials"**
```
Solution:
1. Check AWS_ACCESS_KEY_ID secret
2. Check AWS_SECRET_ACCESS_KEY secret
3. Verify they're not expired (check AWS console)
4. Test locally: aws sts get-caller-identity
```

**Problem: "Argument must be a string"**
```
Cause: Variable type mismatch
Solution:
1. Check variable type in variables.tf
2. Ensure secret value is correct format
3. For numbers: use tonumber() if needed
```

---

### Category 2: Cross-Module References

**Problem: "Error: Unsupported attribute reference"**
```
Example Error:
Error: Unsupported attribute reference

on main.tf line 45, in module "core":
  resource name "module.bootstrap[0].invalid_output"

Available outputs are: oidc_provider_arn, github_deploy_role_arn
```

**Solution:**
1. Check what outputs module actually has
2. Read module's outputs.tf file
3. Use correct output name

**Fix Map:**
```
module.core[0].vpc_id                    ✓ Correct
module.core.vpc_id                       ✗ Missing [0] index
module.core[0].wrong_output_name         ✗ Doesn't exist
```

**Problem: "Error: resource does not have an attribute"**
```
Cause: Trying to reference non-existent output
Solution: Check outputs.tf for exact name
```

---

### Category 3: IAM Permission Issues

**Problem: "User: arn:aws:iam::... is not authorized"**
```
Solution:
1. Which action failed? (ec2:CreateVpc, rds:CreateDBInstance, etc.)
2. Add that action to IAM policy
3. Wait 1-2 minutes for policy to propagate
4. Retry terraform apply
```

**Problem: "AccessDenied: User is not authorized to perform: sts:AssumeRole"**
```
Solution:
1. Remove OIDC role assumption from workflow (we use static creds)
2. Use AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY only
3. Already fixed in current workflow
```

---

### Category 4: Terraform State Issues

**Problem: "Error: resource already exists in AWS but not in state"**
```
Example: VPC vpc-12345678 exists but terraform doesn't know about it

Solution:
1. Import the resource: terraform import aws_vpc.main vpc-12345678
2. Or: Delete from AWS and re-create
3. Or: Manually delete resource from state file
```

**Problem: "Terraform state is locked"**
```
Cause: Previous apply didn't complete cleanly
Solution:
1. Check if any other apply is running
2. If not: terraform force-unlock LOCK_ID
3. Retry apply
```

**Problem: "Error: resource does not exist"**
```
Cause: Trying to destroy something already gone
Solution:
1. Remove from state: terraform state rm aws_vpc.main
2. Continue with apply
```

---

### Category 5: AWS Resource Issues

**Problem: "Error: VPC already exists with CIDR 10.0.0.0/16"**
```
Cause: Stuck resource from previous CloudFormation attempt
Solution:
1. Delete in AWS Console: EC2 → VPCs
2. Delete ENIs, security groups manually if needed
3. Retry terraform apply
```

**Problem: "Error: RDS creation timeout"**
```
Cause: RDS takes 15+ minutes to create
Solution:
1. This is NORMAL
2. Let it continue
3. Or: Check AWS Console → RDS → Databases
4. If stuck for 30+ min, delete and retry
```

**Problem: "Error: S3 bucket name already exists"**
```
Cause: Bucket naming collision (bucket names are globally unique)
Solution:
1. Change bucket name in template: add suffix or timestamp
2. Or: Delete old bucket in AWS Console
3. S3 buckets have 24-hour retention after deletion
```

**Problem: "Error: Security Group already exists"**
```
Cause: Leftover from failed deployment
Solution:
1. Delete in AWS Console
2. Wait 10 seconds (AWS needs time to detach)
3. Retry apply
```

---

### Category 6: Network/Subnet Issues

**Problem: "Error: Invalid CIDR block"**
```
Cause: Overlapping subnets or invalid CIDR
Solution:
1. Check vpc_cidr, public_subnet_cidrs, private_subnet_cidrs
2. Ensure all are valid and non-overlapping
3. Example (WRONG):
   vpc_cidr = "10.0.0.0/16"
   subnet = "10.1.0.0/24"  ← Outside VPC CIDR!
```

**Problem: "Error: No availability zones found"**
```
Cause: Region doesn't have AZs (wrong region)
Solution:
1. Check AWS_REGION environment variable
2. Verify region is valid (us-east-1, us-west-2, etc.)
3. Set correct region
```

---

### Category 7: Module/Count Issues

**Problem: "Error: resource index out of range"**
```
Example: module.core[1].vpc_id but we only created module.core[0]
Cause: Conditional deployment failed silently
Solution:
1. Check if deploy_core = true in variables
2. Check if deploy_bootstrap = true (bootstrap must deploy first)
3. Check depends_on relationships
```

**Problem: "Error: Cannot use count in this context"**
```
Cause: Syntax error in conditional
Solution:
1. Check count = var.deploy_X ? 1 : 0 syntax
2. Ensure variable exists and is boolean
3. Ensure conditional is in right location
```

---

## Real-Time Debugging Steps

### Step 1: Get Full Error Output
```bash
# From workflow logs, copy FULL error message
# Include:
# - Error type (InvalidParameterValue, AccessDenied, etc.)
# - Resource it failed on
# - Full stack trace
```

### Step 2: Understand What Failed
```
Question: Which module failed?
Answer: bootstrap / core / data-infrastructure / loaders / webapp / algo

Question: Which resource type?
Answer: aws_vpc / aws_rds_instance / aws_ecs_cluster / etc.

Question: What was the action?
Answer: CreateVpc / ModifyDBInstance / etc.
```

### Step 3: Check State vs AWS

**Local state:**
```bash
terraform state list | grep failed-resource
terraform state show aws_vpc.main
```

**AWS console:**
```bash
aws ec2 describe-vpcs --region us-east-1
aws rds describe-db-instances --region us-east-1
aws ecs describe-clusters --region us-east-1
```

**Are they in sync?**
- ✓ Resource in both → Likely transient error, retry
- ✗ In AWS but not state → Import resource
- ✗ In state but not AWS → Remove from state
- ✗ In neither → Create fresh

### Step 4: Identify Root Cause Category

**Is it a:**
- [ ] Variable/secret issue? → Check inputs
- [ ] IAM permission? → Add to policy
- [ ] Cross-module reference? → Check outputs.tf
- [ ] Resource conflict? → Delete and recreate
- [ ] Timeout? → Increase timeout or retry
- [ ] Invalid configuration? → Fix HCL syntax

### Step 5: Apply Fix

**Don't try to fix in state.** Instead:

```bash
# Option 1: Delete and recreate
terraform destroy -target=aws_vpc.main
terraform apply

# Option 2: Import existing resource
terraform import aws_vpc.main vpc-12345678

# Option 3: Update configuration
# Edit terraform code → git push → workflow re-runs

# Option 4: Update variable
terraform apply -var="vpc_cidr=10.1.0.0/16"
```

---

## Debugging Checklist

Before saying "it's broken," verify:

- [ ] All 4 secrets exist in GitHub: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, DB_PASSWORD, NOTIFICATION_EMAIL
- [ ] AWS account ID is correct: 626216981288
- [ ] All module outputs referenced exist in their outputs.tf files
- [ ] All module inputs are provided from parent module or are optional
- [ ] No circular dependencies (A depends on B, B depends on A)
- [ ] All variable types match (string vs number vs list)
- [ ] No hardcoded AWS resource IDs (should use variables/outputs)
- [ ] VPC CIDR doesn't overlap with other VPCs in account
- [ ] Subnet CIDRs are within VPC CIDR
- [ ] IAM policy includes all actions used by resources
- [ ] No resources with same name in same region

---

## Common Patterns We'll Fix

### Pattern 1: Missing Secret
```
Error: expected db_password to be set

Fix:
1. Check GitHub Secrets has DB_PASSWORD
2. Check workflow exports it as TF_VAR_db_password
3. Check variable definition accepts it
```

### Pattern 2: Module Not Deploying
```
Error: module.core[0] does not exist

Fix:
1. Check deploy_core = true
2. Check bootstrap deployed first (depends_on)
3. Check no errors in bootstrap
```

### Pattern 3: Output Name Typo
```
Error: unsupported attribute vpc_id

Fix:
1. Check outputs.tf for exact name: vpc_id or VpcId?
2. Update reference in main.tf
3. Grep for all instances of typo
```

### Pattern 4: Permission Denied
```
Error: User is not authorized to perform ec2:CreateVpc

Fix:
1. Add ec2:CreateVpc to IAM policy
2. Wait 2 minutes
3. Retry
```

### Pattern 5: Resource Already Exists
```
Error: InvalidParameterValue: Resource already exists

Fix:
1. Delete in AWS Console
2. Or: terraform import to state
3. Or: Change name/CIDR to avoid conflict
```

---

## When to Escalate

If error persists after 3 attempts:

1. **Check AWS Console directly**
   - Does resource exist? Where?
   - What state is it in?
   - Any error messages?

2. **Review terraform.tfstate**
   - What does local state think exists?
   - Does it match AWS?

3. **Check CloudTrail logs**
   - What API calls were made?
   - Which one failed and why?

4. **Nuclear option**
   ```bash
   # Destroy everything and start fresh
   terraform destroy -auto-approve
   # Wait 5 minutes
   terraform apply
   ```

---

## Prevention Strategies

### Before Deployment
- [ ] Run `terraform validate` (workflow does this)
- [ ] Run `terraform plan` and review (workflow does this)
- [ ] Check all variables are set
- [ ] Verify module outputs are actually defined

### During Deployment
- [ ] Monitor workflow logs in real-time
- [ ] Screenshot any error messages
- [ ] Note the exact resource that failed
- [ ] Check AWS Console simultaneously

### After Issues
- [ ] Document what happened
- [ ] Document what fixed it
- [ ] Update this guide with new patterns
- [ ] Prevent recurrence

---

## Quick Reference: Error → Solution

| Error Message | Likely Cause | Solution |
|---|---|---|
| "expected X to be set" | Missing secret/variable | Check GitHub Secrets |
| "unsupported attribute" | Typo in output name | Check outputs.tf |
| "is not authorized" | Missing IAM permission | Add action to policy |
| "already exists" | Leftover resource | Delete in AWS Console |
| "does not exist" | Resource deleted outside TF | `terraform import` or delete from state |
| "timeout" | Too slow (RDS) | Wait longer or check AWS Console |
| "invalid CIDR" | Configuration error | Check vpc_cidr vs subnet cidrs |
| "dependency cycle" | Circular references | Fix depends_on |
| "module not found" | Conditional deploy failed | Check deploy_X = true |

---

## We Will Fix These Together

I'm ready to:
1. ✅ Read workflow error logs
2. ✅ Identify root cause
3. ✅ Propose fix (code edit or AWS cleanup)
4. ✅ Test fix
5. ✅ Verify success

**Just send me the error message and I'll diagnose it.**

---

**Last Updated:** 2026-05-06
**Status:** Ready for battle
**Attitude:** Expect issues, fix systematically, document learnings

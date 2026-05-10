# AWS Cleanup & Terraform Deployment Plan

## Phase 1: AWS Resource Cleanup (Dependency Order)

### Why This Order Matters
AWS resources have dependencies that must be respected during deletion:
- Launch Templates used by Auto Scaling Groups → delete ASG first
- DB Subnet Groups used by RDS instances → delete RDS first or keep empty
- IAM Roles with inline policies → delete policies before removing role
- Terraform state → delete last so we track what was removed

### Cleanup Steps (Execute in Order)

#### Step 1: Delete EC2 Launch Templates
```bash
aws ec2 delete-launch-template \
  --launch-template-name stocks-bastion-lt \
  --region us-east-1
```
**Why:** May be referenced by Auto Scaling Groups or older stack attempts.

#### Step 2: Delete RDS DB Subnet Group (if empty)
```bash
aws rds delete-db-subnet-group \
  --db-subnet-group-name stocks-db-subnet-group \
  --region us-east-1
```
**Why:** Can only be deleted if no RDS instances use it. If it fails, skip — RDS still needs it.

#### Step 3: Delete EventBridge IAM Role
```bash
# First list all inline policies
aws iam list-role-policies --role-name stocks-eventbridge-run-task-role

# Delete each inline policy found
aws iam delete-role-policy \
  --role-name stocks-eventbridge-run-task-role \
  --policy-name <policy-name>

# Then delete the role
aws iam delete-role \
  --role-name stocks-eventbridge-run-task-role
```
**Why:** IAM roles must have all inline policies removed before deletion.

#### Step 4: Delete Terraform State (if starting fresh)
```bash
aws s3 rm s3://stocks-terraform-state/dev/terraform.tfstate --region us-east-1
```
**Why:** Only do this if you want Terraform to think it's deploying from scratch. Normally, you'd keep state.

### Alternative: Use AWS Console
If CLI access is limited, use AWS Management Console:
1. EC2 → Launch Templates → Select `stocks-bastion-lt` → Delete
2. RDS → Subnet Groups → Select `stocks-db-subnet-group` → Delete (if empty)
3. IAM → Roles → Select `stocks-eventbridge-run-task-role` → Delete inline policies → Delete role

---

## Phase 2: Terraform Validation

Run these commands from the `terraform/` directory to verify configuration:

```bash
cd terraform

# 1. Validate syntax
terraform validate

# 2. Check for format issues
terraform fmt -recursive -check

# 3. Generate plan (preview all resources)
terraform plan -out=tfplan

# 4. Check plan for potential issues (optional)
terraform plan -json | jq '.resource_changes[] | select(.change.actions | length > 0)'
```

### Expected Output
- `terraform validate`: Should show "Success! The configuration is valid."
- `terraform fmt`: Should show no changes needed
- `terraform plan`: Should show ~182 resources to create (first deploy after cleanup)

---

## Phase 3: Identify Remaining Issues

Check for these common Terraform issues:

### 1. Hardcoded Values
```bash
grep -r "hardcoded\|TODO\|FIXME\|changeme" terraform/
```
Expected: No matches

### 2. Missing Variable Defaults
```bash
grep -n "type = " terraform/variables.tf | grep -v "default ="
```
Expected: Some variables (like `rds_password`) intentionally have no default

### 3. Provider Configuration
```bash
grep -n "provider\|required_providers" terraform/versions.tf
```
Expected: AWS provider ~> 5.0, Terraform >= 1.5.0

### 4. Module References
```bash
grep -n "module\|source =" terraform/main.tf
```
Expected: All 7 modules properly referenced

### 5. Data Source Validation
```bash
terraform validate -json | jq '.diagnostics[]'
```
Expected: No errors, only warnings at most

---

## Phase 4: Fix Any Identified Issues

After terraform plan output, check for:

| Issue | Fix |
|-------|-----|
| **Missing variable** | Add to `variables.tf` with proper type and validation |
| **Circular dependency** | Refactor to use `depends_on` explicitly or split into modules |
| **Invalid resource type** | Check AWS provider documentation for correct resource name |
| **Missing required parameter** | Add to resource configuration |
| **Type mismatch** | Ensure variable type matches usage (string vs list vs map) |

---

## Phase 5: Deployment

Once all validation passes and issues are fixed:

```bash
# Option 1: Deploy via GitHub Actions (Recommended)
git add .
git commit -m "Fix: Terraform validation and resource cleanup"
git push origin main
# GitHub Actions will run terraform-apply automatically

# Option 2: Manual deployment
cd terraform
terraform apply tfplan
```

---

## Files to Check Before Deployment

| File | Check |
|------|-------|
| `terraform/variables.tf` | All variables defined and typed correctly |
| `terraform/locals.tf` | No dynamic values (like `timestamp()`) |
| `terraform/main.tf` | All modules have required variables passed |
| `terraform/backend.tf` | S3 bucket and DynamoDB table names correct |
| `.github/workflows/terraform-apply.yml` | All secrets referenced in env vars |
| `bootstrap/oidc.yml` | OIDC trust policy scoped to repo correctly |

---

## Rollback Plan (if deployment fails)

1. **Check what failed:**
   ```bash
   aws cloudformation describe-stacks \
     --region us-east-1 \
     --query 'Stacks[?contains(StackStatus, `FAILED`)].{Name:StackName, Status:StackStatus}'
   ```

2. **Delete failed resources:**
   ```bash
   # This automatically triggers via rollback-on-failure job in GitHub Actions
   # Or manual:
   terraform destroy -auto-approve
   ```

3. **Check state integrity:**
   ```bash
   terraform state list
   terraform refresh
   ```

4. **Retry deployment** after fixes applied

---

## Success Criteria

✅ Terraform validate passes
✅ Terraform plan shows 180+ resources  
✅ All required variables set via GitHub secrets
✅ No hardcoded AWS account IDs or regions
✅ All modules properly reference outputs
✅ ECR lifecycle policy has valid JSON
✅ API Gateway integration configured correctly
✅ CloudFront origin domain names valid
✅ RDS subnet group, launch template, IAM roles cleaned up
✅ GitHub Actions secrets configured: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ACCOUNT_ID, RDS_PASSWORD, SLACK_WEBHOOK

---

**Status:** Ready for Phase 1 (Cleanup)
**Last Updated:** 2026-05-07

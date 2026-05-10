# Terraform Pre-Flight Checklist

## Prerequisites (Before Any Deployment)

### 1. GitHub Secrets Configuration
Verify all required secrets are set in GitHub repository settings:
```bash
# Check each secret is defined (output will be redacted if set)
gh secret list --repository argeropolos/algo
```

**Required Secrets:**
- ✅ AWS_ACCESS_KEY_ID
- ✅ AWS_SECRET_ACCESS_KEY  
- ✅ AWS_ACCOUNT_ID
- ✅ RDS_PASSWORD
- ✅ SLACK_WEBHOOK

**Set a secret:**
```bash
gh secret set AWS_ACCESS_KEY_ID --body "your-access-key"
gh secret set AWS_SECRET_ACCESS_KEY --body "your-secret-key"
gh secret set AWS_ACCOUNT_ID --body "123456789012"
gh secret set RDS_PASSWORD --body "SecurePassword123!"
gh secret set SLACK_WEBHOOK --body "https://hooks.slack.com/services/..."
```

### 2. AWS Account & Permissions
- ✅ AWS account has Administrator or near-Administrator access
- ✅ Current AWS region is `us-east-1` (verify in console)
- ✅ No resource quotas preventing 180+ new resources

### 3. Terraform State Backend
The S3 state bucket must exist:
```bash
# Verify state bucket exists
aws s3 ls s3://stocks-terraform-state/

# Verify DynamoDB lock table exists  
aws dynamodb list-tables --region us-east-1 | grep stocks-terraform-locks
```

If not found, run bootstrap:
```bash
# Option 1: Via GitHub Actions (recommended)
gh workflow run bootstrap-oidc.yml

# Option 2: Manual (requires AWS CLI locally)
aws s3 mb s3://stocks-terraform-state --region us-east-1
aws dynamodb create-table \
  --table-name stocks-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 4. OIDC Provider Configuration
GitHub OIDC provider must be configured in AWS:
```bash
# Verify OIDC provider exists
aws iam list-open-id-connect-providers --region us-east-1 | grep token.actions.githubusercontent.com

# Verify github-actions-role exists
aws iam get-role --role-name github-actions-role

# Verify role has correct trust relationship
aws iam get-role --role-name github-actions-role --query 'Role.AssumeRolePolicyDocument'
```

If not found:
```bash
# Deploy OIDC stack via GitHub Actions (recommended)
gh workflow run bootstrap-oidc.yml

# Or deploy manually:
aws cloudformation deploy \
  --template-file bootstrap/oidc.yml \
  --stack-name stocks-oidc \
  --region us-east-1 \
  --no-fail-on-empty-changeset \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## Pre-Deployment Checks

### Step 1: Verify Terraform Configuration
```bash
# 1. Run terraform init (downloads modules and initializes backend)
cd terraform
terraform init

# 2. Validate syntax
terraform validate

# 3. Format check (detects style issues)
terraform fmt -recursive -check

# 4. Generate plan (preview all 180+ resources)
terraform plan -out=tfplan
```

**Expected Output:**
- ✅ `terraform init`: "Terraform has been successfully initialized"
- ✅ `terraform validate`: "Success! The configuration is valid"
- ✅ `terraform fmt`: No output (or list of files needing formatting)
- ✅ `terraform plan`: Shows ~180 resources to create/modify

### Step 2: Analyze Plan Output
```bash
# Check plan for resource count
terraform plan -json | jq '.resource_changes | length'

# Check for any potential issues
terraform plan -json | jq '.diagnostics | length'
```

### Step 3: Verify Variable Substitution
```bash
# All variables properly defined and typed
grep -n "variable \|type \|default " terraform/variables.tf | head -20

# Check terraform.tfvars or .auto.tfvars
ls -la terraform/*.tfvars

# Verify TF_VAR_ environment variables will be set
cat .github/workflows/terraform-apply.yml | grep TF_VAR_
```

### Step 4: Review Key Configuration Files
```bash
# Check versions.tf
cat terraform/versions.tf

# Check locals.tf (ensure no dynamic values)
cat terraform/locals.tf

# Check backend.tf
cat terraform/backend.tf
```

**What to look for:**
- ✅ Terraform >= 1.5.0 required
- ✅ AWS provider ~> 5.0
- ✅ No `timestamp()` or `random_*` in common_tags
- ✅ S3 bucket name = `stocks-terraform-state`
- ✅ DynamoDB table = `stocks-terraform-locks`

### Step 5: Module Dependency Verification
```bash
# Check all modules have required variables
terraform validate -json | jq '.diagnostics[]'

# List module sources
grep -r "source = " terraform/main.tf
```

**Modules (must all be present):**
- ✅ iam
- ✅ vpc
- ✅ storage
- ✅ database
- ✅ compute
- ✅ loaders
- ✅ services

---

## Common Issues & Fixes

### Issue: "Error acquiring the state lock"
**Cause:** Another terraform apply is running or lock is stuck
**Fix:**
```bash
terraform force-unlock <lock-id>

# Or wait 5 minutes and retry
sleep 300
terraform plan
```

### Issue: "Missing variable 'rds_password'"
**Cause:** RDS_PASSWORD secret not set in GitHub
**Fix:**
```bash
gh secret set RDS_PASSWORD --body "YourPassword123!"
```

### Issue: "The argument ... is not expected"
**Cause:** Terraform version mismatch or invalid resource type
**Fix:**
```bash
# Verify Terraform version
terraform --version

# Should be >= 1.5.0

# Update if needed
terraform -version 1.5.4  # or use tfenv/asdf to manage versions
```

### Issue: "Module not found"
**Cause:** Terraform module source path is incorrect
**Fix:**
```bash
cd terraform
terraform init -upgrade  # Re-fetch all modules
terraform validate
```

---

## Deployment Readiness Checklist

- [ ] All GitHub secrets are set and non-empty
- [ ] AWS account has Administrator access
- [ ] Terraform state bucket (stocks-terraform-state) exists
- [ ] DynamoDB lock table (stocks-terraform-locks) exists
- [ ] OIDC provider for GitHub is configured
- [ ] IAM role (github-actions-role) exists and has correct trust policy
- [ ] `terraform validate` passes with no errors
- [ ] `terraform plan` shows ~180 resources to create
- [ ] No hardcoded values in Terraform code
- [ ] All modules are present and accessible
- [ ] Stale AWS resources have been cleaned up:
  - [ ] EC2 Launch Template (stocks-bastion-lt) deleted
  - [ ] RDS DB Subnet Group (stocks-db-subnet-group) deleted
  - [ ] IAM Role (stocks-eventbridge-run-task-role) deleted

---

## Deployment Steps (GitHub Actions Only)

### Option 1: Trigger via GitHub CLI (Recommended)
```bash
# Manually trigger terraform-apply workflow
gh workflow run terraform-apply.yml

# Or trigger cleanup first, then deploy
gh workflow run cleanup-stale-resources.yml

# Wait for cleanup to complete (~1-2 minutes), then:
gh workflow run terraform-apply.yml

# Monitor the deployment
gh run list --workflow=terraform-apply.yml --limit 1
```

### Option 2: Push Code (Auto-triggers)
```bash
git add terraform/
git commit -m "Deploy: Terraform infrastructure with all fixes"
git push origin main

# Workflow runs automatically on push to main
# View in GitHub UI or via:
gh run list
```

### Option 3: Manual Terraform (Local, only if Terraform installed)
```bash
cd terraform

# Initialize (one-time)
terraform init

# Plan (review what will be created)
terraform plan -out=tfplan

# Apply (create all resources)
terraform apply tfplan

# Check outputs
terraform output
```

---

## Post-Deployment Verification

After deployment completes successfully:

```bash
# 1. Verify all resources were created
aws cloudformation list-stacks \
  --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE`].StackName'

# 2. Check Terraform outputs
terraform output

# 3. Test RDS connectivity
aws rds describe-db-instances \
  --region us-east-1 \
  --query 'DBInstances[?contains(DBInstanceIdentifier, `stocks`)].{ID:DBInstanceIdentifier, Status:DBInstanceStatus}'

# 4. Check ECS cluster
aws ecs list-clusters \
  --region us-east-1 \
  --query 'clusterArns'

# 5. Verify data loaders
aws ecs list-task-definitions \
  --region us-east-1 \
  --query 'taskDefinitionArns | length'
```

---

## Rollback Procedure

If deployment fails and you need to rollback:

```bash
# 1. Identify what failed
aws cloudformation list-stacks \
  --region us-east-1 \
  --query 'StackSummaries[?contains(StackStatus, `FAILED`)]'

# 2. Automatic rollback via GitHub Actions
# The rollback-on-failure job runs automatically

# 3. Or manual rollback (if needed)
terraform destroy -auto-approve

# 4. Or restore from backup state
aws s3 cp \
  s3://stocks-terraform-state/backups/terraform.tfstate.TIMESTAMP.backup \
  s3://stocks-terraform-state/dev/terraform.tfstate \
  --region us-east-1

# 5. Retry deployment
gh workflow run terraform-apply.yml
```

---

**Status:** Ready for pre-flight checklist execution
**Last Updated:** 2026-05-07
**Maintainer:** Claude Code

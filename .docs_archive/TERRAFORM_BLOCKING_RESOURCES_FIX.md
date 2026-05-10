# Terraform Blocking Resources - Complete Fix Guide

**Date:** 2026-05-08
**Status:** In Progress
**Owner:** User

---

## Problem Summary

Terraform deployment is blocked by 11 IAM roles and CloudFront Origin Access Controls (OACs) that exist in AWS but aren't managed by the current terraform code. When `terraform apply` runs, it tries to create these resources, hits `EntityAlreadyExists` errors, and the deployment fails.

### The 11 Blocking IAM Roles

1. `stocks-bastion-stop-lambda-role`
2. `stocks-github-actions-dev`
3. `stocks-bastion-dev`
4. `stocks-ecs-task-execution-dev`
5. `stocks-ecs-task-dev`
6. `stocks-lambda-api-dev`
7. `stocks-lambda-algo-dev`
8. `stocks-eventbridge-scheduler-dev`
9. `stocks-eventbridge-run-task-role`
10. `stocks-api-dev-role`
11. `stocks-algo-dev-role`

### Why This Happens

These roles were created in previous terraform runs or manual AWS operations. They're not defined in the current terraform code, so terraform doesn't know about them. When terraform tries to create them, it gets `EntityAlreadyExists` errors.

---

## Root Cause Analysis

### What's Creating These Roles in Terraform

Looking at `terraform/modules/` directory:

- **services/main.tf**: Creates `aws_iam_role.api_lambda` → becomes `stocks-api-dev-role`
- **algo/main.tf**: Creates `aws_iam_role.lambda_role` → becomes `stocks-algo-dev-role`
- **loaders/main.tf**: Creates `aws_iam_role.eventbridge_run_task` → becomes `stocks-eventbridge-run-task-role`
- **iam/main.tf**: Creates `aws_iam_role.github_actions` → becomes `stocks-github-actions-dev`
- **compute/main.tf**: Creates various instance profiles and roles

### Why Cleanup Fails

The existing `terraform-apply.yml` workflow tries to clean up these roles, but:

1. **Retry logic is insufficient**: AWS API may be slow, deletion succeeds but terraform doesn't see it immediately
2. **No verification step**: Workflow doesn't wait to confirm roles are actually deleted before terraform runs
3. **Silent failures**: If a deletion fails, the script continues without raising an error
4. **Timing issues**: Terraform init/plan might run before cleanup is complete

---

## Solution: Three-Phase Cleanup & Verification

### Phase 1: Manual Cleanup (Today)

Run the enhanced cleanup workflow to verify and delete all blocking resources:

```bash
gh workflow run terraform-cleanup-enhanced.yml --repo argie33/algo
```

This workflow:
1. **Lists** all blocking resources before deletion
2. **Deletes** inline policies → managed policies → roles (correct dependency order)
3. **Retries** each deletion up to 3 times with delays
4. **Verifies** all resources are gone before completing
5. **Reports** detailed status for each operation

### Phase 2: Update Terraform Code (After Cleanup)

Once roles are deleted, we need to ensure terraform doesn't try to recreate them with old names. Options:

**Option A: Rename all roles** (Recommended)
- Change naming pattern to avoid legacy naming
- Example: `stocks-api-${environment}-role` → `stocks-svc-api-${environment}`
- This avoids all conflicts with old resources

**Option B: Add explicit count conditions**
- Use `count = var.create_legacy_roles ? 1 : 0`
- Set `create_legacy_roles = false` in terraform.tfvars
- Good for gradual migration

**Option C: Use terraform import** (Complex)
- Import existing resources into terraform state
- Requires understanding current state
- High risk of state corruption

### Phase 3: Test Clean Deployment

After cleanup and terraform fixes:

```bash
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo --input skip_bootstrap=true
```

This:
1. Runs terraform init/plan/apply
2. Creates all infrastructure from scratch
3. Monitors logs for any `EntityAlreadyExists` errors
4. Provides detailed output at each stage

---

## Step-by-Step Execution

### STEP 1: Run Enhanced Cleanup (5 minutes)

```bash
# First, just verify what will be deleted (no actual deletion)
gh workflow run terraform-cleanup-enhanced.yml \
  --repo argie33/algo \
  --input verify_only=true

# Watch the workflow run:
# https://github.com/argie33/algo/actions/workflows/terraform-cleanup-enhanced.yml

# Once you verify the list is correct, run the actual cleanup:
gh workflow run terraform-cleanup-enhanced.yml \
  --repo argie33/algo \
  --input verify_only=false

# Wait for completion - check Action logs for:
# ✅ POST-CLEANUP: All blocking resources cleaned up!
```

### STEP 2: Verify All Resources Are Gone (2 minutes)

After cleanup workflow completes successfully:

```bash
# The workflow output will show:
# ✓ Deleted: stocks-bastion-stop-lambda-role
# ✓ Deleted: stocks-github-actions-dev
# ... (all 11 roles)
# ✓ Deleted: CloudFront OACs
```

If any resources remain, the workflow will error. Check the logs to see which ones failed and why.

### STEP 3: Update Terraform Code (30 minutes)

#### Option A Recommended: Rename Roles

Update terraform/modules/services/main.tf:

```terraform
# OLD (line 17):
name = "${local.api_lambda_name}-role"

# NEW:
name = "${var.project_name}-svc-api-${var.environment}-role"
```

Update terraform/modules/algo/main.tf (line 15):

```terraform
# OLD:
name = "${var.project_name}-algo-lambda-role"

# NEW:
name = "${var.project_name}-svc-algo-${var.environment}-role"
```

Update all other role names similarly to follow pattern:
- `stocks-svc-api-dev`
- `stocks-svc-algo-dev`
- `stocks-svc-eventbridge-run-task-dev`
- etc.

Test locally first:

```bash
cd terraform
terraform plan -var-file=terraform.tfvars
```

Expect output:
```
Plan: 45 to add, 0 to change, 0 to destroy
```

No role conflicts = good!

### STEP 4: Commit & Push Changes

```bash
git add terraform/
git commit -m "Fix: Rename IAM roles to prevent conflicts with legacy resources"
git push origin main
```

This will trigger `terraform-apply.yml` workflow. Watch logs carefully for any errors.

### STEP 5: Run Full Deployment Test

Once terraform-apply succeeds:

```bash
gh workflow run deploy-all-infrastructure.yml \
  --repo argie33/algo \
  --input skip_bootstrap=true
```

Monitor each stage:
1. Core Infrastructure (VPC, ECR, S3)
2. Data Infrastructure (RDS, ECS cluster, Secrets)
3. Webapp (Lambda API, CloudFront)
4. Loaders (ECS task definitions)
5. Algo (Orchestrator Lambda, EventBridge)

Watch for errors in each stage. If you see `EntityAlreadyExists`, a role wasn't properly deleted.

### STEP 6: Verify Deployment Success

```bash
# Check all stacks created
aws cloudformation list-stacks --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE`].StackName'

# Should see:
# - stocks-core (VPC, networking)
# - stocks-data (RDS, ECS cluster)
# - stocks-webapp-dev (API Lambda)
# - stocks-loaders (task definitions)
# - stocks-algo-dev (Orchestrator)
```

---

## Troubleshooting

### If cleanup workflow fails:

```bash
# Check the workflow logs for details
# https://github.com/argie33/algo/actions

# Look for:
# ✗ Failed to delete role X
# ✗ Failed to delete OAC Y

# Common reasons:
# 1. Policy has dependent service role - detach all managed policies first
# 2. OAC is still referenced by CloudFront - delete CloudFront distribution first
# 3. AWS API rate limiting - retry the workflow
```

### If terraform apply still fails:

```bash
# Check if any roles still exist
aws iam list-roles --query "Roles[?contains(RoleName, 'stocks')].RoleName" \
  --output text

# If roles exist, they weren't deleted. Re-run cleanup workflow.
# If no roles exist, error is elsewhere - check terraform logs.
```

### If deployment completes but infrastructure doesn't work:

```bash
# Check Lambda logs
aws logs tail /aws/lambda/algo-orchestrator --follow

# Check CloudFormation events
aws cloudformation describe-stack-events --stack-name stocks-core \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'

# Verify RDS is accessible
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c "SELECT 1"
```

---

## Rollback Plan

If something goes wrong:

1. **Don't force-push to main** - keep the git history
2. **Check terraform state**: `terraform state show`
3. **If state is corrupted**: Go to S3, download backup, restore manually
4. **If resources are stuck**: Delete via AWS console, retry deployment
5. **Contact support** if VPC quota is exhausted (requires AWS support ticket)

---

## Expected Timeline

- **Phase 1 (Cleanup)**: 10 minutes
- **Phase 2 (Code update)**: 30 minutes
- **Phase 3 (First deployment)**: 25 minutes
- **Phase 4 (Verification)**: 5 minutes

**Total: ~70 minutes for complete fix**

---

## Success Criteria

✅ All 11 IAM roles deleted  
✅ All CloudFront OACs deleted  
✅ Terraform plan shows no conflicts  
✅ `terraform apply` completes without errors  
✅ All CloudFormation stacks created successfully  
✅ Lambda functions are deployed and callable  
✅ RDS is accessible  
✅ EventBridge scheduler is active  

---

## Learning Points

### Why This Happened

1. **Infrastructure drift**: Manual AWS operations created resources terraform doesn't know about
2. **Incomplete cleanup**: Previous workflows tried to clean but didn't verify completeness
3. **Naming conflicts**: Old role names matched what terraform wanted to create

### How to Prevent

1. **All-or-nothing deployments**: Always use terraform, never manual AWS console changes
2. **Cleanup verification**: Always wait for deletion confirmation before proceeding
3. **Immutable naming**: Use timestamps or UUIDs for role names to avoid collisions
4. **Terraform state management**: Regular backups and audits of terraform.tfstate

---

## Questions or Issues?

If anything goes wrong:
1. Check the workflow logs first (most detailed info)
2. Review this guide's troubleshooting section
3. Check AWS CloudFormation events for service-specific errors
4. Save workflow output for debugging

# Debug: Why Terraform Deploy Never Works

## The Mystery

1. **Terraform code is correct:**
   - Line 444 of `terraform/modules/loaders/main.tf`: `"value_metrics" = { cpu = 1024, memory = 2048, ...}`
   - Lines 788-789: `cpu = tostring(each.value.cpu)` and `memory = tostring(each.value.memory)`

2. **Terraform output is correct:**
   - Line 7 of `terraform/modules/loaders/outputs.tf`: Returns `v.family` (not hardcoded revision)
   - Comment says "Step Functions will resolve to latest active revision"

3. **But ECS task in AWS still shows 512 CPU, 1024 Memory (old values)**
   - Last checked: Session 196
   - Terraform code has been updated (Commit 90291b160)
   - GitHub Actions claimed success (02:29:12 UTC Session 195)
   - BUT: Task definitions not actually updated

## Possible Root Causes

### Theory 1: Terraform Isn't Detecting Changes

The `aws_ecs_task_definition` resource has `family` set but doesn't have explicit `lifecycle { create_before_destroy = true }`. When CPU/memory change, Terraform might:
- Think "family name hasn't changed, so no new revision needed"
- Skip creating a new task definition revision
- Do nothing (no-op apply)

**Evidence:**
- Lines 788-789 change cpu/memory but family name doesn't change
- ECS task definitions are versioned — CPU/memory changes should trigger new revision
- But if Terraform's comparison only looks at family name, it won't trigger

### Theory 2: Terraform State Corruption or Lock

The Terraform state might:
- Be locked by a previous failed apply
- Have stale cached values
- Not be syncing properly between GitHub Actions and S3 backend

**Evidence from workflow:**
- workflow runs `terraform init -reconfigure -backend-config=...`
- But `-reconfigure` might not clear old locks
- DynamoDB lock table `terraform-locks` might have stale entries

### Theory 3: IAM Permissions

GitHub Actions role might not have:
- `ecs:RegisterTaskDefinition` permission
- `iam:PassRole` for task role/execution role
- Causing silent failure (apply claims success but doesn't actually register)

**But unlikely** since you'd see errors in workflow logs.

### Theory 4: ECS Task Definition ARN Format Issue

The output passes task definition **family name** (`algo-value-metrics-loader`), but Step Functions needs to specify a revision to get the new resources.

**How to check:** If Step Functions runs the task but it uses the old revision (512 CPU), the family name isn't resolving to the latest revision.

---

## How to Verify and Fix

### Quick Test: Force New Task Definition

Add a trigger to force Terraform to detect changes:

```hcl
# terraform/modules/loaders/main.tf line 517 (after family declaration)

  # FORCE: Increment this when manual re-deploy is needed (don't rely on auto-detection)
  tags = merge(var.common_tags, {
    force_rebuild_version = "2"  # Increment to force new task def
  })
```

If this forces a new revision but nothing else does, then **Terraform isn't detecting CPU/memory changes**.

### Real Fix: Explicit Revision in Task Definition Output

Change line 7 of `terraform/modules/loaders/outputs.tf`:

```hcl
# OLD (uses family name, may not resolve correctly):
value = { for k, v in aws_ecs_task_definition.loader : k => v.family }

# NEW (uses ARN with latest revision implicit):
value = { for k, v in aws_ecs_task_definition.loader : k => "${v.arn}" }

# OR (if Step Functions needs explicit revision):
value = { for k, v in aws_ecs_task_definition.loader : k => "${v.family}:${v.revision}" }
```

### Check State Backend

```bash
# Verify Terraform state is not corrupted
aws dynamodb scan --table-name terraform-locks --region us-east-1

# Check if lock is stale (should be empty or very recent)
# If lock.expires_at < NOW(), it's stale and preventing terraform apply
```

### Force Fresh Terraform Apply

```bash
cd terraform
# Backup current state
aws s3 cp s3://stocks-terraform-state/stocks/terraform.tfstate terraform.tfstate.backup

# Force refresh and re-apply
terraform init -reconfigure -backend-config=bucket=stocks-terraform-state -backend-config=key=stocks/terraform.tfstate -backend-config=region=us-east-1
terraform refresh  # Re-read actual AWS state
terraform plan     # Should show CPU/memory changes
terraform apply    # Apply changes
```

---

## Why User Says "Deploy Never Works"

**Pattern across Sessions 193-196:**
1. Code changed (CPU 512→1024)
2. Commit pushed (90291b160)
3. GitHub Actions triggered
4. Workflow shows "success"
5. But AWS still has old resources
6. User manually runs pipeline, fails with old resources
7. Try again...

**This is a classic Terraform detection issue:**
- The `for_each` loop iterates over `local.all_loaders`
- Each iteration should create a task definition
- If Terraform thinks nothing changed (because it only watches family name), it applies no changes
- GitHub Actions workflow succeeds (no error), but nothing actually deployed

**The fix:** Make Terraform explicitly track CPU and memory changes. Either:
1. Add `force_rebuild_version` tag (forces change detection), or
2. Use task definition ARN instead of family name in outputs, or
3. Add explicit lifecycle rule to force new revision creation

---

## Immediate Action

Until Terraform is fixed, **manual workaround:**

```bash
# Register new task definition manually (bypasses Terraform)
aws ecs register-task-definition \
  --family algo-value-metrics-loader \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu 1024 \
  --memory 2048 \
  --execution-role-arn arn:aws:iam::ACCOUNT_ID:role/algo-ecs-task-execution-role \
  --task-role-arn arn:aws:iam::ACCOUNT_ID:role/algo-ecs-task-role \
  --container-definitions '[{...existing container defs from old revision...}]'

# Then run pipeline
python scripts/trigger_eod_pipeline.py
```

This will register revision 8+ with the new resources, and Step Functions will use it (since it uses family name).

---

## Why This Matters

The symptom is "deploy doesn't work." The root cause is "Terraform doesn't detect CPU/memory changes as reasons to create a new task definition revision."

This is a **showstopper bug** because:
- Users update IaC (Terraform)
- Users commit and push
- GitHub Actions runs and shows success
- But actual AWS resources never update
- False confidence that deployment succeeded

Fix by either making Terraform detect changes or bypassing Terraform for task registration.

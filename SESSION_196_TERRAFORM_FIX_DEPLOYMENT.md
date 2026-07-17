# Session 196: Terraform Fix Deployed - Monitoring Guide

## What Just Happened

**Commit:** 248413233 - "fix: Force Terraform to detect ECS task CPU/memory changes"

**Change:** Added `force_rebuild_version = "3"` tag to ECS task definition resource

**Purpose:** Force Terraform to create NEW task definition revisions when CPU/memory parameters change (previously being ignored)

---

## Deployment Timeline

### Stage 1: GitHub Actions CI (5-10 min) ⏳
- Workflow: `.github/workflows/ci.yml`
- Status: Check GitHub Actions tab
- What it does: Runs tests, validates code
- Success criteria: All tests pass

### Stage 2: GitHub Actions Deploy (30-40 min) ⏳⏳
- Workflow: `.github/workflows/deploy-all-infrastructure.yml`
- Triggered: Automatically after CI passes
- What it does:
  1. Initialize Terraform backend (S3 + DynamoDB)
  2. Run `terraform plan` (should show 37+ resources to change)
  3. Run `terraform apply` (creates new task definition revisions)
  4. Deploy Lambda code
  5. Deploy frontend code

### Expected Changes in Plan

```
Plan: 37 to update, 0 to add, 0 to destroy

Changes:
- aws_ecs_task_definition.loader["value_metrics"] — new revision with cpu=1024, memory=2048
- aws_ecs_task_definition.loader["positioning_metrics"] — new revision with cpu=1024, memory=2048  
- aws_ecs_task_definition.loader["stock_scores"] — new revision with cpu=1024, memory=2048
- [35 other loaders with tags updated]
```

---

## How to Monitor Deployment

### Option 1: Watch GitHub Actions (Easiest)

1. Go to: https://github.com/argie33/algo/actions
2. Find the latest run for commit `248413233`
3. Click into "Deploy All Infrastructure" job
4. Watch for:
   - ✅ "Terraform Apply" succeeds (green checkmark)
   - Output shows "37 to update" and "Apply complete!"

### Option 2: Check AWS Directly

Once Terraform applies, verify the new task definitions exist:

```bash
# Check value_metrics task definition
aws ecs describe-task-definition \
  --task-definition algo-value-metrics-loader \
  --region us-east-1 \
  --query 'taskDefinition.[cpu,memory,revision]'

# Expected output:
# ["1024", "2048", 8]  (or higher revision number)
```

If revision is still 7 (or lower) with cpu=512: **Terraform apply didn't work**
If revision is 8+ with cpu=1024: **Terraform apply worked!** ✅

---

## After Deployment: Test the Fix

Once Terraform deployment completes and new task definitions are registered (5-10 min):

### Trigger EOD Pipeline

```bash
python scripts/trigger_eod_pipeline.py
```

Monitor execution:
```bash
aws stepfunctions describe-execution \
  --execution-arn $(aws stepfunctions list-executions \
    --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev \
    --max-results 1 \
    --query 'executions[0].executionArn' \
    --output text) \
  --region us-east-1
```

### Expected Results (30-40 min)

Check stock_scores coverage after pipeline completes:

```bash
python << 'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM stock_scores WHERE value_score > 0')
with_scores = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM stock_scores')
total = cur.fetchone()[0]
print(f'Value scores: {with_scores}/{total} ({100*with_scores/total:.1f}%)')
cur.close()
conn.close()
EOF
```

**Success criteria:**
- Before: 78.5% (3696/4711 stocks)
- After: 95%+ (4500+/4711 stocks)
- Gap fixed by 1000+ additional scores

---

## If Deployment Fails

### Check GitHub Actions Logs

1. Go to workflow run
2. Find "Terraform Apply" step
3. Look for:
   - "Terraform apply failed" → Check error message
   - "Transient provisioned-concurrency race detected" → Normal, workflow retries automatically
   - "Apply complete!" → Success (despite any warnings)

### Common Issues

**Issue 1: "Requested Provisioned Concurrency should not be greater than..."**
- This is a known AWS eventual-consistency race
- Workflow has auto-retry (3 attempts with 30s delays)
- Usually resolves on retry

**Issue 2: "AccessDenied: User is not authorized to perform s3:PutObject"**
- GitHub Actions IAM role lost S3 permissions
- Check GitHub Secrets: `GITHUB_ACTIONS_ROLE_ARN`
- Verify IAM role has `s3:*` on `stocks-terraform-state` bucket

**Issue 3: "No infrastructure changes detected — skipping terraform apply"**
- Terraform didn't see the `force_rebuild_version` tag change
- Could indicate state file corruption
- Workaround: Manually increment version again and re-push

### Fallback: Manual Task Definition Registration

If Terraform fails, register task definitions manually:

```bash
# Get old task definition
aws ecs describe-task-definition \
  --task-definition algo-value-metrics-loader \
  --region us-east-1 > /tmp/task_def.json

# Edit CPU/memory in JSON
# Register new version
aws ecs register-task-definition \
  --cli-input-json file:///tmp/task_def.json \
  --cpu 1024 --memory 2048 \
  --region us-east-1
```

---

## Success Checklist

- [ ] GitHub Actions CI passes
- [ ] GitHub Actions Deploy starts
- [ ] Terraform plan shows "37 to update"
- [ ] Terraform apply completes successfully
- [ ] New task definitions created (revision 8+)
- [ ] `aws ecs describe-task-definition` shows cpu=1024
- [ ] Pipeline triggered successfully
- [ ] stock_scores coverage > 95%

---

## Timeline Estimate

- Commit pushed: Now ✅
- CI completes: 10 min
- Deploy starts: 15 min
- Terraform plan: 5 min  
- Terraform apply: 10 min
- Task definitions ready: 40 min (total)
- Pipeline completes: 80 min total (40 min deploy + 40 min pipeline run)
- Factor scores > 95%: ~90 min from now

---

## Session 196 - The Fix

**Problem:** Terraform deploy succeeds but doesn't actually update resources

**Root Cause:** Terraform only watches family name, not CPU/memory parameters

**Solution:** Add tag to force change detection

**Expected Impact:** 
- Factor scores jump from 78.5% → 95%+
- StockScoresLoader gets proper resources (1024 CPU, 2048 Memory)
- Calculation completes for all 4711 stocks
- No more partial failures due to resource constraints

**Next Blocker:** Flag system (Session 195) - need to migrate loaders to LoaderStatusManager to prevent silent failures in future

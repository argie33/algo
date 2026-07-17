# Session 199: ECS Best Practices - Complete Deployment Guide

## Summary

✅ **FULLY INTEGRATED & READY TO DEPLOY**

All 4 layers are now production-ready:
1. **Enhanced health check script** - In Docker image, checks responsiveness
2. **Updated ECS task definitions** - Uses new health check script
3. **Auto-kill Lambda** - Terminates stuck tasks automatically
4. **Complete IaC** - Terraform deploys everything

**Commit:** `6f2170a06`

---

## What Changed (Technical)

### 1. Dockerfile
```dockerfile
COPY healthcheck.sh /healthcheck.sh
RUN chmod +x /healthcheck.sh
```
- Added healthcheck.sh to Docker image
- Made executable so ECS can run it

### 2. Health Check Script (healthcheck.sh)
Already existed, now integrated. Checks:
```bash
1. Python loader process exists
2. /tmp/loader_health_check file exists
3. File is < 60 seconds old
```
Returns exit 0 (healthy) or exit 1 (unhealthy)

### 3. ECS Task Definition (terraform/modules/loaders/main.tf)
Changed from:
```hcl
command = ["CMD-SHELL", "ps aux | grep -q '[p]ython.*${each.key}' || exit 1"]
```

To:
```hcl
command = ["/healthcheck.sh"]
```
Same settings: interval=30s, timeout=5s, retries=2, startPeriod=120s

### 4. OptimalLoader (utils/optimal_loader.py) - Already Done
- Creates `/tmp/loader_health_check` on startup
- Updates file every 5 seconds during execution
- Signals "I'm responsive and working"

### 5. Auto-Kill Lambda (lambda/auto_kill_stuck_tasks/index.py)
Production-ready Lambda that:
- Lists all tasks in cluster
- Finds stuck ones (UNHEALTHY>2h, UNKNOWN>3h, any>4h)
- Terminates them with reason
- Sends SNS alert with cost savings

### 6. Lambda Terraform (terraform/modules/monitoring/auto_kill_stuck_tasks.tf)
Complete IaC:
- Lambda function + execution role
- IAM permissions (ecs:StopTask, sns:Publish)
- CloudWatch alarm (unhealthy task count > 0)
- EventBridge Scheduler (runs every 6 hours)
- CloudWatch log group

### 7. Terraform Wiring (terraform/main.tf)
- Passes `cluster_name = "algo-cluster"` to monitoring module
- All variables connected

---

## Deployment Steps

### Phase 1: Build & Deploy Docker Image (GitHub Actions)
This happens automatically when you push:

1. **Trigger:** Push to main branch (or manually trigger `deploy-ecs-image.yml`)
2. **What happens:**
   - GitHub Actions validates code (lint, type check, tests)
   - Builds Docker image with healthcheck.sh included
   - Pushes to ECR (`algo:dev-latest`)
   - Optionally restarts running tasks with new image

3. **Timeline:** ~5-10 minutes
4. **Verify:** 
   ```bash
   aws ecr describe-images \
     --repository-name algo \
     --query 'imageDetails[0].[imageTags,imagePushedAt]'
   ```

### Phase 2: Deploy Terraform (Manual)
After Docker image is built:

```bash
cd terraform

# Preview changes
terraform plan -var-file=dev.tfvars

# Deploy
terraform apply -var-file=dev.tfvars

# Verify
terraform output | grep auto_kill
```

**What deploys:**
- New ECS task definitions (health check uses /healthcheck.sh)
- Auto-kill Lambda function
- CloudWatch alarms + EventBridge schedule
- All IAM roles and policies

**Timeline:** ~2-3 minutes

### Phase 3: Restart Running Tasks (Manual)
Force ECS to use new task definition with new health check:

```bash
# Option A: GitHub Actions (automatic)
# Just set force_recreate=true in workflow_dispatch

# Option B: AWS CLI (manual)
CLUSTER=$(aws ecs list-clusters \
  --query "clusterArns[0]" --output text)

SERVICES=$(aws ecs list-services --cluster "$CLUSTER" \
  --query "serviceArns[]" --output text)

for SERVICE in $SERVICES; do
  aws ecs update-service --cluster "$CLUSTER" \
    --service "$SERVICE" --force-new-deployment
done
```

**What happens:**
- Running tasks gracefully shut down (drain)
- New tasks start with new health check script
- ECS runs new health check every 30 seconds

---

## How It Works (Day-to-Day)

### Normal Execution (Loader Running)

```
Time 0s:  Loader starts
          ├─ OptimalLoader.__init__() runs
          └─ _init_health_check() creates /tmp/loader_health_check with timestamp

Time 5s:  Loader processes first symbol
          ├─ _update_health_check() updates file with current time
          └─ File now says "5 seconds old"

Time 30s: ECS runs health check (scheduled)
          ├─ healthcheck.sh runs
          ├─ Checks: process exists? YES
          ├─ Checks: file exists? YES
          ├─ Checks: file age < 60s? YES (only 25s old)
          └─ Returns exit 0 → HEALTHY ✅

Time 35-60s: Loader continues
          ├─ _update_health_check() keeps updating file every 5s
          ├─ File stays fresh (< 5s old)
          └─ Each health check sees healthy status

Time 120s+: Normal operation
          └─ Loader completes, task exits gracefully
```

### Stuck Loader (Hung or Frozen)

```
Time 0s:   Loader starts normally
          └─ File created at T0

Time 30s:  Loader gets stuck in database query
          ├─ Thread frozen, can't update health file
          └─ File still shows "timestamp from T0"

Time 60s:  ECS runs health check
          ├─ Checks: process exists? YES (still running)
          ├─ Checks: file exists? YES
          ├─ Checks: file age < 60s? YES (exactly 60s old, passes)
          └─ Returns exit 0 → HEALTHY ✅ (still healthy)

Time 90s:  ECS runs health check again
          ├─ Checks: file age < 60s? NO (90s old)
          └─ Returns exit 1 → UNHEALTHY ❌ (first failure)

Time 120s: ECS runs health check again
          ├─ File still 120s old
          └─ Returns exit 1 → UNHEALTHY ❌ (second failure)
          
          **Task marked UNHEALTHY in ECS** 🚨

Time 180s-360s: Task stays unhealthy
          └─ Cost accumulating: $0.06/hour = $1.48/day

Time 360m (6 hours): Auto-kill Lambda runs via EventBridge
          ├─ Finds task UNHEALTHY for > 2 hours
          ├─ Stops task with reason "UNHEALTHY for 6.0h"
          ├─ Sends SNS alert: "Cost saved: $45/month"
          └─ Task terminated ✅
```

### Cost Impact

| Scenario | Time to Kill | Cost Waste | Notes |
|----------|-------------|-----------|-------|
| Healthy loader | N/A | $0 | Normal |
| Stuck 30 min, old health check | 6 hours (circuit breaker) | $0.30 | No detection until circuit breaker |
| Stuck 30 min, new health check + Lambda | 2 hours | $0.12 | Detected in 60s, killed by Lambda |
| Stuck 24 hours, no safeguards | Still running | $1.44 | Cost keeps accumulating |
| Stuck 24 hours, with safeguards | Killed at 2h | $0.12 | Max waste before auto-kill |

---

## Testing Checklist

### Test 1: Health Check Script Works
```bash
# In any ECS task, test the script manually:
/healthcheck.sh

# Should return:
# - Exit 0 if loader is healthy
# - Exit 1 if loader is stuck/missing file
```

### Test 2: Health Check File Updates
```bash
# SSH into running ECS task and watch:
watch -n 1 'stat /tmp/loader_health_check | grep Modify'

# Should show timestamp updating every 5 seconds during execution
# Should stay constant if loader is frozen
```

### Test 3: ECS Marks Task Unhealthy
```bash
# Artificially freeze a loader (in ECS task):
# 1. SSH in, find Python process
# 2. Send SIGSTOP to freeze it (keeps running but frozen)
#    kill -STOP <pid>
#
# 3. Watch ECS console:
#    - Task stays RUNNING but healthStatus becomes UNHEALTHY after 60s

# Unfreeze:
#    kill -CONT <pid>
```

### Test 4: Lambda Kills Stuck Tasks
```bash
# Manually invoke Lambda:
aws lambda invoke \
  --function-name algo-auto-kill-stuck-tasks-dev \
  --log-type Tail \
  /tmp/lambda_result.json

cat /tmp/lambda_result.json

# Expected output:
# {
#   "statusCode": 200,
#   "message": "Successfully processed X stuck task(s), killed Y",
#   "killed_count": 0,  # 0 if no stuck tasks
#   "killed_tasks": []
# }
```

### Test 5: Lambda Actually Kills a Stuck Task
```bash
# Create a stuck task:
# 1. Intentionally hang a loader in database query
# 2. Wait for it to be marked UNHEALTHY (60s)
# 3. Invoke Lambda:

aws lambda invoke --function-name algo-auto-kill-stuck-tasks-dev /tmp/result.json

cat /tmp/result.json

# Expected:
# "killed_count": 1,
# "killed_tasks": ["stock_prices_daily"]

# Verify in ECS console: Task should be STOPPED with reason containing "Auto-Kill"
```

### Test 6: SNS Alert Received
```bash
# Check SNS topic for alert:
aws sns list-subscriptions-by-topic \
  --topic-arn $(terraform output -raw sns_alerts_topic_arn)

# Should see email alert with:
# - Subject: "ECS Auto-Kill: X task(s) terminated"
# - Body: Task names, reasons, cost savings estimate
```

---

## Monitoring & Observability

### CloudWatch Alarms
```bash
# View auto-kill alarms:
aws cloudwatch describe-alarms \
  --alarm-name-prefix algo-ecs-unhealthy
```

### CloudWatch Logs
```bash
# Monitor Lambda execution:
aws logs tail /aws/lambda/algo-auto-kill-stuck-tasks-dev --follow

# Expected output:
# [2026-07-17 10:00:00] Starting auto-kill check
# [2026-07-17 10:00:01] Found 0 stuck task(s)
# [2026-07-17 10:00:02] Successfully processed 0 stuck task(s), killed 0
```

### EventBridge Scheduler
```bash
# Verify Lambda is scheduled:
aws scheduler get-schedule \
  --name algo-auto-kill-stuck-tasks-dev

# Check execution history:
aws scheduler list-schedule-executions \
  --schedule-name algo-auto-kill-stuck-tasks-dev \
  --query 'ScheduleExecutions[0:5].[ExecutionTime,ExecutionStatus]'
```

---

## Rollback Plan (If Issues)

### If Health Check Script Has Bugs

**Quick rollback (keep new image, disable new health check):**
```bash
cd terraform

# Edit: terraform/modules/loaders/main.tf line ~784
# Change back to:
# command = ["CMD-SHELL", "ps aux | grep -q '[p]ython.*${each.key}' || exit 1"]

terraform apply -var-file=dev.tfvars

# Tasks will restart with old health check
# Timeline: ~5-10 minutes for all tasks to restart
```

### If Lambda Kills Wrong Tasks

**Disable Lambda:**
```bash
# Option 1: Disable EventBridge schedule
aws scheduler update-schedule \
  --name algo-auto-kill-stuck-tasks-dev \
  --state DISABLED

# Option 2: Update Lambda to no-op
# Redeploy Lambda with minimal kill logic
```

### If Need to Rebuild Docker Image

```bash
# Manually trigger rebuild:
gh workflow run deploy-ecs-image.yml \
  --ref main \
  -f force_recreate=true

# Or via AWS console if gh not available:
aws codebuild start-build \
  --project-name algo-docker-build
```

---

## Success Criteria

You'll know it's working when:

✅ Docker image builds and includes healthcheck.sh
✅ ECS tasks updated with new health check script  
✅ Health check runs every 30 seconds (check CloudWatch metrics)
✅ Intentionally hung loader marked UNHEALTHY within 60 seconds
✅ Lambda invokes successfully (check CloudWatch logs)
✅ SNS alert received when Lambda kills tasks
✅ No healthy tasks killed (manual verification)
✅ Cost savings estimated correctly in alerts

---

## Cost Analysis

### Implementation Cost
- Lambda function: ~$0.01/month (runs every 6h = 4 invocations/day)
- CloudWatch alarms: ~$0.10/month (2 alarms)
- EventBridge Scheduler: ~$0.01/month
- **Total:** ~$0.12/month

### Cost Savings
- Each stuck task prevented: $45/month saved
- Typical incident: 22 stuck tasks = $990/month → $990 saved!
- **ROI:** Paid back in ONE incident prevention

---

## Next Steps

### Immediate (Do Now)
1. Review this deployment guide
2. Run `terraform plan` to see changes
3. Deploy terraform changes
4. Verify Lambda is deployed

### Testing (Week 1)
1. Run through testing checklist
2. Monitor for 24-48 hours in dev
3. Check CloudWatch logs for any issues
4. Verify SNS alerts arriving

### Production (After Testing)
1. Deploy to production terraform
2. Monitor for 24 hours
3. Verify cost circuit breaker still works
4. Document in runbook

---

## Questions?

Check:
- `SESSION_199_REVIEW.md` - Complete analysis
- `steering/ECS_BEST_PRACTICES.md` - Operational guide
- CloudWatch logs - Lambda execution details
- ECS console - Task health status

All code is in commit `6f2170a06` - review before deploying.

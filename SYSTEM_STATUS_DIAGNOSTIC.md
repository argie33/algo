# System Status & Fix Plan (2026-06-14)

## Current State Summary

### ✅ What's Working
- Lambda API (`algo-api-dev`): **ACTIVE** ✓
  - RDS connection pool: **HEALTHY** (23/500 connections in use)
  - All route imports: **SUCCESSFUL** (0 failures)
  - Responding to requests: **YES**
  
- Step Functions State Machines: **DEPLOYED** ✓
  - algo-eod-pipeline-dev: EXISTS
  - algo-morning-prep-pipeline-dev: EXISTS
  - algo-intraday-afternoon-update-dev: EXISTS
  - algo-intraday-preclose-update-dev: EXISTS
  - Manual execution test: **WORKS** ✓

- EventBridge Scheduler: **CONFIGURED** ✓
  - morning-pipeline: ENABLED (2:00 AM ET cron schedule)
  - eod-pipeline: ENABLED (4:05 PM ET cron schedule)
  - IAM Role has states:StartExecution permission: **YES**

### ❌ What's Broken
- **DATA FRESHNESS**: **CRITICAL**
  - Signals: 123 hours OLD (5+ days)
  - Status: "degraded"
  - Reason: Loaders haven't run recently
  
- **Terraform State**: **LOST**
  - No terraform.tfstate file
  - Only errored.tfstate exists (3.4MB from previous failed run)
  - Plan shows ~500+ resources will be created (wrong state)
  
- **Automatic Pipeline Execution**: **UNKNOWN**
  - Schedules are configured to run, but no recent executions in Step Functions history
  - Morning pipeline should have run 1h ago (2 AM ET was 6 hours ago)
  - Last known execution: NEVER (empty history)

---

## Root Cause Analysis

### Why Loaders Aren't Running

**Primary hypothesis:** Terraform state lost between deployments
- Infrastructure exists in AWS (we can see Step Functions, Lambda, RDS Proxy)
- But terraform has no record of it
- This likely happened during a failed `terraform apply` or state bucket access issue
- Without state, terraform can't manage/update the scheduler targets

**Secondary possibility:** EventBridge Scheduler not actually invoking the state machines
- Even though config looks correct in code
- Actual AWS resources might have stale or incorrect target bindings

---

## What Needs to Happen

### IMMEDIATE ACTIONS (Next 2 hours)

#### 1. Get Fresh Data Flowing (Unblock Everything)
```bash
# Manually trigger morning pipeline to load current data
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev \
  --name "urgent-data-load-$(date +%s)" \
  --input '{"execution_name":"urgent-data-load"}'

# Monitor execution (should take 60-120 minutes)
# Check logs at: /ecs/algo-stock-prices-daily-loader
```

Expected result: 
- Data freshness resets to TODAY
- API health checks pass
- Degraded mode clears
- Trading can resume

#### 2. Recover Terraform State
**Option A: Restore from S3 backup (if available)**
```bash
aws s3 cp s3://stocks-terraform-state/stocks/terraform.tfstate terraform.tfstate
terraform state list  # Should show 500+ resources
```

**Option B: Rebuild state from AWS (risky, experts only)**
- Import all existing resources into terraform
- Or destroy all and redeploy from scratch

**Option C: Continue without terraform for now (dangerous)**
- Manually manage infrastructure via CLI/console
- High risk of drift and data loss

---

## Expected Timeline

| Step | Duration | Owner | Status |
|------|----------|-------|--------|
| 1. Trigger data loader | Start now | Auto (already running test) | IN PROGRESS |
| 2. Wait for fresh prices | 60-120 min | Step Functions | PENDING |
| 3. Wait for swing scores | 30+ min after prices | Step Functions | PENDING |
| 4. API health resets | ~5 min after scores | Lambda | PENDING |
| 5. Recover terraform state | 30-60 min | DevOps | BLOCKED (permissions?) |
| 6. Full system operational | 4+ hours | Combined | BLOCKED |

---

## Next Steps

### To Unblock Trading TODAY:
1. ✅ Allow morning pipeline execution to complete
2. ✅ Verify data freshness resets
3. ✅ Test API endpoints (should return fresh data)
4. ✅ Clear orchestrator halt flag if it's set
5. ✅ Resume trading

### To Stabilize System:
1. Recover terraform state (S3 backup or manual import)
2. Verify EventBridge Scheduler is actually firing at scheduled times
3. Monitor first automated pipeline run (morning or EOD)
4. Add CloudWatch alarms for pipeline failures

### To Prevent Future Issues:
1. Enable daily terraform plan validation in CI/CD
2. Backup terraform state before any apply
3. Add metric for "data freshness age" to dashboard
4. Alert if no loader execution in 24h

---

## Files to Monitor

| Path | What to Check |
|------|---------------|
| `/ecs/algo-stock-prices-daily-loader` | Price loader progress |
| `/ecs/algo-swing-trader-scores-loader` | Scores loader progress |
| `algo_orchestrator_state` (DynamoDB) | Halt flag status |
| CloudWatch Metrics → States → ExecutionsFailed | Pipeline failures |

---

## Commands to Run Now

```bash
# Monitor currently running pipeline
EXEC_ARN="arn:aws:states:us-east-1:626216981288:execution:algo-morning-prep-pipeline-dev:test-manual-1781434260"
aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" | grep status

# Check ECS task logs
aws logs filter-log-events \
  --log-group-name /ecs/algo-stock-prices-daily-loader \
  --start-time $(($(date +%s)*1000 - 7200000)) \
  | grep -E "Loading|Completed|ERROR"

# Check DynamoDB for halt flag
aws dynamodb get-item \
  --table-name algo_orchestrator_state-dev \
  --key '{"key":{"S":"orchestrator_halt"}}'

# Once data is fresh, clear degraded mode
# (Only if data is actually fresh - verify prices loaded)
aws dynamodb put-item \
  --table-name algo_orchestrator_state-dev \
  --item '{"key":{"S":"orchestrator_halt"},"halt_flag":{"BOOL":false}}'
```

---

## Risk Assessment

🔴 **CRITICAL RISK**: Terraform state lost
- Could lose infrastructure definition
- Manual management needed until recovered
- Recommend immediate S3 state recovery attempt

🟡 **HIGH RISK**: Data freshness at 0 (must load immediately)
- Trading cannot happen with 5-day-old data
- Orchestrator Phase 1 will set halt flag
- Pipeline must complete successfully

🟢 **LOW RISK**: EventBridge Scheduler configuration
- Code is correct, IAM permissions are correct
- Just need to verify actual AWS resources match code

---

## Success Criteria

✅ **System is fully operational when:**
1. Data freshness < 24 hours (preferably same-day)
2. Health endpoint returns `status: "healthy"`
3. API endpoints return fresh market data (not stale)
4. Orchestrator halt flag is cleared
5. Terraform state is recovered/rebuilt
6. Scheduled pipelines auto-execute at correct times

✅ **This fix is DONE when:**
- All 5 criteria above are met
- First automated pipeline (morning or EOD) executes successfully
- Fresh data loads without manual intervention
- Trading resumes normally

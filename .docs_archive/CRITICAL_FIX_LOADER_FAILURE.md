# CRITICAL FIX - Loader Orchestration System Failure

**Status:** EMERGENCY - System down, data not updating for days  
**Root Cause:** Step Functions failing to execute loaders  
**Impact:** All data tables stale (4-30 days old)  
**Severity:** CRITICAL

---

## Issue Summary

### What's Broken
```
SYSTEM STATE:
- EventBridge rule configured to run at 20:41 UTC ✓
- Step Functions orchestrator exists ✓
- 10+ loaders defined in CloudFormation ✓
- 7 buyselldaily tasks running continuously ✓

BUT:
- Step Functions executions ALL FAILING
- Data hasn't updated in 4-30 days
- Latest Step Functions failure: 5 hours ago
- Error: "One or more loader stages failed after retries"
```

### Data Freshness Status
```
price_daily         - 7 days old (last: 2026-04-24)
price_weekly        - 4 days old (last: 2026-04-27)
price_monthly       - 30 days old (last: 2026-04-01)
etf_price_daily     - 7 days old
etf_price_weekly    - 7 days old
buy_sell_daily      - 7 days old
technical_data      - 7 days old
earnings_history    - TABLE ERROR
stock_scores        - TABLE ERROR

RESULT: Complete data stagnation
```

---

## Root Cause Analysis

### Theory 1: Task Definition Mismatch
Step Functions may be trying to run task definitions that don't exist or are outdated.

**Evidence:**
- Task defs exist (technicalsdaily-loader:51, etc) 
- But "algo-loadpricedaily:1" doesn't exist (error when trying to run)
- Step Functions may be referencing old names

### Theory 2: Network Configuration Error
ECS tasks may be failing due to VPC/subnet configuration.

**Evidence:**
- Task logs show network attachment details
- Tasks may be starting but subnet/security group blocking traffic
- DB connection failing -> task exits

### Theory 3: Missing Environment Variables
New task definitions may not have DB credentials configured.

**Evidence:**
- Tasks run but exit immediately
- No logs showing actual errors
- Could be silent credential failures

---

## Immediate Fix Plan

### Step 1: Identify Correct Task Definition Names
```bash
# List all loader task definitions
aws ecs list-task-definitions --family-prefix="" --sort DESC | grep -i load | head -20
```

### Step 2: Check Latest Task Definition Configuration
```bash
# Get latest task definition for a loader
aws ecs describe-task-definition --task-definition technicalsdaily-loader:51 | jq '.taskDefinition'
```

### Step 3: Verify Environment Variables
Check if task definition has:
- DB_HOST
- DB_PORT
- DB_USER
- DB_PASSWORD (or DB_SECRET_ARN for AWS Secrets Manager)
- AWS_REGION
- LOG_LEVEL=INFO or DEBUG

### Step 4: Test Single Loader
```bash
# Manually run a single loader to see actual error
aws ecs run-task \
  --cluster stocks-cluster \
  --task-definition technicalsdaily-loader:51 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0142dc004c9fc3e0c],assignPublicIp=DISABLED}"

# Check logs immediately
aws logs tail /ecs/technicalsdaily-loader --follow
```

### Step 5: Fix Step Functions Orchestrator
The Step Functions state machine may be:
1. Using wrong task definition names
2. Missing retry logic
3. Not passing environment variables correctly

**Action:** 
- Review `template-app-ecs-tasks.yml` CloudFormation
- Verify Step Functions JSON state machine definition
- Check task definition references in orchestrator

---

## Recovery Procedure

### Phase 1: Diagnostic (Now)
```bash
1. Check all task definition names and latest versions
2. Get latest task definition and examine environment variables
3. Check Step Functions state machine definition
4. Check CloudWatch Logs for actual task failures
```

### Phase 2: Fix (Immediate)
```bash
1. Create/update task definitions with correct environment variables
2. Update Step Functions orchestrator to use correct task definition names
3. Manually test one loader
4. Fix any network/credential issues found
```

### Phase 3: Redeploy (Same day)
```bash
1. Push fixed CloudFormation templates
2. Update Step Functions state machine
3. Trigger manual loader run
4. Verify data updates
5. Re-enable EventBridge schedule
```

### Phase 4: Reload Stale Data
```bash
1. Run all 39 loaders in correct dependency order
2. Verify data completeness
3. Monitor for errors
4. Document what went wrong
```

---

## GitHub Actions Context

The recent push (commit 52a7b7d9a) with Wave 1 optimizations should have triggered:
1. Docker build for loaders
2. Push to ECR
3. Update CloudFormation stack
4. Update task definitions

**Check:** Did the workflow complete successfully? Or did it fail silently?

---

## Severity Assessment

**Impact Level:** CRITICAL
- All loader data is stale
- Frontend will show old data
- Analytics/dashboards unreliable
- User-facing application degraded

**Time to Fix:** 1-2 hours
- Diagnose: 15-20 minutes
- Fix: 30-40 minutes
- Verify: 10-15 minutes
- Reload data: 30-60 minutes

**Business Impact:**
- Trading signals based on 7-day-old data
- Portfolio analytics incorrect
- Market opportunities missed

---

## Never-Settle Action Items

After fixing this:
1. Add alerting for stale data (e.g., if no update in 24 hours, alert)
2. Add Step Functions execution monitoring
3. Add health check endpoint that verifies data freshness
4. Add automatic rollback on loader failure
5. Document exact task definition names and versions

---

## Files to Modify

1. `.github/workflows/deploy-app-stocks.yml` - Verify it updates task definitions
2. `template-app-ecs-tasks.yml` - Check task definition environment variables
3. Step Functions state machine JSON - Check task definition names
4. Monitor system - Add data freshness checks and alerts

---

## Next Steps

**IMMEDIATE:**
1. Run diagnostic commands above
2. Get actual error messages from failed ECS tasks
3. Post findings in CRITICAL_FIX_DIAGNOSTIC.md

**DO NOT:**
- Manually edit task definitions (use CloudFormation)
- Force re-run Step Functions until root cause found
- Assume issue is resolved without testing

**DO:**
- Get actual error logs
- Trace Step Functions execution history
- Verify every fix with test run

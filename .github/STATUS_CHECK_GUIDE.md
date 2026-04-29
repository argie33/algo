# Batch 5 - Status Check Guide

**Last Push:** Just now (commits a3f468c04 + ff45d0fae + c453d03e1)
**Expected Workflow Start:** 1-2 minutes after push

---

## Quick Status Check (Pick One)

### Option 1: GitHub Actions (BEST - Real-time)
**URL:** https://github.com/argie33/algo/actions

**Look for:**
- Workflow: "Data Loaders Pipeline"
- Latest run should show 4 loaders detected (annualcashflow, quarterlycashflow, factormetrics, stockscores)

**Status Indicators:**
- 🟠 Orange circle = Running
- ✅ Green checkmark = Success
- ❌ Red X = Failed
- ⏳ Queued = Waiting to run

---

### Option 2: AWS ECS (Most Detailed)
**AWS Console → ECS → Clusters → stocks-cluster**

**Look for 4 tasks:**
- Task name: `loader-annualcashflow-*`
- Task name: `loader-quarterlycashflow-*`
- Task name: `loader-factormetrics-*`
- Task name: `loader-stockscores-*`

**Status Values:**
- `PROVISIONING` = Starting up
- `PENDING` = Waiting for resources
- `ACTIVATING` = Loading container
- `RUNNING` = Currently executing
- `DEACTIVATING` = Shutting down
- `STOPPING` = Stopped
- `DEPROVISIONING` = Cleaned up

---

### Option 3: CloudWatch Logs (Most Detail)
**AWS Console → CloudWatch → Log Groups**

**Search for:** `/aws/ecs/stocks-loader-tasks`

**Watch for log streams:**
- `loader-annualcashflow-*` - Look for "Starting loadannualcashflow.py"
- `loader-quarterlycashflow-*` - Look for "Starting loadquarterlycashflow.py"
- `loader-factormetrics-*` - Look for "Starting loadfactormetrics.py"
- `loader-stockscores-*` - Look for "Starting loadstockscores.py"

**Key Log Messages to Watch:**
```
✓ SUCCESS: "Completed: X rows"
✓ SUCCESS: "COMPLETE - ..." 
✗ FAILURE: "ERROR:", "Exception:", "Failed to connect"
```

---

## Expected Progress

### Phase 1: Detection (T+0 to T+2 min)
```
GitHub Actions detects push
  → Workflow "Data Loaders Pipeline" starts
  → "Detect Changes" job runs
  → Should find 4 loaders with changed files
```
**Check GitHub Actions:** Look for orange "Detect Changes" job running

### Phase 2: Infrastructure (T+2 to T+10 min)
```
Deploy Infrastructure job runs
  → Creates/updates ECS task definitions
  → Validates CloudFormation stack
  → Prepares ECR images
```
**Check GitHub Actions:** Look for orange "Deploy Infrastructure" job

### Phase 3: Build & Push Images (T+10 to T+25 min)
```
For each loader:
  → Build Docker image
  → Tag with commit hash
  → Push to ECR registry
```
**Check GitHub Actions:** Look for orange "Execute Loaders" job with matrix

### Phase 4: Execute Tasks (T+25 to T+30+ min per loader)
```
Launch ECS Fargate tasks:
  → annualcashflow: 60-90 min
  → quarterlycashflow: 60-90 min
  → factormetrics: 120-180 min
  → stockscores: 30-60 min
```
**Check CloudWatch:** Look for log messages showing data being loaded

### Phase 5: Completion (T+5-7 hours total)
```
All 4 tasks complete
  → Each exits with code 0 (success)
  → Data populated in database
  → Tables show row counts
```
**Check ECS:** Look for "STOPPED" status with exit code 0

---

## Known Issues to Watch For

### Issue 1: Workflow doesn't start
**Symptom:** No "Data Loaders Pipeline" workflow visible
**Cause:** GitHub hasn't processed the push yet
**Action:** Wait 2-3 minutes and refresh

### Issue 2: "No loaders detected"
**Symptom:** Workflow runs but finds 0 loaders
**Cause:** File changes not detected (cache issue)
**Action:** 
1. Check GitHub Actions - "Generate loader matrix" step
2. Look for "Debug: Loader files found:" message
3. Should show annualcashflow, quarterlycashflow, factormetrics, stockscores

### Issue 3: "Cannot find Dockerfile"
**Symptom:** Workflow fails with "Dockerfile.load* not found"
**Cause:** File doesn't exist in repo
**Action:**
1. Verify all 4 Dockerfiles exist locally
2. Push again if needed

### Issue 4: ECS task fails to launch
**Symptom:** Task status shows "STOPPED" with non-zero exit code
**Cause:** Database connection failed or loader crashed
**Action:**
1. Check CloudWatch logs for error messages
2. Look for "ERROR" or "Exception" in logs
3. Common: "connection refused" (DB auth) or "No such file" (missing data)

### Issue 5: Task runs but completes immediately
**Symptom:** Task shows STOPPED with exit code 0 but took < 10 seconds
**Cause:** No symbols loaded or early exit
**Action:**
1. Check CloudWatch logs for actual data loading
2. Look for "Loading X symbols..." message
3. Verify stock_symbols table has data

---

## Quick Database Check

Once tasks complete, verify data was loaded:

**If you have psql access:**
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks -c "
SELECT 'annual_cash_flow' as table_name, COUNT(*) as rows FROM annual_cash_flow
UNION
SELECT 'quarterly_cash_flow', COUNT(*) FROM quarterly_cash_flow
UNION
SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
UNION
SELECT 'stock_scores', COUNT(*) FROM stock_scores;"
```

**Expected output:**
```
     table_name      | rows
---------------------+------
 annual_cash_flow    | 4500+
 quarterly_cash_flow | 4500+
 growth_metrics      | 4500+
 stock_scores        | 4500+
```

---

## Status Summary Template

**Use this to track progress:**

```
BATCH 5 EXECUTION STATUS
========================

Current Time: [YOUR TIME]
Time Since Push: [DURATION]

GitHub Actions Workflow:
  - Detect Changes: [STATUS]
  - Deploy Infrastructure: [STATUS]
  - Execute Loaders: [STATUS]
  - Deployment Summary: [STATUS]

Individual Loaders:
  - annualcashflow: [RUNNING/STOPPED/FAILED/PENDING]
  - quarterlycashflow: [RUNNING/STOPPED/FAILED/PENDING]
  - factormetrics: [RUNNING/STOPPED/FAILED/PENDING]
  - stockscores: [RUNNING/STOPPED/FAILED/PENDING]

Latest Log Messages:
  [Copy relevant messages from CloudWatch]

Data Loaded:
  - annual_cash_flow: [X rows] ✓/✗
  - quarterly_cash_flow: [X rows] ✓/✗
  - growth_metrics: [X rows] ✓/✗
  - stock_scores: [X rows] ✓/✗

Overall Status: [NOT STARTED/QUEUED/RUNNING/COMPLETED/FAILED]
```

---

## Summary

- **Latest Push:** Just moments ago (commit a3f468c04)
- **Workflow Should Start:** Within 1-2 minutes
- **Expected Total Time:** 5-7 hours for all 4 loaders
- **Best Status Check:** GitHub Actions workflow page
- **Detailed Status Check:** CloudWatch logs + ECS console

**Next Step:** Check GitHub Actions in 2-3 minutes to see if workflow started.

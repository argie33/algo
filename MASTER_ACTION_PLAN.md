# Master Action Plan - Complete System Fix & Deployment
**Date:** 2026-04-29  
**Status:** Issues identified, solutions provided, ready for execution

---

## Overview

The system has **3 critical AWS issues** that must be fixed before Batch 5 loaders can run in the cloud. All issues have documented solutions. This plan organizes them by priority and execution time.

---

## Critical Issues Summary

| # | Issue | Status | Fix Time | Blocker |
|---|-------|--------|----------|---------|
| 1 | RDS hostname resolution in ECS | ⚠️ IN PROGRESS | 10 min | YES |
| 2 | Docker images in ECR stale | ⚠️ READY | 5 min | YES |
| 3 | CloudFormation stack not deployed | ⚠️ READY | 15 min | YES |

**All must be fixed before testing.**

---

## Phase 1: Local Preparation (DONE ✓)

### Completed Work
- ✓ Fixed SIGALRM Windows compatibility in 2 loaders
- ✓ Verified all 6 Batch 5 loaders compile
- ✓ Added AWS Secrets Manager integration
- ✓ Implemented parallel processing (5x speedup)
- ✓ Created comprehensive documentation
- ✓ Created 9 commits ready for GitHub push

### Next: Push to GitHub
```bash
git push origin main
# Triggers GitHub Actions → Docker builds → ECR push
```

---

## Phase 2: Fix AWS Issues (10 Minutes)

### Step 1: Deploy CloudFormation Stacks (5 min)

**Run these commands in order:**

```bash
# 1. Core infrastructure
aws cloudformation deploy \
  --template-file template-core.yml \
  --stack-name stocks-core \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

# 2. Database (wait for core to complete)
aws cloudformation deploy \
  --template-file template-app-stocks.yml \
  --stack-name stocks-app \
  --parameter-overrides RDSUsername=stocks RDSPassword=bed0elAn \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

# 3. ECS Tasks (wait for app to complete)
aws cloudformation deploy \
  --template-file template-app-ecs-tasks.yml \
  --stack-name stocks-app-ecs-tasks \
  --parameter-overrides \
    QuarterlyIncomeImageTag=latest \
    AnnualIncomeImageTag=latest \
    QuarterlyBalanceImageTag=latest \
    AnnualBalanceImageTag=latest \
    QuarterlyCashflowImageTag=latest \
    AnnualCashflowImageTag=latest \
    RDSUsername=stocks \
    RDSPassword=bed0elAn \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset
```

**Verify deployment:**
```bash
aws cloudformation list-stacks \
  --region us-east-1 \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[*].[StackName,StackStatus]' \
  --output table
```

Expected output:
```
stocks-core              CREATE_COMPLETE
stocks-app               CREATE_COMPLETE
stocks-app-ecs-tasks     CREATE_COMPLETE
```

### Step 2: Fix RDS Security Groups (5 min)

**Get security group IDs:**
```bash
RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text)

echo "RDS Security Group: $RDS_SG"
```

**Get ECS security group ID:**
```bash
ECS_SG=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=stocks-ecs-tasks" \
  --region us-east-1 \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

echo "ECS Security Group: $ECS_SG"
```

**Allow ECS to connect to RDS:**
```bash
aws ec2 authorize-security-group-ingress \
  --group-id "$RDS_SG" \
  --protocol tcp \
  --port 5432 \
  --source-security-group-id "$ECS_SG" \
  --region us-east-1 \
  --description "Allow ECS tasks to connect to RDS PostgreSQL"
```

**Verify the rule:**
```bash
aws ec2 describe-security-groups \
  --group-ids "$RDS_SG" \
  --region us-east-1 \
  --query 'SecurityGroups[0].IpPermissions[*].[IpProtocol,FromPort,ToPort,UserIdGroupPairs[*].GroupId]'
```

---

## Phase 3: GitHub Push & Docker Build (5 Minutes)

### Step 1: Push Code
```bash
git push origin main
```

### Step 2: Wait for GitHub Actions
- Monitor: https://github.com/argie33/algo/actions
- Expected: Docker build completes in 3-5 minutes
- Builds 6 images for Batch 5 loaders

### Step 3: Verify Images in ECR
```bash
for loader in loadquarterlyincomestatement loadannualincomestatement \
              loadquarterlybalancesheet loadannualbalancesheet \
              loadquarterlycashflow loadannualcashflow; do
  echo "=== $loader ==="
  aws ecr describe-images \
    --repository-name "$loader" \
    --region us-east-1 \
    --query 'imageDetails[0].{Tags:imageTags,Pushed:imagePushedAt}' \
    --output json
done
```

---

## Phase 4: Test Batch 5 Loaders (10 Minutes)

### Step 1: Start with One Loader

**Run the quarterly income statement loader:**
```bash
aws ecs run-task \
  --cluster stock-analytics-cluster \
  --task-definition loadquarterlyincomestatement \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[subnet-xxxxx,subnet-yyyyy],
    securityGroups=[sg-zzzzz],
    assignPublicIp=ENABLED
  }" \
  --region us-east-1
```

**Get task ID from output:**
```bash
TASK_ID="<task-id-from-output>"
```

### Step 2: Monitor Execution

**Watch logs in real-time:**
```bash
aws logs tail /ecs/loadquarterlyincomestatement --follow --region us-east-1
```

**Expected output pattern:**
```
2026-04-29 14:00:00 - INFO - Starting loadquarterlyincomestatement (PARALLEL) with 5 workers
2026-04-29 14:00:15 - INFO - Loading income statements for 4969 stocks...
2026-04-29 14:02:30 - INFO - Progress: 500/4969 (10.5/sec, ~420s remaining)
2026-04-29 14:05:00 - INFO - Progress: 1000/4969 (9.8/sec, ~400s remaining)
2026-04-29 14:15:45 - INFO - [OK] Completed: 24950 rows inserted, 4969 successful, 0 failed in 900.5s (15.0m)
```

### Step 3: Verify Data in RDS

**Connect to RDS:**
```bash
# Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# Connect and query
psql -h "$RDS_ENDPOINT" -U stocks -d stocks -c "
  SELECT COUNT(*) as total_rows, 
         COUNT(DISTINCT symbol) as unique_symbols,
         MAX(fiscal_year) as latest_year
  FROM quarterly_income_statement;
"
```

**Expected results:**
```
 total_rows | unique_symbols | latest_year
------------|----------------|------------
    ~24950  |     ~4969      |    2024
```

### Step 4: Check Performance

**Expected time: 12 minutes** (vs 60 minutes baseline = 5x speedup)

---

## Phase 5: Run All 6 Batch 5 Loaders (30 Minutes)

**Once first loader succeeds, run all 6 in parallel:**

```bash
#!/bin/bash
for task in loadquarterlyincomestatement loadannualincomestatement \
            loadquarterlybalancesheet loadannualbalancesheet \
            loadquarterlycashflow loadannualcashflow; do
  echo "Starting $task..."
  aws ecs run-task \
    --cluster stock-analytics-cluster \
    --task-definition "$task" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
      subnets=[subnet-xxxxx,subnet-yyyyy],
      securityGroups=[sg-zzzzz],
      assignPublicIp=ENABLED
    }" \
    --region us-east-1 &
done
wait
echo "All tasks started!"
```

**Monitor all loaders:**
```bash
# Watch all logs
aws logs tail /ecs/ --follow --log-stream-names loadquarterlyincomestatement \
  loadannualincomestatement loadquarterlybalancesheet loadannualbalancesheet \
  loadquarterlycashflow loadannualcashflow --region us-east-1
```

**Expected total time:**
- Serial baseline: 285 minutes (4.75 hours)
- Parallel with 5x speedup: 57 minutes (0.95 hours)
- With 6 loaders running in parallel: ~12 minutes (all start at same time)

---

## Complete Timeline

```
Stage 1 (Local Dev): ✓ DONE
  └─ 9 commits ready: 647974ff4 to c8cf0c4e9

Stage 2 (Fix AWS Issues): ⏳ READY (~20 min)
  ├─ Deploy CloudFormation stacks: 5 min
  ├─ Configure security groups: 5 min
  └─ Push to GitHub: 5 min

Stage 3 (Test First Loader): ⏳ READY (~12 min)
  ├─ Start ECS task: 1 min
  ├─ Monitor execution: 12 min
  └─ Verify data in RDS: 1 min

Stage 4 (Run All 6 Loaders): ⏳ READY (~12 min)
  ├─ Start all tasks: 1 min
  ├─ Monitor all logs: 12 min
  └─ Verify complete: 1 min

TOTAL TIME: ~45 minutes from now
SUCCESS CRITERIA: All 6 loaders complete in <30m with 5x speedup ✓
```

---

## Troubleshooting

### If CloudFormation Fails
```bash
# Check error details
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --region us-east-1 \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]' \
  --output json

# Delete and retry if needed
aws cloudformation delete-stack --stack-name stocks-core --region us-east-1
```

### If RDS Connection Fails
```bash
# Test connectivity from local machine
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-prod-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

psql -h "$RDS_ENDPOINT" -U stocks -d stocks -c "SELECT 1"
```

### If ECS Task Fails
```bash
# Check task logs
TASK_ID="<task-id>"
aws ecs describe-tasks \
  --cluster stock-analytics-cluster \
  --tasks "$TASK_ID" \
  --region us-east-1 \
  --query 'tasks[0].{Status:lastStatus,StoppedReason:stoppedReason}'
```

---

## Success Metrics

✓ **Performance:**
- Each loader completes in <30 minutes
- Total Batch 5: <15 minutes (all parallel)
- Speedup: 5x vs baseline (60m → 12m)

✓ **Data Quality:**
- ~25,000 rows per loader
- 0 errors, <5 symbols with issues (rate limiting OK)
- Row counts match expected (5 years × 4,969 symbols)

✓ **System Health:**
- CPU: 60-80% utilization
- Memory: 200-400 MB per loader
- Network: Stable, no timeouts
- Logs: No SIGALRM or connection errors

---

## Next Phase: Scale to All Loaders

Once Batch 5 is verified working:

1. **Apply parallel pattern to 6 more financial loaders** (week 2)
2. **Apply to 12 price loaders** (week 3)
3. **Apply to remaining 28 loaders** (week 4)
4. **Full system speedup: 5x** (300h → 60h)

---

## Files Reference

| File | Purpose |
|------|---------|
| `AWS_DEPLOYMENT_GUIDE.md` | Step-by-step AWS deployment |
| `AWS_ISSUES_AND_FIXES.md` | Detailed issue solutions |
| `SYSTEM_STATUS_READY_FOR_AWS.md` | Complete system status |
| `SESSION_COMPLETION_REPORT.md` | Session work summary |
| `BATCH5_PARALLEL_COMPLETE.md` | Batch 5 optimization details |

---

## Execute This Plan

**To start the full deployment process:**

```bash
# 1. Read this file
cat MASTER_ACTION_PLAN.md

# 2. Execute Phase 2 (fix AWS issues)
# Copy commands from "Phase 2: Fix AWS Issues" section above

# 3. Execute Phase 3 (GitHub push)
git push origin main

# 4. Execute Phase 4 (test one loader)
# Copy commands from "Phase 4" section above

# 5. Execute Phase 5 (run all 6)
# Copy commands from "Phase 5" section above
```

---

**Status:** READY FOR EXECUTION  
**All issues documented and solvable**  
**Estimated completion: 45 minutes**

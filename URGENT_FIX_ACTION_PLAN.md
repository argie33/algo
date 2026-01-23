# 🚨 URGENT: Fix ECS Loaders NOW - Action Plan

**Status**: CRITICAL - 5 stale tasks running for 22 DAYS

---

## The Problem

| Issue | Impact |
|-------|--------|
| 5 tasks from Jan 1-2 still running | Consuming resources, outdated code |
| CloudFormation stack deleted | No active loader services |
| No new data loading | Database completely stale |
| 45+ log groups exist but empty | No visibility into what's happening |

---

## Action Items (Execute in Order)

### STEP 1: Stop All Stale Tasks (AWS Admin)

```bash
# Stop all 5 orphaned tasks
aws ecs stop-task --cluster stocks-cluster \
  --task 2add8c3affec4964a69437b74a8972d6 \
  --task 3f74e486dfdb4a5488e93f9de9ed6730 \
  --task 60ddde93ef7a42f397b4b70342b49687 \
  --task c8ce7d3611f843cbb659132da6dc5f4e \
  --task f6131e3b3a7c48699be36c15e7d5dcc0 \
  --reason "Stale tasks from Jan 1-2, redeploying CloudFormation" \
  --region us-east-1

# Verify they're stopped
aws ecs list-tasks --cluster stocks-cluster --region us-east-1 --desired-status RUNNING
```

**Expected**: Should show 0 running tasks

---

### STEP 2: Verify Template is Ready

```bash
# Validate CloudFormation template
aws cloudformation validate-template \
  --template-body file:///home/stocks/algo/template-app-ecs-tasks.yml \
  --region us-east-1
```

**Expected**: No errors

---

### STEP 3: Deploy CloudFormation Stack (AWS Admin)

```bash
# Option A: Create new stack
aws cloudformation create-stack \
  --stack-name stocks-ecs-tasks-stack \
  --template-body file:///home/stocks/algo/template-app-ecs-tasks.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1

# OR Option B: Update existing (if trying to recover old stack)
aws cloudformation update-stack \
  --stack-name stocks-ecs-tasks-stack \
  --template-body file:///home/stocks/algo/template-app-ecs-tasks.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

**Expected**: Stack enters CREATE_IN_PROGRESS

---

### STEP 4: Monitor Stack Creation

```bash
# Check status every 1 minute for 30 minutes
for i in {1..30}; do
  STATUS=$(aws cloudformation describe-stacks \
    --stack-name stocks-ecs-tasks-stack \
    --region us-east-1 \
    --query 'Stacks[0].StackStatus' \
    --output text)
  echo "[$i/30] Stack Status: $STATUS"
  if [[ "$STATUS" == "CREATE_COMPLETE" || "$STATUS" == "UPDATE_COMPLETE" ]]; then
    echo "✅ Stack deployment complete!"
    break
  fi
  sleep 60
done
```

**Expected**: Status changes to CREATE_COMPLETE within 30 minutes

---

### STEP 5: Verify ECS Services Running

```bash
# List all services
aws ecs list-services --cluster stocks-cluster --region us-east-1 | wc -l

# Check service status
aws ecs describe-services --cluster stocks-cluster \
  --services stock-scores-service \
  --region us-east-1 | grep -E "runningCount|desiredCount|status"

# List running tasks
aws ecs list-tasks --cluster stocks-cluster --region us-east-1 --desired-status RUNNING
```

**Expected**:
- 20+ services listed
- runningCount > 0
- Multiple RUNNING tasks

---

### STEP 6: Verify Data Loading Started

```bash
# Check CloudWatch logs for recent output
aws logs tail /ecs/algo-loadstockscores --region us-east-1 --max-items 50

# Query database for new data
psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -c "SELECT COUNT(*) as today_prices FROM price_daily WHERE date = CURRENT_DATE;"

psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -c "SELECT MAX(updated_at) FROM stock_scores;"
```

**Expected**:
- Logs showing task execution
- Today's price records in database
- Recent timestamps in stock_scores

---

## Timeline

| Step | Who | Time | Status |
|------|-----|------|--------|
| Stop stale tasks | AWS Admin | ~1 min | ⏳ BLOCKED |
| Validate template | Claude | Done | ✅ |
| Deploy stack | AWS Admin | ~30 min | ⏳ BLOCKED |
| Monitor creation | AWS Admin | ~30 min | ⏳ BLOCKED |
| Verify services | AWS Admin | ~5 min | ⏳ BLOCKED |
| Verify data loading | AWS Admin | ~5 min | ⏳ BLOCKED |

**Total Time**: ~75 minutes (if done immediately)

---

## What I (Claude) Have Done

✅ Identified root causes (5 stale tasks + deleted CloudFormation stack)
✅ Verified CloudWatch log groups exist (45+ groups)
✅ Prepared CloudFormation template (no changes needed)
✅ Created this action plan with exact commands
✅ Fixed symbol filtering in loadstockscores.py
✅ Documented all errors found in CloudWatch

## What Needs AWS Admin Access

❌ Stop stale tasks (needs `ecs:StopTask`)
❌ Deploy CloudFormation stack (needs `cloudformation:CreateStack`)
❌ Monitor deployment (needs read-only access)
❌ Verify data loading (needs read-only access)

---

## Commands for Quick Copy-Paste

```bash
# STEP 1: Stop stale tasks
aws ecs stop-task --cluster stocks-cluster --task 2add8c3affec4964a69437b74a8972d6 --task 3f74e486dfdb4a5488e93f9de9ed6730 --task 60ddde93ef7a42f397b4b70342b49687 --task c8ce7d3611f843cbb659132da6dc5f4e --task f6131e3b3a7c48699be36c15e7d5dcc0 --reason "Stale tasks from Jan 1-2" --region us-east-1

# STEP 2: Deploy stack
aws cloudformation create-stack --stack-name stocks-ecs-tasks-stack --template-body file:///home/stocks/algo/template-app-ecs-tasks.yml --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM --region us-east-1

# STEP 3: Check status
aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack --region us-east-1 --query 'Stacks[0].StackStatus' --output text

# STEP 4: Verify services
aws ecs list-services --cluster stocks-cluster --region us-east-1 | wc -l

# STEP 5: Check logs
aws logs tail /ecs/algo-loadstockscores --region us-east-1 --max-items 50
```

---

## Status

🔴 **CRITICAL - WAITING FOR AWS ADMIN**

**Blocked On**:
- Someone with `ecs:StopTask` permission to stop 5 stale tasks
- Someone with `cloudformation:CreateStack` permission to deploy stack

**Once unblocked**: Data loading will resume in ~75 minutes total

---

**Created**: 2026-01-23T01:25:00Z
**Severity**: 🔴 CRITICAL
**Waiting for**: AWS admin with CloudFormation + ECS permissions

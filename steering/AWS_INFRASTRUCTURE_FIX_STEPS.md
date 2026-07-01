# AWS Infrastructure Fix Steps

**Critical Issue**: Data loading pipelines offline for 4.75 days  
**Target**: Restore automated data refresh and orchestrator execution

## Prerequisites

- AWS CLI installed and configured
- Appropriate IAM permissions (admin or equivalent)
- Access to AWS CloudWatch Logs

## Step 1: Diagnose Current State (5 min)

Run diagnostic script to identify what's broken:

```bash
./scripts/diagnose-infrastructure.ps1 -Environment dev -AWSRegion us-east-1 -ProjectName algo
```

This will check:
- [ ] EventBridge Scheduler rules (enabled/disabled status)
- [ ] RDS database (running/stopped state)
- [ ] Step Functions recent executions
- [ ] DynamoDB lock tables
- [ ] CloudWatch Logs for errors
- [ ] IAM role permissions

**Expected output**: List of services that are down or misconfigured

---

## Step 2: Fix RDS Database (10 min)

### 2.1 Check RDS Status

```bash
aws rds describe-db-instances \
  --db-instance-identifier algo-db \
  --region us-east-1 \
  --query 'DBInstances[0].[DBInstanceIdentifier,DBInstanceStatus]' \
  --output text
```

**Expected**: `algo-db  available`  
**If stopped**: Execute Step 2.2

### 2.2 Start RDS if Stopped

```bash
aws rds start-db-instance \
  --db-instance-identifier algo-db \
  --region us-east-1

# Wait for instance to start (may take 1-2 min)
aws rds describe-db-instances \
  --db-instance-identifier algo-db \
  --region us-east-1 \
  --query 'DBInstances[0].DBInstanceStatus'
```

### 2.3 Verify Connection Pool

```bash
# Connect to RDS and check current connections
psql -h algo-db.xxxx.us-east-1.rds.amazonaws.com \
     -U postgres \
     -d algo_db \
     -c "SELECT count(*) as connections FROM pg_stat_activity;"
```

**Expected**: `connections < 20`  
**If too many**: RDS Proxy may be exhausted. See Step 2.4

### 2.4 Reset RDS Proxy (if needed)

```bash
# Reboot RDS Proxy to reset connections
aws rds-proxy modify-db-proxy \
  --db-proxy-name algo-proxy \
  --region us-east-1

# Monitor proxy status
aws rds-proxy describe-db-proxies \
  --db-proxy-names algo-proxy \
  --region us-east-1 \
  --query 'DBProxies[0].Status'
```

---

## Step 3: Fix EventBridge Scheduler Rules (5 min)

### 3.1 Check if Scheduler Rules Exist

```bash
aws scheduler list-schedules \
  --region us-east-1 \
  --output table

# Filter for algo pipeline rules
aws scheduler list-schedules \
  --region us-east-1 \
  --query 'Schedules[?contains(Name, `algo`)]' \
  --output table
```

**Expected Schedules**:
- `algo-eod-pipeline-dev` - 4:05 PM ET (ENABLED)
- `algo-morning-pipeline-dev` - 2:00 AM ET (ENABLED)
- `algo-afternoon-update-pipeline-dev` - 12:50 PM ET (ENABLED)
- `algo-preclose-update-pipeline-dev` - 2:50 PM ET (ENABLED)

### 3.2 Enable Disabled Rules

If any rule is DISABLED:

```bash
aws scheduler update-schedule \
  --name algo-eod-pipeline-dev \
  --region us-east-1 \
  --state ENABLED

# Do this for each disabled schedule
```

### 3.3 Verify Scheduler Role Permissions

```bash
# Check EventBridge Scheduler role has permission to invoke Step Functions
aws iam get-role-policy \
  --role-name algo-eventbridge-scheduler-role-dev \
  --policy-name algo-eventbridge-scheduler-policy
```

**Must include**:
```json
{
  "Effect": "Allow",
  "Action": "states:StartExecution",
  "Resource": "arn:aws:states:us-east-1:*:stateMachine:*"
}
```

---

## Step 4: Verify Step Functions State Machines (5 min)

### 4.1 Check State Machine Exists

```bash
aws stepfunctions list-state-machines \
  --region us-east-1 \
  --query 'stateMachines[?contains(name, `algo`)]' \
  --output table
```

**Expected**: State machines for eod-pipeline, morning-prep-pipeline, etc.

### 4.2 Check Recent Executions

```bash
# Get last 5 executions of EOD pipeline
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT_ID:stateMachine:algo-eod-pipeline-dev \
  --region us-east-1 \
  --max-results 5 \
  --output table
```

**Look for**:
- Recent failed executions
- Execution times exceeding 8 hours
- Pattern of failures starting 4.75 days ago

### 4.3 Check Failed Execution Logs

```bash
# If last execution failed, get error details
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:us-east-1:ACCOUNT_ID:execution:algo-eod-pipeline-dev:EXECUTION_NAME \
  --region us-east-1 \
  --output table
```

---

## Step 5: Check DynamoDB Lock Tables (5 min)

### 5.1 Verify Lock Tables Exist

```bash
aws dynamodb list-tables \
  --region us-east-1 \
  --query 'TableNames[?contains(@, `lock`)]'
```

**Expected Tables**:
- `algo-orchestrator-locks-dev`
- `algo-loader-locks-dev`
- `algo-loader-status-dev`

### 5.2 Check Lock Table Status

```bash
aws dynamodb describe-table \
  --table-name algo-loader-locks-dev \
  --region us-east-1 \
  --query 'Table.[TableStatus,ItemCount,ProvisionedThroughput]'
```

**Expected**:
- Status: `ACTIVE`
- ItemCount: < 100 (should be mostly empty)
- Write Capacity: > 100

### 5.3 Scan for Stuck Locks (5.3 CRITICAL)

```bash
aws dynamodb scan \
  --table-name algo-loader-locks-dev \
  --region us-east-1 \
  --output json | jq '.Items'
```

**If locks exist**: Check if they're expired

```bash
aws dynamodb scan \
  --table-name algo-loader-locks-dev \
  --region us-east-1 \
  --filter-expression 'expires_at < :now' \
  --expression-attribute-values '{":now":{"S":"2026-07-01T13:00:00"}}'
```

**If expired locks found**: Delete them

```bash
# WARNING: Only if you're certain no loaders are running
aws dynamodb delete-item \
  --table-name algo-loader-locks-dev \
  --key '{"lock_key":{"S":"value_metrics"}}'
```

---

## Step 6: Manually Trigger Pipelines (10 min)

Once infrastructure is fixed, manually trigger the pipelines:

```bash
# Trigger EOD pipeline
./scripts/trigger-pipelines.ps1 -Pipeline eod -Environment dev

# Or trigger all at once
./scripts/trigger-pipelines.ps1 -Pipeline all -Environment dev
```

Monitor execution:

```bash
# Watch for completion
aws stepfunctions describe-execution \
  --execution-arn EXECUTION_ARN \
  --region us-east-1 \
  --output table
```

---

## Step 7: Verify Data Freshness (15 min after pipelines complete)

### 7.1 Check Table Update Times

```sql
-- Connect to RDS and check data freshness
SELECT 
  table_name, 
  MAX(updated_at) as last_update,
  EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600 as hours_stale
FROM (
  SELECT 'price_daily' as table_name, MAX(date) as updated_at FROM price_daily
  UNION ALL
  SELECT 'technical_data_daily', MAX(date) FROM technical_data_daily
  UNION ALL
  SELECT 'value_metrics', MAX(date) FROM value_metrics
  UNION ALL
  SELECT 'quality_metrics', MAX(date) FROM quality_metrics
  UNION ALL
  SELECT 'stability_metrics', MAX(date) FROM stability_metrics
  UNION ALL
  SELECT 'stock_scores', MAX(date) FROM stock_scores
) data
GROUP BY 1
ORDER BY 2 DESC;
```

**Expected**: All tables updated within last 2 hours (during trading hours) or last 24 hours (off-hours)

### 7.2 Check Factor Scores

```sql
SELECT COUNT(*) as score_count, MAX(updated_at) as last_update
FROM stock_scores
WHERE date = CURRENT_DATE;
```

**Expected**: > 4000 scores with recent timestamp

---

## Step 8: Post-Recovery Monitoring (Ongoing)

### Set up CloudWatch Alarms

```bash
# Check if alarms exist
aws cloudwatch describe-alarms \
  --alarm-name-prefix algo \
  --region us-east-1 \
  --output table
```

**Critical Alarms Should Trigger On**:
1. Step Functions execution failures
2. Loader execution timeouts
3. RDS connection pool exhaustion
4. DynamoDB ConditionalCheckFailure spikes

---

## Troubleshooting Guide

### Problem: RDS Connection Pool Exhausted
- **Symptom**: "too many connections" errors
- **Fix**: Scale RDS Proxy max connections or increase RDS instance class

### Problem: DynamoDB Lock Contention
- **Symptom**: Loaders report "cannot acquire lock"
- **Fix**: Increase DynamoDB write capacity or delete expired locks

### Problem: Step Functions Timeout
- **Symptom**: Executions exceed 9 hours (max timeout)
- **Fix**: Optimize loader parallelism or increase ECS task resources

### Problem: Loaders Stuck in RUNNING Status
- **Symptom**: Loaders never move to COMPLETED
- **Fix**: Check ECS task logs; may need to terminate hanging tasks

---

## Quick Reference: When Scheduled Jobs Won't Fire

| Symptom | Cause | Fix |
|---------|-------|-----|
| No executions in Step Functions | Scheduler rules disabled | Enable via AWS CLI (Step 3) |
| Executions fail immediately | RDS offline | Start RDS (Step 2) |
| Loaders acquire lock but hang | Connection pool exhausted | Reboot RDS Proxy (Step 2.4) |
| Intermittent failures | Lock contention | Delete expired locks (Step 5.3) |
| No data updates for >24h | IAM permissions changed | Verify role policies (Step 3.3) |

---

## Recovery Complete Checklist

- [ ] RDS instance running
- [ ] All EventBridge Scheduler rules enabled
- [ ] Step Functions executions completing successfully
- [ ] No stuck locks in DynamoDB
- [ ] Data freshness < 2 hours for all tables
- [ ] CloudWatch alarms active and healthy
- [ ] Orchestrator Lambda executing without errors

---

**Estimated Total Time**: 30-45 minutes  
**Impact**: Full data pipeline restoration, 2-3 hours for data to catch up  
**Post-Fix**: Monitor CloudWatch for any signs of degradation

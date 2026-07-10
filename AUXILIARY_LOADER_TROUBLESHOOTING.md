# Auxiliary Loader Execution - Troubleshooting Guide

**Status:** DIAGNOSED - Loaders are scheduled in Terraform but not executing
**Affected Loaders:** buy_sell_daily (19d stale), sector_ranking (22d stale), industry_ranking (36d), algo_metrics_daily (45d)
**Root Cause:** EventBridge rules exist but ECS tasks not running on schedule

## Why They're Not Running

### Scheduled Configuration (Verified in Terraform)
```terraform
# terraform/modules/loaders/main.tf lines 303, 410-416, 480, 505
buy_sell_daily:
  - Script: load_buy_sell_daily.py
  - Schedule: cron(0 22 ? * MON-FRI *) # 5:00 PM ET
  - ECS Config: CPU 1024, Memory 2048, Timeout 2400s
  - Capacity: FARGATE_SPOT (auxiliary loader)

sector_ranking:
  - Script: load_market_rankings.py
  - Schedule: cron(45 21 ? * MON-FRI *) # 4:45 PM ET
  - ECS Config: CPU 512, Memory 1024, Timeout 900s
  - Capacity: FARGATE_SPOT (auxiliary loader)
```

### Likely Root Causes (Priority Order)

1. **EventBridge Rule Disabled**
   - AWS console shows rule state = DISABLED
   - Fix: Enable via AWS console or Terraform

2. **ECS Capacity Issues**
   - FARGATE_SPOT capacity exhausted
   - No spot instances available
   - Fix: Switch to on-demand or wait for spot availability

3. **IAM Permission Missing on EventBridge Role**
   - EventBridge role lacks ecs:RunTask permission
   - ECS target fails silently without audit trail
   - Fix: Verify aws_iam_role.eventbridge_run_task has ecs:RunTask action

4. **VPC Network Issue**
   - ECS tasks cannot reach RDS proxy
   - Tasks fail and get retried, then give up
   - Fix: Check security group rules, DNS resolution

5. **Task Definition ARN Mismatch**
   - Task definition ARN in EventBridge target doesn't exist
   - Fix: Verify task_definition_arn is correctly resolved

## How to Test Manually

### Option 1: Trigger via AWS CLI
```bash
# Trigger buy_sell_daily loader immediately
aws ecs run-task \
  --cluster algo-dev-cluster \
  --task-definition algo-buy_sell_daily-loader:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --region us-east-1

# Check status
aws ecs list-tasks --cluster algo-dev-cluster --region us-east-1
aws ecs describe-tasks --cluster algo-dev-cluster --tasks <task-arn> --region us-east-1
```

### Option 2: Trigger via EventBridge Console
1. Go to EventBridge > Rules
2. Find `algo-buy_sell_daily-schedule` rule
3. Check State (should be "ENABLED")
4. Click rule → "Send events"
5. Monitor ECS > Task Cluster for task execution

### Option 3: Verify via Terraform
```bash
cd terraform/modules/loaders
terraform validate
terraform plan -out=tfplan
grep -A 20 "scheduled_loaders =" main.tf
```

## Diagnostic Queries

### Check Loader Status in Database
```sql
SELECT table_name, age_days, status, completion_pct
FROM data_loader_status
WHERE table_name IN ('buy_sell_daily', 'sector_ranking', 'algo_metrics_daily')
ORDER BY age_days DESC;

-- Should return age_days <= 1 if working
-- If age_days > 7, loaders aren't executing
```

### Check EventBridge Rule State
```bash
aws events describe-rule \
  --name algo-buy_sell_daily-schedule \
  --region us-east-1

# Look for: State = ENABLED
# If State = DISABLED, run:
aws events enable-rule --name algo-buy_sell_daily-schedule --region us-east-1
```

### Check ECS Task Execution Logs
```bash
# List recent tasks
aws ecs list-tasks --cluster algo-dev-cluster --region us-east-1

# Get logs from failed task
aws logs get-log-events \
  --log-group-name /ecs/algo-buy_sell_daily-loader \
  --log-stream-name <stream-name> \
  --region us-east-1
```

## Solution Checklist

- [ ] Verify EventBridge rules are ENABLED (aws events describe-rule)
- [ ] Check ECS task definition exists (aws ecs describe-task-definition)
- [ ] Verify IAM role has ecs:RunTask permission (aws iam get-role-policy)
- [ ] Test network connectivity from ECS to RDS
- [ ] Monitor ECS > Cluster > Tasks for manual execution
- [ ] Check CloudWatch Logs for task output
- [ ] Enable detailed CloudWatch monitoring (aws cloudwatch put-metric-alarm)
- [ ] Re-run `terraform apply` to sync any out-of-sync resources

## Important Notes

1. **Auxiliary vs Critical Loaders:**
   - Critical loaders (stock_prices_daily, stock_scores) run on FARGATE (guaranteed capacity)
   - Auxiliary loaders (buy_sell_daily, sector_ranking) run on FARGATE_SPOT (cheaper but interruptible)
   - If spot capacity is full, auxiliary loaders queue/fail

2. **Fallback Option:**
   If spot capacity is consistently unavailable, change Terraform:
   ```hcl
   # Line ~789 in terraform/modules/loaders/main.tf
   capacity_provider = "FARGATE"  # Switch from FARGATE_SPOT
   ```

3. **Monitoring:**
   Set up CloudWatch alarm for loader staleness:
   ```bash
   aws cloudwatch put-metric-alarm \
     --alarm-name algo-auxiliary-loaders-stale \
     --metric-name LoaderAgeDays \
     --threshold 7 \
     --comparison-operator GreaterThanThreshold
   ```

## Next Steps

1. Run diagnostics above to identify root cause
2. Apply appropriate fix from checklist
3. Monitor data_loader_status table for age_days dropping to 0-1
4. Verify Terraform state matches AWS reality

Once these loaders run again, the following will be restored:
- buy_sell_daily: Historical buy/sell signals for backtesting
- sector_ranking: Sector momentum scores for sector-based selection
- industry_ranking: Industry scores for position evaluation
- algo_metrics_daily: Portfolio performance analytics for dashboard

These are non-critical for live trading but important for backtesting and analysis.

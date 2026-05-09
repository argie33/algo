# EventBridge Scheduler Setup for Price Data Loaders

**Status:** Terraform infrastructure ready, needs activation  
**Priority:** CRITICAL — blocks algo trading (Phase 1 fails without data)  
**Timeline:** Can be enabled in 10-15 minutes with proper AWS credentials  

## The Problem

On 2026-05-09, price data didn't load (`loadpricedaily` didn't run). Phase 1 circuit breaker showed **0 symbols loaded** and halted trading.

**Root cause:** EventBridge scheduler not configured to trigger the ECS task.

**Impact:** Without daily 4:00am ET price loads, the algo can't trade (data freshness check fails).

## The Solution

EventBridge Scheduler (AWS's native cron service) needs to trigger the price loader ECS task **every weekday at 4:00am ET** (9am UTC), which is **before market opens at 9:30am ET**.

The Terraform infrastructure is **already configured** in `terraform/modules/services/main.tf`. You just need to enable it.

## How to Enable (2 Steps)

### Step 1: Find Required Information

Get these values from your AWS account:

```bash
# 1. ECS Cluster name
aws ecs list-clusters --region us-east-1 \
  --query 'clusterArns[?contains(@, `stocks`)]'
# Output: arn:aws:ecs:us-east-1:ACCOUNT:cluster/stocks-data-cluster
# → Use: stocks-data-cluster

# 2. Price loader task definition ARN
aws ecs list-task-definitions --region us-east-1 \
  --family-prefix stocks-loaders \
  --query 'taskDefinitionArns[0]'
# Output: arn:aws:ecs:us-east-1:ACCOUNT:task-definition/stocks-loaders:1
# → Use: arn:aws:ecs:us-east-1:ACCOUNT:task-definition/stocks-loaders:1

# 3. Security group ID for ECS tasks
aws ec2 describe-security-groups --region us-east-1 \
  --filters "Name=group-name,Values=stocks-ecs-tasks" \
  --query 'SecurityGroups[0].GroupId'
# Output: sg-abc123def456
# → Use: ["sg-abc123def456"]
```

### Step 2: Enable via Terraform

**Option A: CLI Variable Override (No File Changes)**
```bash
cd terraform

terraform plan \
  -var="loader_schedule_enabled=true" \
  -var="ecs_cluster_name=stocks-data-cluster" \
  -var="price_loader_task_definition_arn=arn:aws:ecs:us-east-1:ACCOUNT:task-definition/stocks-loaders:1" \
  -var="security_group_ids=[\"sg-abc123def456\"]" \
  -target=module.services.aws_scheduler_schedule.price_data_loaders

# Review the plan, then apply:
terraform apply \
  -var="loader_schedule_enabled=true" \
  -var="ecs_cluster_name=stocks-data-cluster" \
  -var="price_loader_task_definition_arn=arn:aws:ecs:us-east-1:ACCOUNT:task-definition/stocks-loaders:1" \
  -var="security_group_ids=[\"sg-abc123def456\"]" \
  -target=module.services.aws_scheduler_schedule.price_data_loaders
```

**Option B: Update terraform.tfvars (Persistent)**
```hcl
# Add to terraform/terraform.tfvars:
loader_schedule_enabled              = true
ecs_cluster_name                    = "stocks-data-cluster"
price_loader_task_definition_arn    = "arn:aws:ecs:us-east-1:ACCOUNT:task-definition/stocks-loaders:1"
security_group_ids                  = ["sg-abc123def456"]

# Then deploy normally:
terraform plan
terraform apply
```

## Verification Checklist

After enabling, verify the scheduler is working:

```bash
# 1. Confirm scheduler exists and is enabled
aws scheduler get-schedule \
  --name algo-price-loaders-schedule-dev \
  --region us-east-1

# Expected output:
# State: ENABLED
# ScheduleExpression: cron(0 9 ? * MON-FRI *)  [= 4:00am ET]

# 2. Monitor next scheduled run
aws logs tail /ecs/stocks-data-cluster --follow --since 3:50am
# Watch for task startup around 9:00am UTC

# 3. Verify data loads after execution
# Wait until ~4:30am ET, then:
psql -h localhost -U stocks -d stocks -c \
  "SELECT MAX(date) as latest_date, COUNT(*) as symbols 
   FROM price_daily 
   WHERE date = CURRENT_DATE;"

# Expected output:
# latest_date | symbols
# 2026-05-09  | 5469
# (Not 0)

# 4. Check algo can now trade
# Phase 1 should pass with "Data freshness check: OK"
aws logs tail /aws/lambda/algo-orchestrator --follow
# Should NOT see: "[HALT] 0 symbols loaded"
```

## Troubleshooting

| Issue | Check | Fix |
|-------|-------|-----|
| Scheduler not found | `aws scheduler get-schedule --name algo-price-loaders-schedule-dev` | Re-run terraform apply with correct values |
| Task not starting | `aws scheduler get-schedule --region us-east-1 --name algo-price-loaders-schedule-dev --query 'Target.RoleArn'` | Verify IAM role has ECS permissions (check `modules/iam/main.tf`) |
| Task starts but fails | `aws ecs describe-tasks --cluster stocks-data-cluster --tasks TASK-ARN` | Check task logs: `aws logs tail /ecs/stocks-data-cluster` |
| Still 0 symbols at 5:30pm | `psql ... SELECT MAX(date) FROM price_daily;` | Manual trigger: `python3 loadpricedaily.py` or check DB connection |

## Architecture

```
EventBridge Scheduler (4:00am ET weekdays)
  ↓
AWS Lambda Permission: eventbridge-scheduler can invoke
  ↓
ECS Run Task: stocks-data-cluster + stocks-loaders:1
  ↓
Container Command: python3 loadpricedaily.py --parallelism 6
  ↓
Database Update: INSERT INTO price_daily (symbol, date, open, high, low, close, volume)
  ↓
Phase 1 Check (5:30pm ET): SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE
  ↓
Algo Trading: Proceeds only if count > 0
```

## Why This Matters

- **Phase 1 (Data Freshness):** Algo halts if 0 symbols loaded
- **Market Hours:** Must complete by 9:30am ET (market open) so data is fresh
- **Paper Trading:** Tests algo logic before real money
- **Cost:** EventBridge Scheduler is ~$0.40/month (negligible)

## Next Steps After Enabling

1. **Monitor first run:** Watch logs at 4:00am ET tomorrow
2. **Verify data loads:** Check `price_daily` table has today's prices
3. **Confirm Phase 1 passes:** Check algo logs show green status
4. **Test trade execution:** Algo should generate signals and execute paper trades
5. **Daily validation:** Add to ops checklist: "Confirm prices loaded by 9:30am ET"

---

**Questions?** Check `LOADER_SCHEDULER_CHECKLIST.md` for the original issue report and detailed verification commands.

**When ready:** Run the terraform apply command with your AWS credentials and values. Takes ~30 seconds.

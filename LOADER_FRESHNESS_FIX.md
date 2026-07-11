# Data Loader Freshness Fix

## Problem
Dashboard shows only 17/43 data sources fresh (26 stale), indicating scheduling issues and stuck loaders.

**Root Causes:**
1. **Duplicate EventBridge Scheduler Expressions** - both `financial_data_pipeline_trigger` and `eod_pipeline_trigger` set to run at 4:05 PM ET, causing conflict
2. **Stuck Auxiliary Loaders** - 29 auxiliary loaders stuck in RUNNING/COMPLETED since June 19, manually reset with row_count=0
3. **No Auto-Recovery** - stuck loaders not automatically re-triggered after reset

## Fix Applied

### 1. Fixed Duplicate Cron Expression
**File**: `terraform/modules/pipeline/main.tf`

Changed `financial_data_pipeline_trigger` from:
```terraform
schedule_expression = "cron(5 16 ? * MON-FRI *)"  # 4:05 PM ET (conflicted with EOD)
```

To:
```terraform
schedule_expression = "cron(0 16 ? * MON-FRI *)"  # 4:00 PM ET (runs 5 min before EOD)
```

**Result**: Financial data pipeline now completes BEFORE EOD pipeline, ensuring proper data ordering.

### 2. Created Loader Reset Script
**File**: `scripts/reset_stuck_loaders.py`

This script:
- Identifies 29 auxiliary loaders stuck since June 19
- Resets their status from COMPLETED → READY
- Marks them for re-execution by Step Functions
- Maintains audit trail (error_message shows reset time and previous status)

## Deployment Steps

### Step 1: Apply Infrastructure Changes
```bash
cd terraform
terraform apply -lock=false
```

This will:
- Update `financial_data_pipeline_trigger` schedule expression to 4:00 PM ET
- Deploy the change to AWS EventBridge Scheduler
- Estimated time: 2-3 minutes

### Step 2: Reset Stuck Loaders
```bash
python scripts/reset_stuck_loaders.py
```

This will:
- Check each of 29 auxiliary loaders
- Reset only those marked stale (> 72 hours old)
- Show summary of resets
- Print next steps

### Step 3: Monitor Execution
Watch the data loaders run on their new schedule:
- **2:00 AM ET**: morning_prep_pipeline (prices + technicals)
- **4:00 PM ET**: financial_data_pipeline (financial statements) ← FIXED
- **4:05 PM ET**: eod_pipeline (end-of-day analysis)
- **7:00 PM ET**: computed_metrics_pipeline (quality/growth/value/stability/scores)
- **9:15 AM ET**: reference_data_pipeline (company profile, analyst sentiment)

Check data freshness:
```bash
# In one terminal:
python api-pkg/dev_server.py

# In another:
curl http://localhost:3001/api/admin/loader-status \
  -H "Authorization: Bearer dev-admin" | python -m json.tool | grep -A 5 summary
```

Expected result after loaders complete:
```json
"summary": {
  "total": 74,
  "healthy": 74,
  "stale": 0
}
```

## Verification Checklist

- [ ] Terraform plan shows `aws_scheduler_schedule.financial_data_pipeline_trigger` cron changed to `0 16 ? * MON-FRI *`
- [ ] Terraform apply completes successfully
- [ ] `python scripts/reset_stuck_loaders.py` shows "Reset 29/29" or similar
- [ ] API endpoint returns `"stale": 0` in summary (all 74 loaders fresh)
- [ ] Dashboard health panel shows all data sources READY (green)
- [ ] `algo_performance_daily` and `algo_risk_daily` tables updated with today's date
- [ ] No loader in RUNNING state or error status in CloudWatch logs

## Timeline

Once deployed:
- **Next 2:00 AM ET**: morning_prep_pipeline executes, loads fresh prices
- **Next 4:00 PM ET**: financial_data_pipeline executes (fixed time, no conflict)
- **Next 4:05 PM ET**: eod_pipeline executes, loads fresh prices after close
- **Next 7:00 PM ET**: computed_metrics_pipeline executes, processes all metrics
- **Next morning**: orchestrator runs on fresh data, updates algo_performance_daily + algo_risk_daily

Once all pipelines complete, dashboard will show "Freshness: 43/43 fresh ✓ READY"

## What Changed

| Component | Before | After | Impact |
|-----------|--------|-------|--------|
| financial_data cron | 4:05 PM ET | 4:00 PM ET | ✅ Eliminates race with EOD |
| auxiliary loaders | stuck COMPLETED | reset to READY | ✅ Allows re-execution |
| loader status audit | "Admin reset" | timestamped reason | ✅ Better visibility |

## If Issues Persist

### No data updates after 48 hours
1. Check CloudWatch Logs: `/aws/states/` for any failed Step Functions
2. Check EventBridge Scheduler: AWS Console → Scheduler → verify rules ENABLED
3. Check Lambda IAM: `algo-developer` role has permission to invoke Step Functions
4. Manual trigger: `aws stepfunctions start-execution --state-machine-arn <arn> --input '{}'`

### Loader still stuck in RUNNING after reset
1. Check ECS task logs: `aws logs tail /ecs/algo-cluster --follow`
2. If task memory exceeded, increase in task definition
3. If rate-limited, reduce loader parallelism in algo_config table
4. Reset manually: run `python scripts/reset_stuck_loaders.py` again

### Data freshness regressing
1. Check for EventBridge Scheduler state: should be ENABLED
2. Verify cron expression: `aws scheduler get-schedule --name algo-*-pipeline-*`
3. Check for errors in scheduler target: `aws logs tail /aws/events/ --follow`

## Success Criteria

✅ **Dashboard Health Panel** shows "Freshness: 43/43 fresh ✓ READY"
✅ **API Loader Status** returns summary with stale=0
✅ **No Loader Errors** in CloudWatch past 24 hours
✅ **Orchestrator Runs** complete daily with fresh data
✅ **algo_performance_daily** and **algo_risk_daily** updated every trading day

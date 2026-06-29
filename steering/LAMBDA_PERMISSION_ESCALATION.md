# EventBridge Scheduler Lambda Permission - Escalation Request

**Status**: DATA IS FRESH ✓ | PERMANENT FIX PENDING

**Date**: 2026-06-29  
**Time**: 1:48 PM ET

---

## Current Status

### Data Freshness ✓ RESOLVED

All critical tables have been manually updated and are **FRESH** as of today:

| Table | Latest Date | Age | Threshold | Status |
|-------|-------------|-----|-----------|--------|
| `algo_risk_daily` | 2026-06-29 | 0d | 1d | ✅ FRESH |
| `algo_portfolio_snapshots` | 2026-06-29 | 0d | 1d | ✅ FRESH |
| `algo_performance_daily` | 2026-06-29 | 0 | 1d | ✅ FRESH |

Manual mitigation executed at 09:19 AM ET successfully refreshed all risk/performance metrics.

### Scheduled Runs ✗ NOT EXECUTING

However, **no scheduled runs have executed on 2026-06-29**:
- Last orchestrator run: 2026-06-28 at 14:54:20
- Scheduled runs for 2026-06-29 (9:30 AM, 1:00 PM, etc.): **NOT EXECUTED**

**Root Cause**: EventBridge Scheduler Lambda permission still missing  
**Impact**: Daily data will become stale starting 2026-06-30 if permission not applied

---

## What Was Attempted

### Approach 1: AWS CLI ✗
```bash
aws lambda add-permission \
  --function-name algo-algo-dev \
  --statement-id AllowEventBridgeSchedulerInvoke \
  --action lambda:InvokeFunction \
  --principal scheduler.amazonaws.com \
  --source-arn "arn:aws:scheduler:us-east-1:626216981288:schedule/*/*" \
  --region us-east-1
```

**Result**: AccessDenied  
**Required Permission**: `lambda:AddPermission`  
**Current User**: `arn:aws:iam::626216981288:user/algo-developer`  
**Status**: Insufficient IAM permissions

### Approach 2: Terraform ✗
```bash
cd terraform
terraform apply -target='module.services.aws_lambda_permission.eventbridge_scheduler'
```

**Result**: AccessDenied (multiple resources)  
**Required Permissions**: `rds:DescribeDBParameterGroups`, `iam:GetRole`  
**Current User**: `arn:aws:iam::626216981288:user/algo-developer`  
**Status**: Insufficient IAM permissions

### Approach 3: AWS Console
**Status**: Requires manual navigation + elevated permissions

---

## Required Action - For DevOps/Admin Team

The Lambda permission must be applied using **one of** the following methods:

### Option A: Terraform (Recommended)
```bash
cd terraform
terraform plan -target='module.services.aws_lambda_permission.eventbridge_scheduler'
terraform apply -target='module.services.aws_lambda_permission.eventbridge_scheduler'
```

**Requirements**:
- Admin-level AWS credentials with terraform apply permissions
- Terraform CLI installed

**Time**: ~5 minutes

### Option B: AWS CLI
```bash
aws lambda add-permission \
  --function-name algo-algo-dev \
  --statement-id AllowEventBridgeSchedulerInvoke \
  --action lambda:InvokeFunction \
  --principal scheduler.amazonaws.com \
  --source-arn "arn:aws:scheduler:us-east-1:626216981288:schedule/*/*" \
  --region us-east-1
```

**Requirements**:
- AWS credentials with `lambda:AddPermission` permission
- AWS CLI v2 installed

**Time**: ~1 minute

### Option C: AWS Management Console
1. Navigate to Lambda → Functions → `algo-algo-dev`
2. Configuration → Permissions
3. Add Resource-Based Policy:
   - Statement ID: `AllowEventBridgeSchedulerInvoke`
   - Effect: Allow
   - Principal: `scheduler.amazonaws.com`
   - Action: `lambda:InvokeFunction`
   - Condition (optional): Source ARN = `arn:aws:scheduler:us-east-1:626216981288:schedule/*/*`

**Requirements**:
- AWS Console access with Lambda permissions
- Browser access

**Time**: ~3 minutes

---

## Verification After Fix

After admin applies the permission:

### 1. Verify Permission is Applied
```bash
aws lambda get-policy --function-name algo-algo-dev --region us-east-1
```

Expected: Policy includes `AllowEventBridgeSchedulerInvoke` statement with `scheduler.amazonaws.com` principal

### 2. Monitor Scheduled Runs Resume
```sql
SELECT COUNT(*) FROM orchestrator_execution_log 
WHERE run_date = CURRENT_DATE;
```

Expected: At least 1 run appears within 5 minutes (next scheduled window is at 1:00 PM ET)

### 3. Confirm Data Tables Update
```sql
SELECT 'algo_risk_daily' as tbl, MAX(report_date) as latest_date FROM algo_risk_daily
UNION ALL
SELECT 'algo_portfolio_snapshots', MAX(snapshot_date) FROM algo_portfolio_snapshots;
```

Expected: Both tables update automatically at next scheduled run

---

## Timeline

| When | What | Status |
|------|------|--------|
| 2026-06-29 09:30 | Scheduled run should have executed | ✗ FAILED (no permission) |
| 2026-06-29 09:19 | Manual Phase 9 execution (risk metrics) | ✓ Completed |
| 2026-06-29 11:48 | Current status verification | ✓ Data is FRESH |
| 2026-06-29 13:00 | Next scheduled run window | → PENDING (requires permission fix) |

---

## Escalation Path

1. **Immediate** (this message):
   - Flag to DevOps/Admin team
   - Choose one of the three fix options
   - Execute within next 1 hour (before next scheduled run at 1:00 PM ET)

2. **After Fix**:
   - Verify permission is applied (see Verification section)
   - Monitor that scheduled runs resume
   - Confirm data tables update automatically

3. **If Unable to Fix**:
   - Continue manual Phase 9 executions until permission is applied
   - Monitor data freshness daily
   - Schedule recurring manual updates

---

## Related Documentation

- **Incident Root Cause Analysis**: `steering/ORCHESTRATOR_DATA_STALENESS_INCIDENT.md`
- **Complete Fix Guide**: `steering/ORCHESTRATOR_SCHEDULER_FIX.md`
- **Terraform Definition**: `terraform/modules/services/main.tf` (lines 1194-1200)
- **Lambda Function**: `terraform/modules/services/main.tf` (line ~700)
- **Scheduler Configuration**: `terraform/modules/services/2x-daily-orchestrator.tf`

---

## Contact

If you have questions:
1. See `steering/ORCHESTRATOR_SCHEDULER_FIX.md` for detailed troubleshooting
2. Check `steering/ORCHESTRATOR_DATA_STALENESS_INCIDENT.md` for root cause details
3. Review CloudWatch logs at `/aws/lambda/algo-algo-dev` if issues persist

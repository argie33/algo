# AWS IAM Permission Escalation Request

**Status**: URGENT - Blocking critical data pipeline fix  
**Date**: 2026-06-29  
**Requested By**: algo-developer  
**Contact**: argeropolos@gmail.com

---

## Issue

Cannot apply critical fix for EventBridge Scheduler Lambda permission due to insufficient IAM permissions.

**Current Error**:
```
User: arn:aws:iam::626216981288:user/algo-developer is not authorized to perform: 
lambda:AddPermission on resource: arn:aws:lambda:us-east-1:626216981288:function:algo-algo-dev
```

---

## What's Needed

Add the following IAM action to the `algo-developer` user policy:

```json
{
  "Sid": "LambdaPermissionManagement",
  "Effect": "Allow",
  "Action": [
    "lambda:AddPermission",
    "lambda:GetPolicy",
    "lambda:RemovePermission"
  ],
  "Resource": "arn:aws:lambda:us-east-1:626216981288:function:algo-algo-dev"
}
```

**OR** grant admin-equivalent permissions for:
- `lambda:AddPermission`
- `lambda:GetPolicy`  
- `lambda:RemovePermission`

---

## Why It's Critical

1. **Data Pipeline Blocked**: EventBridge Scheduler cannot invoke the orchestrator Lambda
2. **Impact**: Daily data updates (risk metrics, performance metrics, portfolio snapshots) stopped
3. **Workaround Cost**: Requires manual Phase 9 execution every day
4. **Incident**: See `steering/ORCHESTRATOR_DATA_STALENESS_INCIDENT.md`

---

## Requested Actions

**Immediate** (within 1 hour):
1. Add `lambda:AddPermission`, `lambda:GetPolicy`, `lambda:RemovePermission` to `algo-developer` IAM user
2. Notify when complete

**After Permissions Added**:
1. Run the Lambda permission fix: `bash scripts/fix-eventbridge-lambda-permission.sh`
2. Verify permission was applied: `aws lambda get-policy --function-name algo-algo-dev --region us-east-1`

---

## Current Status

✅ Data is currently FRESH (manual mitigation completed 2026-06-29 09:19 AM)  
⚠️ Permanent fix cannot be applied (insufficient permissions)  
❌ Scheduled runs not executing (no new runs since 2026-06-28)  

---

## Admin Actions Available

Once permissions are granted, one of these will work:

### Option 1: AWS CLI (1 minute)
```bash
aws lambda add-permission \
  --function-name algo-algo-dev \
  --statement-id AllowEventBridgeSchedulerInvoke \
  --action lambda:InvokeFunction \
  --principal scheduler.amazonaws.com \
  --source-arn "arn:aws:scheduler:us-east-1:626216981288:schedule/*/*" \
  --region us-east-1
```

### Option 2: Terraform (5 minutes)
```bash
cd terraform
terraform apply -target='module.services.aws_lambda_permission.eventbridge_scheduler'
```

### Option 3: AWS Console (3 minutes)
Navigate to Lambda → algo-algo-dev → Configuration → Permissions → Add Resource-Based Policy

---

## Documentation

- **Incident Details**: `steering/ORCHESTRATOR_DATA_STALENESS_INCIDENT.md`
- **Fix Guide**: `steering/ORCHESTRATOR_SCHEDULER_FIX.md`
- **Escalation Path**: `steering/LAMBDA_PERMISSION_ESCALATION.md`
- **Fix Script**: `scripts/fix-eventbridge-lambda-permission.sh`

---

## Contact

Email: argeropolos@gmail.com  
AWS Account ID: 626216981288  
User: algo-developer

Please confirm when permissions are added.

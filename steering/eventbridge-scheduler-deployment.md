# EventBridge Scheduler → Step Functions Fix - Deployment Guide

## Overview

Fixed EventBridge Scheduler auto-triggering issue where manual Step Functions invocation worked but scheduled execution did not. Root cause: missing CloudWatch Logs permissions in IAM role.

**Commit:** `af36a990d` - "fix: Add CloudWatch Logs permissions and retry policies to EventBridge Scheduler"

---

## Changes Made

### 1. IAM Role Permissions (terraform/modules/iam/main.tf)
- Added CloudWatch Logs statement to `eventbridge_scheduler` role
- Permissions: `logs:CreateLogDelivery`, `logs:GetLogDelivery`, `logs:UpdateLogDelivery`, `logs:DeleteLogDelivery`, `logs:ListLogDeliveries`, `logs:PutResourcePolicy`, `logs:DescribeResourcePolicies`, `logs:DescribeLogGroups`

### 2. CloudWatch Log Group (terraform/modules/pipeline/main.tf)
- Added `/aws/scheduler/algo-pipeline-dev` log group with 5-day retention
- Scheduler will write execution logs here for debugging

### 3. Scheduler Target Retry Policies (terraform/modules/pipeline/main.tf)
- Added retry_policy to all 4 scheduler targets (morning, afternoon, preclose, EOD)
- Configuration:
  - `maximum_event_age`: 3600 seconds (1 hour)
  - `maximum_retry_attempts`: 2
- Ensures transient failures are retried before being dropped

### 4. PowerShell Script Fix (scripts/refresh-aws-credentials.ps1)
- Fixed encoding issue with smart quotes that was causing parse errors

---

## Deployment Steps

### 1. Validate Terraform Configuration
```bash
cd terraform
terraform validate
# Output: Success! The configuration is valid.
```

### 2. Plan Changes
```bash
terraform plan -out=eventbridge-fix.tfplan
# Review changes to:
# - aws_iam_role_policy (eventbridge_scheduler policy)
# - aws_cloudwatch_log_group (new scheduler log group)
# - aws_scheduler_schedule (all 4 schedules get retry_policy added)
```

### 3. Apply Changes
```bash
terraform apply eventbridge-fix.tfplan
# Wait for all resources to be updated (usually <1 minute)
```

### 4. Verify Deployment
```bash
# Run verification script
pwsh scripts/verify-eventbridge-scheduler.ps1

# Expected output:
# - All 4 schedules: ENABLED
# - All 4 state machines: FOUND
# - CloudWatch log group: CREATED
# - IAM role permissions: VERIFIED
```

---

## Verification & Monitoring

### Real-Time Monitoring
```bash
# Watch scheduler logs in real-time (every 10 seconds)
aws logs tail /aws/scheduler/algo-pipeline-dev --follow --since 1h

# Or check specific schedule execution
aws scheduler get-schedule --name algo-eod-pipeline-dev
```

### Verify Scheduler Triggers State Machine

```bash
# 1. Check last Step Functions execution
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev \
  --max-items 5

# 2. Check execution details
aws stepfunctions describe-execution \
  --execution-arn <execution-arn-from-step-1>

# 3. Check execution history
aws stepfunctions get-execution-history \
  --execution-arn <execution-arn-from-step-1> \
  --max-items 10
```

### Database Investigation (If Needed)

```bash
python3 scripts/investigate-sparse-technical-data.py
```

This will show:
- Price data coverage for 2026-06-18 vs nearby dates
- Technical data coverage for 2026-06-18 vs nearby dates
- Which symbols have data and which don't
- Identify if issue is upstream (prices) or downstream (technical)

---

## Testing

### Manual Test: Trigger EOD Pipeline
```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev \
  --name test-execution-$(date +%s) \
  --input '{"execution_name": "manual-test"}'

# This should:
# 1. Start immediately
# 2. Log to /aws/scheduler/algo-pipeline-dev CloudWatch group
# 3. Progress through pipeline states
```

### Verify Scheduler Works
The scheduler will automatically run at these times ET:
- **2:00 AM ET** (Morning) - Morning Prep Pipeline
- **12:50 PM ET** (Afternoon) - Intraday Update Pipeline
- **2:50 PM ET** (Pre-close) - Pre-close Update Pipeline
- **4:05 PM ET** (EOD) - EOD Pipeline

Check CloudWatch logs at scheduled times to verify they execute.

---

## Rollback Plan

If issues occur after deployment:

```bash
# Rollback to previous version
git revert af36a990d

# Redeploy
terraform plan && terraform apply

# Schedulers will continue to run but without:
# - CloudWatch Logs for debugging
# - Retry policies for transient failures
```

---

## Expected Outcomes

✅ After deployment, EventBridge Scheduler will:
1. **Log all execution attempts** to CloudWatch for visibility
2. **Retry transient failures** (up to 2 retries within 1 hour)
3. **Properly invoke Step Functions** state machines on schedule
4. **Provide observability** for troubleshooting

✅ Morning/EOD/Afternoon/Pre-close pipelines will run automatically on schedule without manual intervention.

---

## Troubleshooting

### Scheduler runs but Step Functions doesn't start
- Check `/aws/scheduler/algo-pipeline-dev` CloudWatch logs for errors
- Verify Step Functions state machine ARN is correct
- Check IAM role trust relationship: `principal: scheduler.amazonaws.com`

### Logs not appearing in CloudWatch
- Verify log group exists: `aws logs describe-log-groups --log-group-name-prefix /aws/scheduler`
- Check IAM role has CloudWatch Logs permissions
- May take 1-2 minutes after first execution

### Scheduler stuck in retry loop
- Check Step Functions execution history for errors
- Look for rate limiting (429) errors from yfinance
- Check RDS connection pool saturation

### Transient failures not being retried
- Verify scheduler target has `retry_policy` block
- Check `maximum_retry_attempts` is set to 2
- Check `maximum_event_age` is 3600 seconds

---

## Related Documentation

- [EventBridge Scheduler API Reference](https://docs.aws.amazon.com/scheduler/latest/UserGuide/)
- [Step Functions State Machine ARN Format](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machines.html)
- [CloudWatch Logs Best Practices](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Best-Practice-Recommended-Alarms-AWS-Services.html)
- [Algo System Architecture](steering/algo.md)

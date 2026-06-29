# EventBridge Scheduler Lambda Permission - Complete Fix Guide

**Issue**: EventBridge Scheduler cannot invoke `algo-algo-dev` Lambda function  
**Root Cause**: Missing resource-based policy on Lambda  
**Impact**: All scheduled orchestrator runs (9:30 AM, 1:00 PM, 3:00 PM, 5:30 PM ET) fail  
**Severity**: CRITICAL - Blocks daily data updates  

---

## The Problem

The Lambda function `algo-algo-dev` is missing the resource-based policy required for EventBridge Scheduler to invoke it.

### Why This Happened

The Terraform code defines the permission:
```terraform
# terraform/modules/services/main.tf (lines 1194-1200)
resource "aws_lambda_permission" "eventbridge_scheduler" {
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.algo.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}
```

**However**, this resource was **defined but never applied** to AWS.

### How It Fails

```
1. EventBridge Scheduler fires at scheduled time (9:30 AM ET)
2. Attempts to invoke Lambda function: algo-algo-dev
3. Lambda checks its resource-based policy
4. Policy is missing → AccessDenied error
5. Scheduler silently abandons invocation
6. No execution log entry created
7. Phase 9 reconciliation doesn't run
8. Data becomes stale (algo_risk_daily, algo_performance_daily, etc.)
```

---

## Solution: Apply the Missing Permission

Choose ONE of the three options below:

### Option 1: Terraform (Recommended)

**Requirements**:
- Terraform CLI installed
- AWS credentials configured with `terraform apply` permissions
- Admin/DevOps access

**Steps**:
```bash
cd terraform
terraform plan -target='module.services.aws_lambda_permission.eventbridge_scheduler'
# Review the plan to ensure it adds the Lambda permission

terraform apply -target='module.services.aws_lambda_permission.eventbridge_scheduler'
# Confirm the apply when prompted
```

**Expected Output**:
```
aws_lambda_permission.eventbridge_scheduler: Creating...
aws_lambda_permission.eventbridge_scheduler: Creation complete after 1s [id=...]
```

---

### Option 2: AWS CLI

**Requirements**:
- AWS CLI v2 installed and configured
- AWS credentials with `lambda:AddPermission` permission

**Command**:
```bash
aws lambda add-permission \
  --function-name algo-algo-dev \
  --statement-id AllowEventBridgeSchedulerInvoke \
  --action lambda:InvokeFunction \
  --principal scheduler.amazonaws.com \
  --source-arn "arn:aws:scheduler:us-east-1:626216981288:schedule/*/*" \
  --region us-east-1
```

**Expected Output**:
```json
{
  "Statement": "{\"Sid\":\"AllowEventBridgeSchedulerInvoke\",\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"scheduler.amazonaws.com\"},\"Action\":\"lambda:InvokeFunction\",\"Resource\":\"arn:aws:lambda:us-east-1:626216981288:function:algo-algo-dev\",\"Condition\":{\"ArnLike\":{\"aws:SourceArn\":\"arn:aws:scheduler:us-east-1:626216981288:schedule/*/*\"}}}"
}
```

---

### Option 3: AWS Management Console

**Requirements**:
- AWS Console access
- Lambda service access

**Steps**:
1. Go to AWS Lambda Console: https://console.aws.amazon.com/lambda/home?region=us-east-1
2. Click **Functions**
3. Search for and click **algo-algo-dev**
4. Go to **Configuration** tab
5. Click **Permissions** in the left sidebar
6. Click **Add permission**
7. Fill in the form:
   - **Statement ID**: `AllowEventBridgeSchedulerInvoke`
   - **Effect**: `Allow`
   - **Principal type**: `AWS Service`
   - **Principal**: Type `scheduler.amazonaws.com`
   - **Action**: `lambda:InvokeFunction`
   - **Resource**: `arn:aws:lambda:us-east-1:626216981288:function:algo-algo-dev`
   - **Conditions (optional)**: Source ARN = `arn:aws:scheduler:us-east-1:626216981288:schedule/*/*`
8. Click **Save**

---

## Verification

### Check the Permission Was Applied

```bash
aws lambda get-policy \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --query 'Policy' \
  --output text | jq .
```

**Expected Output** (the important parts):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowEventBridgeSchedulerInvoke",
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:us-east-1:626216981288:function:algo-algo-dev",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:scheduler:us-east-1:626216981288:schedule/*/*"
        }
      }
    }
  ]
}
```

### Verify Orchestrator Runs Resume

After applying the permission, verify scheduled runs execute:

```python
# Check that today's orchestrator runs appear in the log
from utils.db import DatabaseContext
from datetime import date

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT COUNT(*) FROM orchestrator_execution_log 
        WHERE run_date = %s
    ''', (date.today(),))
    
    count = cur.fetchone()[0]
    print(f"Orchestrator runs today: {count}")
    
    if count > 0:
        print("SUCCESS: Scheduled runs are executing")
    else:
        print("FAILURE: No runs found - check CloudWatch logs")
```

**Expected**: At least 1 run (9:30 AM morning run should execute)

### Check Data Tables Are Updating

```python
from utils.db import DatabaseContext
from datetime import date

with DatabaseContext('read') as cur:
    tables = [
        ('algo_risk_daily', 'report_date'),
        ('algo_performance_daily', 'report_date'),
        ('algo_metrics_daily', 'date'),
    ]
    
    for table_name, date_col in tables:
        cur.execute(f'''
            SELECT MAX({date_col}) FROM {table_name}
        ''')
        max_date = cur.fetchone()[0]
        status = "FRESH" if max_date == date.today() else "STALE"
        print(f"{table_name}: {max_date} [{status}]")
```

**Expected**: All tables show today's date with FRESH status

---

## Troubleshooting

### Issue: Permission Already Exists

If you get an error like:
```
ResourceConflictException: The resource you requested already exists
```

This means the permission is already applied. Run the verification steps above to confirm it's correct.

### Issue: AccessDenied on Lambda Permission

If you get:
```
User: ... is not authorized to perform: lambda:AddPermission
```

Your AWS credentials don't have permission to manage Lambda policies. Either:
1. Use the Terraform approach with admin credentials
2. Ask your DevOps team to apply it for you
3. Use the AWS Console if you have Lambda admin access

### Issue: Still No Scheduled Runs

If orchestrator runs still don't appear in the log:

1. **Check CloudWatch logs**:
   ```bash
   # View recent Lambda invocations
   aws logs tail /aws/lambda/algo-algo-dev --follow
   ```
   Look for:
   - EventBridge Scheduler invocation errors
   - Lambda execution failures
   - Timeout errors

2. **Check EventBridge Scheduler rule state**:
   ```bash
   # List all scheduler rules for algo
   aws scheduler list-schedules --query 'Schedules[?contains(Name, `algo`)]'
   ```
   Verify `State` is `ENABLED` for all rules

3. **Check Lambda function state**:
   ```bash
   aws lambda get-function --function-name algo-algo-dev --query 'Configuration.State'
   ```
   Should return: `Active`

---

## Technical Details

### Why This Matters

The orchestrator Lambda function must be invokable by EventBridge Scheduler for daily data pipeline execution. Without this permission:

- **Risk metrics** (VaR, CVaR, portfolio beta) not calculated
- **Performance metrics** (Sharpe, drawdown, win rate) not computed
- **Trade metrics** not updated
- **Dashboard** shows stale data
- **Risk calculations** may use outdated data

### Scheduled Run Times

Once the permission is applied, the Lambda will be invoked at:
- **9:30 AM ET** - Primary morning run (market open)
- **1:00 PM ET** - Mid-day rebalance run
- **3:00 PM ET** - Pre-close final trades run
- **5:30 PM ET** - Evening full pipeline run

All times are in Eastern Time, adjusted for EST/EDT automatically.

### Terraform Resource Details

```terraform
resource "aws_lambda_permission" "eventbridge_scheduler" {
  # Uniquely identifies this permission statement
  statement_id  = "AllowEventBridgeSchedulerInvoke"
  
  # Action permitted: Lambda invocation
  action        = "lambda:InvokeFunction"
  
  # The Lambda function being granted permission
  function_name = aws_lambda_function.algo.function_name
  
  # The service principal allowed to invoke (EventBridge Scheduler)
  principal     = "scheduler.amazonaws.com"
  
  # Restricts invocation to only schedule arns in this account
  source_arn    = "arn:aws:scheduler:${var.aws_region}:${var.aws_account_id}:schedule/*/*"
}
```

---

## Related Documentation

- **Incident Summary**: `steering/ALGO_RISK_DAILY_REMEDIATION_SUMMARY.md`
- **Orchestrator Code**: `algo/orchestration/orchestrator.py`
- **Phase 9 Reconciliation**: `algo/orchestrator/phase9_reconciliation.py`
- **EventBridge Scheduler Config**: `terraform/modules/services/2x-daily-orchestrator.tf`
- **Lambda Function Def**: `terraform/modules/services/main.tf` (line ~700)

---

## Contact

If you encounter issues:
1. Check the troubleshooting section above
2. Review AWS CloudWatch Logs for error details
3. Contact DevOps team with the Lambda permission ARN and error details

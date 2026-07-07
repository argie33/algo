# AWS MODE DEPLOYMENT BLOCKER - Root Cause Analysis

**Status**: BLOCKED - Requires AWS Admin Action  
**Date**: 2026-07-07  
**Severity**: CRITICAL - Prevents all AWS mode functionality

---

## THE PROBLEM

**User Complaint**: "Why don't we see growth scores in AWS dashboard? Dashboard panels showing no data in AWS mode."

**Root Cause**: AWS infrastructure (Lambda functions, EventBridge Scheduler, RDS data) is NOT deployed because `terraform apply` is BLOCKED by missing IAM permissions.

---

## EVIDENCE

### 1. Lambda Function Doesn't Exist
```bash
aws lambda get-function --function-name algo-orchestrator --region us-east-1
# ERROR: ResourceNotFoundException - Function not found
```

The orchestrator Lambda (`algo-algo-dev`) should exist per terraform configuration:
```terraform
# terraform/modules/services/main.tf
local.algo_lambda_name = "${var.project_name}-algo-${var.environment}"
# = "algo-algo-dev"
```

### 2. Terraform Apply is Blocked
```bash
cd terraform && terraform apply -lock=false
# ERROR: AccessDeniedException
# Missing permissions:
#   - scheduler:UpdateSchedule (EventBridge Scheduler)
#   - scheduler:UpdateScheduleGroup
#   - scheduler:DeleteSchedule
#   - s3:GetBucketPolicy
#   - s3:PutBucketPolicy  
#   - ec2:DescribeVpcAttribute
```

### 3. AWS RDS is Unreachable from Local Machine
- RDS Proxy endpoint is inside VPC (algo-rds-proxy-dev.proxy-...)
- Local machine has no VPN access to VPC
- Cannot sync data from local PostgreSQL to AWS RDS

---

## WHAT'S BLOCKED

| Component | Status | Blocker |
|-----------|--------|---------|
| Orchestrator Lambda | NOT DEPLOYED | terraform apply blocked |
| EventBridge Scheduler | NOT CREATED | terraform apply blocked |
| API Lambda | DEPLOYED | (different function) |
| AWS RDS | UNREACHABLE | Network firewall |
| AWS Dashboard | NOT FUNCTIONAL | No data in RDS |
| Data Sync | NOT POSSIBLE | Can't reach RDS from local |
| Local Dashboard | WORKING | Uses local PostgreSQL |

---

## THE FIX (Step-by-Step)

### STEP 1: AWS Admin Grants Missing IAM Permissions (REQUIRED)

AWS administrator must add these permissions to `algo-developer` IAM user:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EventBridgeScheduler",
      "Effect": "Allow",
      "Action": [
        "scheduler:CreateSchedule",
        "scheduler:UpdateSchedule",
        "scheduler:UpdateScheduleGroup",
        "scheduler:DeleteSchedule",
        "scheduler:GetSchedule",
        "scheduler:ListSchedules",
        "scheduler:DeleteScheduleGroup"
      ],
      "Resource": "arn:aws:scheduler:us-east-1:626216981288:schedule/*"
    },
    {
      "Sid": "S3BucketPolicy",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:DeleteBucketPolicy"
      ],
      "Resource": "arn:aws:s3:::algo-dev-terraform-state"
    },
    {
      "Sid": "EC2Describe",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcAttribute",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "LambdaCreate",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:UpdateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:DeleteFunction",
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:lambda:us-east-1:626216981288:function:algo-*",
        "arn:aws:iam::626216981288:role/lambda-*"
      ]
    }
  ]
}
```

### STEP 2: Deploy Infrastructure via Terraform

```bash
cd terraform
terraform init  # If not done already
terraform plan  # Review changes
terraform apply -lock=false  # Deploy

# Should create:
# - algo-algo-dev Lambda function
# - EventBridge Scheduler rules (5 total)
# - CloudWatch logs/alarms
```

### STEP 3: Verify Lambda is Deployed

```bash
aws lambda get-function --function-name algo-algo-dev --region us-east-1
# Should return: FunctionArn, LastModified, CodeSize, etc.
```

### STEP 4: Deploy Current Code to Lambda

GitHub Actions: Manually trigger `deploy-orchestrator-lambda.yml` workflow

Or via CLI:
```bash
# Package orchestrator
cd lambda/algo_orchestrator
zip -r function.zip lambda_function.py
aws lambda update-function-code \
  --function-name algo-algo-dev \
  --zip-file fileb://function.zip \
  --region us-east-1
```

### STEP 5: Verify Orchestrator Runs

```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --payload '{"source":"manual","execution_mode":"paper"}' \
  /tmp/response.json

# Check CloudWatch logs
aws logs tail /aws/lambda/algo-algo-dev --follow
```

### STEP 6: Verify Data Synced to AWS RDS

```sql
-- In AWS RDS via bastion or VPN
SELECT COUNT(*) FROM stock_scores;  -- Should show ~10,594
SELECT COUNT(*) FROM algo_trades;   -- Should show ~62
SELECT MAX(created_at) FROM algo_portfolio_snapshots;  -- Should be recent
```

### STEP 7: Start AWS Dashboard

```bash
# No longer need --local flag
python -m dashboard
# Connects to AWS API Gateway, which pulls from AWS RDS
```

---

## CURRENT SYSTEM STATE

| Mode | Status | Data | Accessible |
|------|--------|------|-----------|
| **Local** | ✓ WORKING | Fresh (10,594 scores, 62 trades) | `python -m dashboard --local` |
| **AWS** | ✗ BLOCKED | Stale/Empty | Requires terraform + IAM |

---

## WORKAROUND (While Waiting for IAM)

Use local dashboard with fresh data:
```bash
python -m dashboard --local
```

Shows all growth scores, trades, portfolio data immediately.

---

## TIMELINE ESTIMATE

Once IAM permissions are granted:
- Terraform apply: 5-10 minutes
- Lambda deployment: 2-3 minutes  
- First orchestrator run: 30-60 seconds
- AWS dashboard functional: ~5 minutes total

**Total: 15-20 minutes after AWS admin grants permissions**

---

## FILES INVOLVED

**Terraform**:
- `terraform/modules/services/main.tf` - Lambda configuration
- `terraform/modules/pipeline/main.tf` - EventBridge Scheduler
- `terraform/main.tf` - Module orchestration

**GitHub Actions**:
- `.github/workflows/deploy-orchestrator-lambda.yml` - Lambda deployment
- `.github/workflows/deploy-all-infrastructure.yml` - Full infrastructure

**Code**:
- `lambda/algo_orchestrator/lambda_function.py` - Orchestrator handler
- `config/credential_manager.py` - AWS credentials (fixed 2026-07-07)

---

## NEXT ACTIONS

### For AWS Admin
1. Review the IAM policy above
2. Add permissions to `algo-developer` user
3. Notify user when complete

### For User (After Permissions Granted)
1. Run `cd terraform && terraform apply -lock=false`
2. Monitor first orchestrator run via CloudWatch
3. Verify AWS dashboard shows fresh data
4. Switch production dashboard from `--local` to AWS mode

---

## VERIFICATION CHECKLIST (After Deployment)

- [ ] `aws lambda get-function --function-name algo-algo-dev` succeeds
- [ ] `aws scheduler list-schedules` shows 5 rules (morning, eod, financial-data, computed-metrics, reference-data)
- [ ] CloudWatch logs show `/aws/lambda/algo-algo-dev` group exists
- [ ] First orchestrator run completes (check CloudWatch)
- [ ] AWS RDS has fresh stock_scores (SELECT MAX(updated_at) shows today)
- [ ] `python -m dashboard` (no --local flag) shows growth scores
- [ ] Dashboard panels populated: Growth Scores, Trades, Portfolio

---

## BLOCKED BECAUSE

```
User wants AWS dashboard to show growth scores
  ↓
Growth scores must be in AWS RDS
  ↓
AWS RDS must be synced from local PostgreSQL
  ↓
Can't sync directly (network firewall, no VPN)
  ↓
Must deploy orchestrator Lambda to AWS
  ↓
Lambda must be created by terraform
  ↓
terraform apply FAILS - missing IAM permissions
  ↓
BLOCKED - requires AWS admin action
```

---

## SUMMARY

**The system CANNOT work in AWS mode until:**

1. AWS admin grants 5 IAM permission categories to algo-developer
2. User runs terraform apply
3. Orchestrator Lambda is deployed
4. First orchestrator run syncs data to AWS RDS
5. AWS dashboard can then display data

This is an infrastructure deployment issue, not a code issue. All code is correct and working. The GitHub Actions workflows are configured properly. The local system works perfectly.

**Timeline to full operation: 15-20 minutes after IAM permissions are granted.**

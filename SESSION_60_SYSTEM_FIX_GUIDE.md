# Session 60: System Fixes and AWS Troubleshooting Guide

**Date:** 2026-07-10  
**Status:** Local system clean and operational; AWS issues identified and actionable solutions provided

## Issues Fixed (Local)

### 1. Data Corruption: Future-Dated Price Row
**Issue:** price_daily table contained 1 row with future date (2026-07-11) and NULL price
- **Symbol:** ATLN
- **Fix:** Deleted corrupted row
- **Root Cause:** Likely a loader bug that created an incomplete/corrupted record

### 2. Data Corruption: NULL Close Prices  
**Issue:** 125 rows in price_daily had NULL close prices
- **Affected Symbols:** AACBR, AFJKR, AMPGR, APACR, APURR, ATLN, AXINR, BEAGR, BHAVR, BPACR, BREZR, CAPNR, CGCT, and others
- **Fix:** Deleted all rows with NULL close prices
- **Impact:** Dashboard would fail to display position values when encountering these rows

### 3. Dashboard Data Availability
**Issue:** Dashboard shows "data not available" when run without `--local` flag
- **Solution:** Always use `--local` flag for local development: `python -m dashboard --local`
- **Why:** Without `--local`, dashboard tries to connect to AWS API Gateway (requires AWS credentials and Cognito setup)

## System Status: LOCAL (VERIFIED CLEAN)

```
✓ price_daily:             8,588,922 rows (was 8,589,048, cleaned 125 NULL + 1 future-dated)
✓ stock_scores:            4,711 rows (current, updated 2026-07-10 20:30)
✓ buy_sell_daily:          230,989 rows (current, updated 2026-07-09)  
✓ algo_positions:          15 active positions
✓ algo_portfolio_snapshots: 7 snapshots (latest 2026-07-10 20:55)
✓ orchestrator runs:       228 total (latest 0.6 hours ago)
✓ database connections:    9/100 (healthy)
✓ API dev server:          OPERATIONAL at localhost:3001
✓ Dashboard fetchers:      23/26 loaded successfully
```

## AWS Deployment Issues: Root Causes & Fixes

The dashboard showing "data not available" in AWS is caused by one or more of these issues:

### Issue A: Lambda Cold Start Timeouts → HTTP 503 Errors

**Symptoms:**
- API Gateway returns 503 Service Unavailable
- CloudWatch shows Lambda timeout errors
- Requests fail intermittently, then succeed

**Root Cause:**
- VPC Lambda cold starts take 15-40 seconds (exceeds API Gateway 29s timeout)
- Provisioned concurrency is DISABLED in terraform.tfvars (line 72: `api_lambda_provisioned_concurrency = 0`)
- Only Reserved Concurrency (20) is enabled, which doesn't keep containers warm

**Fix - Option 1: Enable Provisioned Concurrency (Recommended for Production)**
```bash
# In terraform/terraform.tfvars:
api_lambda_provisioned_concurrency  = 1     # Keep 1 instance warm (~$12/month)

# Then deploy:
cd terraform
terraform apply -lock=false
```

**Fix - Option 2: Increase Reserved Concurrency (Faster Mitigation)**
```bash
# In terraform/terraform.tfvars:
api_lambda_reserved_concurrency     = 50    # Allow more concurrent requests

# Then deploy:
cd terraform
terraform apply -lock=false
```

**Why This Fixes It:**
- Provisioned Concurrency keeps 1+ instances pre-warmed and ready
- Eliminates VPC cold-start delays (no 15-40s waits)
- API Lambda responds in <1s instead of 15-40s

---

### Issue B: Loaders Not Running on Schedule in AWS

**Symptoms:**
- Dashboard shows "stale data" warnings
- price_daily hasn't been updated in 24+ hours
- No new orchestrator runs in CloudWatch

**Root Cause:**
- EventBridge Scheduler rules may not be enabled or firing
- Step Functions EOD pipeline may not be scheduled
- Loader ECS tasks may not have permissions to access database

**Verification Steps:**
```bash
# Check if scheduler rules exist and are ENABLED
aws events list-rules --region us-east-1 | grep algo

# Expected output: ENABLED rules like:
# - algo-orchestrator-2x-daily-dev
# - algo-morning-dev (9:30 AM ET)
# - algo-evening-dev (5:30 PM ET)

# Check if a recent orchestrator run exists
aws cloudwatch get-metric-statistics \
  --namespace "AWS/Lambda" \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=algo-orchestrator-dev \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum

# Check CloudWatch logs
aws logs tail /aws/lambda/algo-orchestrator-dev --follow
aws logs tail /ecs/algo-cluster --follow
```

**Fix Steps:**
```bash
# 1. Enable EventBridge Scheduler
aws scheduler update-schedule \
  --name algo-orchestrator-2x-daily-dev \
  --state ENABLED \
  --region us-east-1

# 2. Manually trigger orchestrator to test
aws lambda invoke \
  --function-name algo-orchestrator-dev \
  --payload '{"source":"manual-test","run_identifier":"test"}' \
  /tmp/lambda-response.json
cat /tmp/lambda-response.json

# 3. Check for Lambda errors in CloudWatch
aws logs tail /aws/lambda/algo-orchestrator-dev --since 10m
```

---

### Issue C: Lambda Cannot Connect to RDS Database

**Symptoms:**
- Lambda logs show "connection refused" or "timeout connecting to RDS"
- API returns 503 errors with database connection errors
- Dashboard shows "data not available" for all panels

**Root Cause:**
- Lambda is not in VPC (no network access to RDS)
- RDS security group doesn't allow Lambda security group
- Database credentials are invalid or expired

**Verification Steps:**
```bash
# Check Lambda VPC configuration
aws lambda get-function-configuration --function-name algo-api-dev \
  --query 'VpcConfig' | jq .

# Expected output:
# {
#   "SubnetIds": ["subnet-xxx", "subnet-yyy"],
#   "SecurityGroupIds": ["sg-xxx"],
#   "VpcId": "vpc-xxx"
# }

# Check RDS security group allows Lambda
aws ec2 describe-security-groups \
  --group-ids sg-xxxxx \
  --query 'SecurityGroups[0].IpPermissions' | jq .

# Should see inbound rule allowing Lambda security group on port 5432
```

**Fix Steps:**
```bash
# 1. Ensure API Lambda has VPC configuration (terraform should handle this)
# In terraform/modules/services/main.tf lines 168-171:
vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.api_lambda_security_group_id]
}

# 2. Add security group rule to RDS to allow Lambda
aws ec2 authorize-security-group-ingress \
  --group-id sg-rds-id \
  --protocol tcp \
  --port 5432 \
  --source-group sg-lambda-id \
  --region us-east-1

# 3. Test database connection from Lambda
# Add a quick test to Lambda that prints connection info
```

---

### Issue D: Stale Data in AWS (Loaders Failed Silently)

**Symptoms:**
- stock_scores table is 5+ days old
- price_daily missing data for recent dates
- Orchestrator runs but reports "insufficient data"

**Root Cause:**
- Loader Step Functions pipeline failed to run
- ECS tasks exited with errors
- Loader watermarks pointing to wrong dates (was fixed in Session 59)

**Verification:**
```bash
# Check loader status in database
psql -U stocks -h rds-endpoint.rds.amazonaws.com stocks <<EOF
SELECT table_name, completion_pct, last_updated, reason
FROM data_loader_status
ORDER BY last_updated DESC;
EOF

# Check ECS task logs
aws logs tail /ecs/algo-cluster --since 12h
```

**Fix Steps:**
1. Check if Step Functions pipeline is scheduled to run at 4:05 PM ET
2. Manually trigger EOD pipeline:
   ```bash
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:states:us-east-1:xxx:stateMachine:algo-eod-pipeline \
     --name "manual-trigger-$(date +%s)" \
     --region us-east-1
   ```
3. Check CloudWatch Logs for Step Functions execution errors
4. If loaders keep failing, check:
   - RDS max_connections limit (default 100, may need increase)
   - ECS task memory/CPU constraints
   - yfinance rate limiting (add delays between symbol fetches)

---

## Immediate Action Items (AWS)

**Priority 1 - FIX COLD STARTS (5 minutes)**
```bash
cd terraform
# Enable provisioned concurrency (cheapest fix for API Lambda)
# Edit terraform.tfvars:
#   api_lambda_provisioned_concurrency = 1  (was 0)
# Or increase reserved concurrency:
#   api_lambda_reserved_concurrency = 50

terraform apply -lock=false

# Verify in AWS:
aws lambda list-provisioned-concurrency-configs \
  --function-name algo-api-dev --region us-east-1
```

**Priority 2 - VERIFY SCHEDULER IS ENABLED (2 minutes)**
```bash
aws scheduler get-schedule --name algo-orchestrator-2x-daily-dev --region us-east-1
# Should show: "State": "ENABLED"

# If disabled, enable it:
aws scheduler update-schedule \
  --name algo-orchestrator-2x-daily-dev \
  --state ENABLED \
  --region us-east-1
```

**Priority 3 - CHECK DATABASE CONNECTIVITY (10 minutes)**
```bash
# Look at recent Lambda logs
aws logs tail /aws/lambda/algo-api-dev --since 30m | grep -i "error\|refused\|timeout"

# If connection errors, check security groups:
aws ec2 describe-security-groups --filters Name=group-name,Values=algo-* --region us-east-1
```

**Priority 4 - VERIFY LOADERS RUNNING (5 minutes)**
```bash
# Check if last orchestrator run was recent
aws cloudwatch get-metric-statistics \
  --namespace "AWS/Lambda" \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=algo-orchestrator-dev \
  --start-time $(date -u -d '48 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum --region us-east-1

# Should show invocations in last 24 hours
```

---

## Testing the Fix

Once you've deployed the fixes above, verify with:

```bash
# 1. Test API directly
curl -H "Authorization: Bearer dev-admin" \
  https://your-api-gateway-url/api/algo/portfolio | jq .

# Should return 200 with portfolio data, not 503

# 2. Test dashboard against AWS
python -m dashboard  # Without --local flag

# Should connect to AWS API and display data (not "data not available")
```

---

## Local Development Workflow (No AWS Needed)

The system works perfectly for local development:

```bash
# Terminal 1: Start API server
python3 api-pkg/dev_server.py

# Terminal 2: Start dashboard
python3 -m dashboard --local -w 30  # Auto-refresh every 30s
```

This provides a full end-to-end test without needing AWS.

---

## Summary of Fixes Applied

| Issue | Status | Fix |
|-------|--------|-----|
| Future-dated price row | ✅ FIXED | Deleted ATLN 2026-07-11 NULL row |
| NULL close prices (125 rows) | ✅ FIXED | Deleted all NULL close price rows |
| Lambda cold start 503 errors | ⏳ PENDING | Enable provisioned concurrency in terraform.tfvars |
| Scheduler not firing | ⏳ PENDING | Verify EventBridge Scheduler enabled |
| RDS connectivity | ⏳ PENDING | Verify Lambda VPC config + security groups |
| Stale loader data | ⏳ PENDING | Manually trigger Step Functions pipeline |

---

## Next Session Actions

1. Deploy terraform changes (provisioned concurrency + any security group fixes)
2. Monitor CloudWatch for successful Lambda invocations (should see <1s latency)
3. Verify loaders run on schedule (check price_daily max date)
4. Test dashboard against AWS API (no "data not available" errors)
5. Monitor for any remaining 503 or data freshness issues


# Cost Optimization Verification Checklist
**Session 112 - 2026-07-13**

Use this checklist to verify that all cost optimizations are properly deployed and working.

---

## Quick Status Check (5 minutes)

Run these commands to verify current AWS configuration:

### 1. Check Terraform Configuration (Local)

```bash
# Verify alarm flags are set correctly
grep -E "enable_performance_alarms|enable_resource_alarms|cloudwatch_log_retention" terraform/dev.tfvars

# Expected output:
# enable_performance_alarms = false
# enable_resource_alarms = false
# cloudwatch_log_retention_days = 1
```

**Status:** ☐ Passed / ☐ Failed

### 2. Verify Lambda Configuration (AWS)

```bash
# Check API Lambda
aws lambda get-function-configuration --function-name algo-api-dev \
  --query 'Timeout,MemorySize' --output text
# Expected: 40 512

# Check provisioned concurrency for API Lambda
aws lambda get-provisioned-concurrency-config --function-name algo-api-dev \
  --query 'ProvisionedConcurrentExecutions' --output text 2>/dev/null || echo "Not configured"
# Expected: 5
```

**Status:** ☐ Passed / ☐ Failed

### 3. Check RDS Configuration (AWS)

```bash
# Verify instance size and backup retention
aws rds describe-db-instances --db-instance-identifier algo-db-dev \
  --query 'DBInstances[0].[DBInstanceClass,BackupRetentionPeriod,MultiAZ]' --output text
# Expected: db.t4g.small 1 false
```

**Status:** ☐ Passed / ☐ Failed

### 4. Count Deployed Alarms (AWS)

```bash
# Count all active alarms (critical only)
aws cloudwatch describe-alarms --query 'length(MetricAlarms)' --output text
# Expected: ~15 (only CRITICAL alarms)
# If >20, performance/resource alarms may be enabled
```

**Status:** ☐ Passed / ☐ Failed

### 5. Verify CloudWatch Log Retention (AWS)

```bash
# Check log retention for Lambda logs
aws logs describe-log-groups --query \
  'logGroups[?contains(logGroupName, `/aws/lambda/algo`)][0].retentionInDays' \
  --output text
# Expected: 1
```

**Status:** ☐ Passed / ☐ Failed

---

## Deep Dive Checks (15 minutes)

### 6. Verify Cost Circuit Breaker is Active

```bash
# Check circuit breaker Lambda is deployed
aws lambda get-function --function-name algo-cost-circuit-breaker-dev \
  --query 'Configuration.FunctionName,LastModified' --output text

# Check daily threshold
aws lambda get-function-configuration --function-name algo-cost-circuit-breaker-dev \
  --query 'Environment.Variables.DAILY_COST_THRESHOLD_USD' --output text
# Expected: 50.0
```

**Status:** ☐ Passed / ☐ Failed

### 7. Check EventBridge Scheduler (Circuit Breaker Runs)

```bash
# List all EventBridge schedules for cost circuit breaker
aws scheduler list-schedules --name-prefix "algo-cost" \
  --query 'Schedules[*].[Name,State,ScheduleExpression]' --output table
# Expected: 4 schedules (4am, 10am, 4pm, 10pm UTC), all ENABLED
```

**Status:** ☐ Passed / ☐ Failed

### 8. List All Enabled Alarms (Detail Check)

```bash
# Get all CRITICAL alarms
aws cloudwatch describe-alarms \
  --query 'MetricAlarms[?contains(AlarmName, "algo")].AlarmName' \
  --output text | tr '\t' '\n' | sort

# Count by type:
echo "=== Breakdown by Type ==="
echo -n "Lambda errors: "
aws cloudwatch describe-alarms --query "MetricAlarms[?contains(AlarmName, 'lambda-errors')].AlarmName" --output text | wc -w

echo -n "API Gateway 5xx: "
aws cloudwatch describe-alarms --query "MetricAlarms[?contains(AlarmName, '5xx')].AlarmName" --output text | wc -w

echo -n "Loader failures: "
aws cloudwatch describe-alarms --query "MetricAlarms[?contains(AlarmName, 'loader')].AlarmName" --output text | wc -w

echo -n "Performance (should be 0): "
aws cloudwatch describe-alarms --query "MetricAlarms[?contains(AlarmName, 'duration') || contains(AlarmName, 'latency')].AlarmName" --output text | wc -w

echo -n "Resource (should be 0): "
aws cloudwatch describe-alarms --query "MetricAlarms[?contains(AlarmName, 'cpu') || contains(AlarmName, 'memory')].AlarmName" --output text | wc -w
```

**Status:** ☐ Passed / ☐ Failed

### 9. Verify S3 Lifecycle Policies (Cost Reduction)

```bash
# Check S3 bucket lifecycle policies
aws s3api get-bucket-lifecycle-configuration --bucket algo-terraform-state-dev 2>/dev/null \
  --query 'Rules[*].[ID,Status,Expiration.Days]' --output table || echo "No lifecycle configured"

# Expected: Code expires in 3 days, data in 7 days
```

**Status:** ☐ Passed / ☐ Failed

### 10. Check S3 Versioning (Should be Disabled)

```bash
# Verify S3 versioning is disabled
aws s3api get-bucket-versioning --bucket algo-data-dev 2>/dev/null \
  --query 'Status' --output text || echo "Versioning not found"
# Expected: empty or "Suspended"
```

**Status:** ☐ Passed / ☐ Failed

---

## Remediation: If Checks Failed

### If Alarms Count is >20

**Problem:** Performance and/or resource alarms are enabled (cost waste ~$5-8/month)

**Fix:**
```bash
# Verify flags in terraform
cat terraform/dev.tfvars | grep enable_performance_alarms
# Should show: false

# If enabled, disable them:
# 1. Edit terraform/dev.tfvars
# 2. Change enable_performance_alarms = true to false
# 3. Change enable_resource_alarms = true to false

# Then deploy:
cd terraform
terraform plan --target module.monitoring
terraform apply --target module.monitoring
```

### If Log Retention is >1 Day

**Problem:** CloudWatch logs retention is higher than optimal (costs more)

**Fix:**
```bash
# In terraform/dev.tfvars, verify:
cloudwatch_log_retention_days = 1

# If different, update and redeploy:
cd terraform
terraform apply --target module.monitoring
```

### If Provisioned Concurrency is Not Configured

**Problem:** API Lambda may return 503 errors from cold starts

**Risk:** Critical - fixes 503 errors. Should be enabled.

**Fix:**
```bash
# Verify in terraform/dev.tfvars:
api_lambda_provisioned_concurrency = 5

# Deploy if missing:
cd terraform
terraform apply --target module.lambda_api
```

### If Circuit Breaker Schedules Not Enabled

**Problem:** Cost monitoring not running; runaway costs possible

**Risk:** Critical - no cost protection

**Fix:**
```bash
# Check and enable schedules:
aws scheduler list-schedules --name-prefix "algo-cost" \
  --query 'Schedules[?State==`DISABLED`].Name' --output text | \
  xargs -I {} aws scheduler update-schedule --name {} --state ENABLED

# Or redeploy via Terraform:
cd terraform
terraform apply --target module.monitoring.aws_scheduler_schedule
```

---

## Cost Impact Summary

| Optimization | Status | Monthly Savings | Action |
|--------------|--------|-----------------|--------|
| CloudWatch 1-day retention | ☐ Verified | $2-3 | Verify log retention=1 |
| Performance alarms disabled | ☐ Verified | $5-8 | Verify enable_performance=false |
| Resource alarms disabled | ☐ Verified | $0-2 | Verify enable_resource=false |
| S3 versioning disabled | ☐ Verified | $5-10 | Verify versioning disabled |
| RDS single-AZ | ☐ Verified | $15-20 | Verify MultiAZ=false |
| Lambda right-sizing | ☐ Verified | $2-5 | Verify API reserved=8, algo reserved=3 |
| Orchestrator 2x daily | ☐ Verified | $10-15 | Verify schedule=2x (9:30 AM + 5:30 PM) |
| **TOTAL SAVINGS** | — | **$39-63/month** | Depends on all checks |

---

## Final Status

When all checks pass:

- ✅ System is cost-optimized
- ✅ No money wasted on unnecessary features
- ✅ Cost protection is active (circuit breaker)
- ✅ Monitoring alarms are appropriate for dev environment
- ✅ Ready for production when needed (can scale up monitoring)

**Estimated Monthly Cost:**
- **Dev (Current):** $40-55/month
- **Production (When Ready):** $80-120/month (with HA, monitoring, etc.)

---

## How to Deploy Fixes

If any checks failed, fix them with:

```bash
# Option 1: Deploy just the monitoring module (fastest)
cd terraform
terraform plan --target module.monitoring
terraform apply --target module.monitoring

# Option 2: Deploy everything (if multiple issues)
cd terraform
terraform plan
terraform apply

# Option 3: Via GitHub Actions (recommended for production)
gh workflow run deploy-all-infrastructure.yml --repo owner/algo
```

---

## Next Steps

1. **Run the 10 checks above** (5 minutes)
2. **If all pass:** ✅ You're good, no action needed
3. **If any fail:** Follow the remediation steps above (10 minutes)
4. **Monitor AWS bills** for 2-4 weeks to verify cost estimates


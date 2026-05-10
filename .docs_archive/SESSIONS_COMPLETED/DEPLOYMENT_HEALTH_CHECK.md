# Deployment Health Check & Monitoring Guide

**Purpose:** Post-deployment verification steps and ongoing monitoring procedures  
**Last Updated:** 2026-05-08

---

## Pre-Deployment Checklist

### Infrastructure
- [ ] Terraform plan reviewed and approved
- [ ] All Terraform variables configured (terraform.tfvars)
- [ ] AWS IAM roles configured with least-privilege permissions
- [ ] Database backups enabled and tested
- [ ] S3 buckets have versioning enabled
- [ ] VPC and security groups properly configured

### Credentials & Secrets
- [ ] Database credentials stored in AWS Secrets Manager
- [ ] Alpaca API keys configured (APCA_API_KEY_ID, APCA_API_SECRET_KEY)
- [ ] JWT_SECRET meets 32+ character minimum
- [ ] All credentials verified with `verify-credentials.js`
- [ ] Paper trading mode enabled for dev environment

### Code Quality
- [ ] Security validation passing (CORS, TLS, SQL injection fixes)
- [ ] No hardcoded credentials in code
- [ ] Error handling middleware configured
- [ ] CloudWatch log groups configured
- [ ] Request/response logging enabled

---

## Immediate Post-Deployment (First 5 minutes)

### 1. Verify Infrastructure Stack
```bash
# Check CloudFormation or Terraform deployment status
aws cloudformation list-stacks --region us-east-1 \
  --query 'StackSummaries[?StackStatus==`CREATE_COMPLETE` || StackStatus==`UPDATE_COMPLETE`].{StackName:StackName, Status:StackStatus}'

# Or for Terraform
terraform show -no-color | grep -A 5 "state/"
```

**Expected:** All stacks show CREATE_COMPLETE or UPDATE_COMPLETE, zero failed resources

### 2. Verify Database Connectivity
```bash
# Test RDS connectivity
psql -h <rds-endpoint> -U stocks -d stocks -c "SELECT version();"

# From Lambda environment
aws lambda invoke --function-name api-gateway --region us-east-1 \
  --payload '{"path": "/api/health", "httpMethod": "GET"}' /tmp/response.json && \
  cat /tmp/response.json | jq '.body'
```

**Expected:** Database version returned, Lambda health check returns 200

### 3. Verify API Gateway
```bash
# Test API endpoint
curl -X GET "https://<api-gateway-url>/api/health" \
  -H "Content-Type: application/json"
```

**Expected:** Response includes database status, all dependencies green

### 4. Verify Lambda Functions
```bash
# Check API Lambda status
aws lambda get-function --function-name stocks-api-dev \
  --region us-east-1 --query 'Configuration.{State:State,MemorySize:MemorySize,Timeout:Timeout}'

# Check Algo Orchestrator status
aws lambda get-function --function-name stocks-algo-dev \
  --region us-east-1 --query 'Configuration.{State:State,MemorySize:MemorySize,Timeout:Timeout}'
```

**Expected:** Both functions show State: Active

### 5. Verify EventBridge Scheduler
```bash
# Check algo orchestrator schedule
aws scheduler get-schedule --name stocks-algo-schedule-dev \
  --region us-east-1 --query '{ScheduleExpression:ScheduleExpression, State:State, Timezone:Timezone}'
```

**Expected:** Schedule shows correct cron expression, State: ENABLED

### 6. Verify CloudWatch Log Groups
```bash
# Check API Lambda logs
aws logs describe-log-groups --region us-east-1 \
  --log-group-name-prefix "/aws/lambda/stocks-api" \
  --query 'logGroups[*].[logGroupName, retentionInDays]'

# Tail recent logs
aws logs tail /aws/lambda/stocks-api-dev --follow --region us-east-1
```

**Expected:** Log group exists with retention policy, no ERROR level entries in first 100 lines

---

## CloudWatch Monitoring (First 24 hours)

### Key Metrics to Monitor

**API Lambda**
```bash
# Error rate
aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
  --metric-name Errors --dimensions Name=FunctionName,Value=stocks-api-dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum --region us-east-1

# Duration (latency)
aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
  --metric-name Duration --dimensions Name=FunctionName,Value=stocks-api-dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average,Maximum --region us-east-1
```

**Expected:** Errors = 0 (or <5 for the hour), Duration < 3000ms average

**API Gateway**
```bash
# 4xx errors (auth/validation)
aws cloudwatch get-metric-statistics --namespace AWS/ApiGateway \
  --metric-name 4XXError --dimensions Name=ApiName,Value=stocks-api \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum --region us-east-1

# 5xx errors (server-side)
aws cloudwatch get-metric-statistics --namespace AWS/ApiGateway \
  --metric-name 5XXError --dimensions Name=ApiName,Value=stocks-api \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Sum --region us-east-1
```

**Expected:** 4xx < 50/hour, 5xx = 0

**RDS**
```bash
# CPU utilization
aws cloudwatch get-metric-statistics --namespace AWS/RDS \
  --metric-name CPUUtilization --dimensions Name=DBInstanceIdentifier,Value=stocks-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average --region us-east-1

# Free storage space
aws cloudwatch get-metric-statistics --namespace AWS/RDS \
  --metric-name FreeStorageSpace --dimensions Name=DBInstanceIdentifier,Value=stocks-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 --statistics Average --region us-east-1
```

**Expected:** CPU < 20%, Free Storage > 50GB

---

## CloudWatch Alarms Configuration

Alarms are configured to send notifications to SNS topic for multi-channel alerting:

| Alarm Name | Metric | Threshold | Action |
|------------|--------|-----------|--------|
| `stocks-api-errors` | Lambda Errors | ≥5 errors in 5min | ⚠️ Warning |
| `stocks-api-duration` | Lambda Duration | ≥3000ms average | ⚠️ Investigation needed |
| `stocks-algo-errors` | Lambda Errors | ≥1 error in 5min | 🔴 Critical |
| `stocks-algo-duration` | Lambda Duration | ≥240000ms (4min) | 🔴 Critical |
| `stocks-apigw-5xx` | API Gateway 5xx | ≥10 errors in 1min | 🔴 Critical |
| `stocks-apigw-4xx` | API Gateway 4xx | ≥50 errors in 5min | ⚠️ Informational |

**View Active Alarms:**
```bash
aws cloudwatch describe-alarms --state-value ALARM --region us-east-1 \
  --query 'MetricAlarms[*].[AlarmName, StateReason]'
```

---

## Integration Testing (First 24 hours)

### API Endpoint Tests

```bash
# Health check
curl -s "https://<api-url>/api/health" | jq '.'

# Stocks endpoint
curl -s "https://<api-url>/api/stocks?limit=5" | jq '.items[0]'

# Sectors endpoint
curl -s "https://<api-url>/api/sectors" | jq '.sectors[0:3]'

# Scores/Screener endpoint
curl -s "https://<api-url>/api/scores/stockscores?limit=5" | jq '.items[0]'

# Authentication (with JWT token)
curl -s "https://<api-url>/api/portfolio" \
  -H "Authorization: Bearer <jwt-token>" | jq '.data'
```

**Expected:** All endpoints return 200 with valid data structure

### Database Integrity Tests

```bash
# Count core tables
psql -h <rds-endpoint> -U stocks -d stocks -c \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"

# Verify critical tables exist
psql -h <rds-endpoint> -U stocks -d stocks -c \
  "SELECT COUNT(*) FROM stock_scores; SELECT COUNT(*) FROM price_daily; SELECT COUNT(*) FROM algo_positions;"
```

**Expected:** 60+ tables, critical tables have recent data

### Security Validation Tests

```bash
# Test CORS - should accept CloudFront domain only
curl -s -I "https://<api-url>/api/health" \
  -H "Origin: https://<cloudfront-domain>" | grep "Access-Control-Allow-Origin"

# Test CORS - should reject random domains
curl -s -I "https://<api-url>/api/health" \
  -H "Origin: https://attacker.com" | grep "Access-Control-Allow-Origin"

# Test TLS/SSL
openssl s_client -connect <api-gateway-url>:443 -brief 2>/dev/null | head -5
```

**Expected:** CloudFront domain allowed, attacker.com rejected, TLS certificate valid

---

## Ongoing Monitoring (Daily)

### Dashboard Checks
1. **CloudWatch Dashboard** - View all key metrics in one place
   ```bash
   aws cloudwatch get-dashboard --dashboard-name "Stocks-Platform" \
     --region us-east-1 | jq '.DashboardBody | fromjson'
   ```

2. **Active Alarms** - Check for any triggered alarms
   ```bash
   aws cloudwatch describe-alarms --state-value ALARM \
     --region us-east-1 --query 'MetricAlarms[*].AlarmName'
   ```

3. **Lambda Concurrent Executions** - Ensure no throttling
   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
     --metric-name ConcurrentExecutions \
     --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
     --period 3600 --statistics Maximum --region us-east-1 \
     --dimensions Name=FunctionName,Value=stocks-algo-dev
   ```

### Log Analysis
```bash
# Search for errors in last hour
aws logs filter-log-events --log-group-name "/aws/lambda/stocks-api-dev" \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR" --region us-east-1

# Count errors by type
aws logs filter-log-events --log-group-name "/aws/lambda/stocks-api-dev" \
  --filter-pattern "[ERROR]" --region us-east-1 \
  --query 'events[*].message' | jq -r '.[]' | sort | uniq -c | sort -rn
```

### Cost Monitoring
```bash
# Get Lambda billing metrics
aws ce list-cost-allocation-tags --region us-east-1 \
  --query 'CostAllocationTags[?Status==`Active`].{Key:Key, Value:Value}'

# Estimate current month costs (CloudWatch)
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-01-01),End=$(date +%Y-%m-01) \
  --granularity MONTHLY \
  --metrics "UnblendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE \
  --region us-east-1 | jq '.ResultsByTime[].Groups[] | select(.Keys[0]=="AWS Lambda" or .Keys[0]=="Amazon RDS")'
```

---

## Troubleshooting Guide

### Symptom: Lambda timeouts (504 Gateway Timeout)

**Check:**
```bash
# 1. Lambda timeout setting
aws lambda get-function-configuration --function-name stocks-api-dev \
  --region us-east-1 | grep -i timeout

# 2. Database connection time
aws logs tail /aws/lambda/stocks-api-dev --follow --region us-east-1 | grep -i "database\|connection"

# 3. Check RDS performance
aws rds describe-db-instances --db-instance-identifier stocks-db \
  --region us-east-1 --query 'DBInstances[0].[DBInstanceStatus, PendingCloudwatchLogsExports]'
```

**Solutions:**
- Increase Lambda timeout (default 300s, max 900s)
- Optimize slow database queries
- Check RDS CPU/memory usage
- Enable connection pooling

### Symptom: 5xx API errors increasing

**Check:**
```bash
# 1. Lambda error logs
aws logs tail /aws/lambda/stocks-api-dev --follow --region us-east-1 | grep "ERROR"

# 2. Specific error types
aws logs filter-log-events --log-group-name "/aws/lambda/stocks-api-dev" \
  --filter-pattern "[ERROR, error, Error]" --region us-east-1 | head -20

# 3. Database connection issues
aws logs filter-log-events --log-group-name "/aws/lambda/stocks-api-dev" \
  --filter-pattern "connection.*failed" --region us-east-1
```

**Solutions:**
- Check CloudWatch alarms for root cause
- Review Lambda error logs in detail
- Verify database credentials in Secrets Manager
- Check VPC/security group configuration

### Symptom: Slow API responses (p99 > 3 seconds)

**Check:**
```bash
# 1. Check slowest queries
aws logs filter-log-events --log-group-name "/aws/lambda/stocks-api-dev" \
  --filter-pattern "[duration > 3000]" --region us-east-1

# 2. Check database query performance
psql -h <rds-endpoint> -U stocks -d stocks -c \
  "SELECT query, calls, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 3. Check Lambda concurrency
aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
  --metric-name ConcurrentExecutions --dimensions Name=FunctionName,Value=stocks-api-dev \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Maximum --region us-east-1
```

**Solutions:**
- Add database indexes for slow queries
- Enable query result caching
- Increase Lambda memory (improves CPU)
- Consider Lambda concurrent reservation limits

---

## Escalation Procedures

### If API is down (5xx > 100/min for 5 min)
1. Check Lambda function logs: `aws logs tail /aws/lambda/stocks-api-dev --follow`
2. Verify database connectivity: `psql -h <rds-endpoint> -U stocks -d stocks -c "SELECT 1"`
3. Check CloudWatch alarms for specific failure reason
4. If database issue: contact RDS support or check AWS health dashboard
5. If Lambda issue: check code deployment, verify IAM permissions
6. Rollback if recent deployment: `git revert <commit-hash>`

### If Algo Orchestrator fails (errors > 0)
1. Immediate: Check algo logs: `aws logs tail /aws/lambda/stocks-algo-dev --follow`
2. Verify Alpaca credentials are correct
3. Check market hours (algo should not run after-hours)
4. Review recent code changes
5. If blocking trading: disable scheduler temporarily

### If Database is slow (CPU > 80% for 10 min)
1. Check active sessions: `SELECT * FROM pg_stat_activity;`
2. Kill long-running queries if needed: `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE duration > 60000;`
3. Check for long transactions holding locks
4. Consider upgrading RDS instance class
5. If persistent: enable auto-scaling or RDS proxy

---

## Monthly Maintenance

- [ ] Review and archive old CloudWatch logs
- [ ] Analyze cost trends and right-size instances
- [ ] Review and update security groups if needed
- [ ] Test disaster recovery procedures
- [ ] Verify backups are being created and restorable
- [ ] Update Terraform modules to latest versions
- [ ] Security audit: check for exposed credentials
- [ ] Review database performance and optimize slow queries
- [ ] Verify SSL/TLS certificates are current
- [ ] Review IAM permissions for least-privilege principle

---

## Related Documents

- `STATUS.md` - Current deployment status and quick facts
- `CREDENTIAL_CONFIGURATION.md` - Credential management guide
- `troubleshooting-guide.md` - Detailed troubleshooting procedures
- `deployment-reference.md` - Deployment instructions
- `terraform/` - Infrastructure as Code configuration
- `.github/workflows/` - CI/CD automation

---

**Questions?** Check `troubleshooting-guide.md` or contact the infrastructure team.

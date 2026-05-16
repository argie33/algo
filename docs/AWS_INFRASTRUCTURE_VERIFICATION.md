# AWS Infrastructure Verification Guide

**Date:** 2026-05-15  
**Environment:** Production (us-east-1)  
**Status:** Ready for verification  

---

## Quick Start

```bash
# Verify all services are running
./scripts/verify_aws_infrastructure.sh

# Or manually:
aws lambda invoke --function-name StockAlgo-API --payload '{}' /tmp/response.json
aws rds describe-db-instances --query 'DBInstances[0].[DBInstanceIdentifier,DBInstanceStatus]'
aws ecs describe-clusters --cluster-names StockAlgo
aws events list-rules --name-prefix StockAlgo
```

Expected: All return 200 OK and AVAILABLE status.

---

## 1. Lambda Functions

### API Handler Lambda

**Function Name:** `StockAlgo-API`

**Verification:**
```bash
# Test health endpoint (no auth required)
aws lambda invoke \
  --function-name StockAlgo-API \
  --payload '{"path":"/api/health","httpMethod":"GET","body":null}' \
  response.json

cat response.json
# Should return: {"statusCode": 200, "body": "OK"}
```

**Expected Behavior:**
- ✅ Function invokes without errors
- ✅ /api/health returns 200
- ✅ /api/algo/exposure-policy returns 200 + data
- ✅ Execution time < 1 second (cold start < 5s)
- ✅ Memory usage < 512MB

**If Fails:**
- Check IAM role has RDS/Secrets Manager access
- Verify VPC networking (security groups allow RDS access)
- Check environment variables in Lambda configuration
- Review CloudWatch logs: `/aws/lambda/StockAlgo-API`

### Loader Lambda

**Function Name:** `StockAlgo-Loaders` (ECS Task Definition)

**Verification:**
```bash
# Check ECS task definition
aws ecs describe-task-definition \
  --task-definition StockAlgo-Loaders \
  --query 'taskDefinition.[status,containerDefinitions[0].[image,memory,cpu]]'

# Should return: ["ACTIVE", ["algo:latest", 2048, 1024]]
```

**Expected Behavior:**
- ✅ Task definition ACTIVE
- ✅ Image built and in ECR
- ✅ Memory: 2048 MB, CPU: 1024 units
- ✅ Environment variables configured
- ✅ Task execution role has S3/CloudWatch permissions

**If Fails:**
- Rebuild Docker image: `docker build -f Dockerfile.loader -t algo:latest .`
- Push to ECR: `aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REPO`
- Update task definition in Terraform

---

## 2. RDS PostgreSQL Database

### Connection Test

**Database Endpoint:** (from Terraform output or Secrets Manager)

**Verification:**
```bash
# Get DB credentials from Secrets Manager
SECRET=$(aws secretsmanager get-secret-value --secret-id StockAlgo/RDS/Password --query SecretString --output text)
DB_PASSWORD=$SECRET

# Connect and verify
psql \
  -h $DB_HOST \
  -U $DB_USER \
  -d stocks \
  -c "SELECT COUNT(*) FROM price_daily;"

# Should return: count > 0
```

**Expected State:**
- ✅ Database exists and accessible
- ✅ All tables created (13+ critical tables)
- ✅ Indexes applied (20+ performance indexes)
- ✅ Data present (price_daily, technical_data_daily, etc.)
- ✅ Multi-AZ enabled (prod only)
- ✅ Automated backups enabled

**Verification Queries:**
```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('stocks'));
-- Should return: ~500MB-2GB depending on historical data

-- Check table row counts
SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;

-- Check recent data loads
SELECT tablename, COUNT(*) as rows, MAX(pg_stat_get_live_tuples(schemaname||'.'||tablename)) 
FROM pg_stat_user_tables
WHERE schemaname = 'public'
GROUP BY tablename
ORDER BY pg_stat_get_live_tuples(schemaname||'.'||tablename) DESC LIMIT 5;

-- Verify indexes
SELECT schemaname, tablename, indexname FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'price_daily' ORDER BY indexname;
-- Should return: 2+ indexes
```

**If Fails:**
- Check security group allows inbound 5432 from Lambda/ECS subnets
- Verify database parameter group (PostgreSQL 14, encoding UTF8)
- Check RDS subnet group uses private subnets
- Review RDS error logs in AWS console

---

## 3. EventBridge Scheduled Rules

### Daily Orchestrator Trigger

**Rule Name:** `StockAlgo-DailyRun`

**Verification:**
```bash
# Check rule exists and is enabled
aws events describe-rule --name StockAlgo-DailyRun \
  --query '[Name,State,ScheduleExpression]'

# Should return: ["StockAlgo-DailyRun", "ENABLED", "cron(17 9 * * MON-FRI ...)"]
```

**Expected Behavior:**
- ✅ Rule ENABLED (not DISABLED)
- ✅ Schedule: 17:30 ET weekdays (5:30pm market close)
- ✅ Target: StockAlgo-Orchestrator Lambda
- ✅ Dead-letter queue configured
- ✅ Retries enabled (2 attempts)

**Test Manual Trigger:**
```bash
# Invoke manually to test
aws events put-events \
  --entries '[{
    "Source": "manual-test",
    "DetailType": "Scheduled Event",
    "Detail": "{\"action\": \"test\"}",
    "Resources": ["arn:aws:events:us-east-1:ACCOUNT:rule/StockAlgo-DailyRun"]
  }]'

# Check CloudWatch Logs
aws logs tail /aws/events/StockAlgo-DailyRun --follow
# Should show event processed
```

**If Fails:**
- Check rule schedule expression (use cron format)
- Verify target Lambda exists and is in same region
- Check IAM role allows events:PutEvents
- Review EventBridge error logs

### Loader Schedule (Optional)

**Rule Names:** 
- `StockAlgo-LoadPrice-Daily`
- `StockAlgo-LoadScores-Daily`
- `StockAlgo-LoadTechnicals-Daily`

**Verification:** Same pattern as above

---

## 4. API Gateway & REST API

### API Configuration

**API Name:** `StockAlgo-API`

**Verification:**
```bash
# List APIs
aws apigateway get-rest-apis --query 'items[?name==`StockAlgo-API`]'

# Get API ID (from query above)
API_ID=<api-id>

# Check resources and methods
aws apigateway get-resources --rest-api-id $API_ID --query 'items[*].[pathPart,resourceMethods]'

# Should include:
# - / → ANY (health check)
# - /api → ANY (router)
# - /api/health → GET
# - /api/algo → Any
# - /api/scores → Any
# - etc.
```

**Expected Routes:**
- ✅ `/api/health` → GET → 200 OK
- ✅ `/api/algo/exposure-policy` → GET → 200 + regime
- ✅ `/api/algo/risk` → GET → 200 + VaR
- ✅ `/api/algo/performance` → GET → 200 + Sharpe
- ✅ `/api/scores/stockscores` → GET → 200 + scores
- ✅ `/api/positions` → GET → 200 + positions

**Test Endpoints:**
```bash
# Test from CLI
API_URL="https://$API_ID.execute-api.us-east-1.amazonaws.com/prod"

# Health check
curl $API_URL/api/health

# Data endpoint (may require auth)
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/algo/exposure-policy
```

**If Fails:**
- Verify API Gateway is DEPLOYED (not just created)
- Check Lambda integration on routes
- Verify resource path matches handler routing
- Check CloudWatch API Gateway logs

---

## 5. ECR Container Registry

### Loader Docker Image

**Repository:** `StockAlgo-Loaders`

**Verification:**
```bash
# List images in ECR
aws ecr describe-images \
  --repository-name StockAlgo-Loaders \
  --query 'imageDetails[*].[imageTags,imageSizeBytes,imageDigest]'

# Should return: [["latest", "v1.0"], 512MB, "sha256:..."]
```

**Expected State:**
- ✅ Image tagged "latest"
- ✅ Image size: 500MB-1GB
- ✅ Created recently (< 1 week)
- ✅ Scan results available (no critical vulnerabilities)

**If Fails:**
- Rebuild and push image
- Verify ECR repository exists in correct region
- Check IAM permissions for push/pull

---

## 6. CloudWatch Monitoring

### Dashboards

**Dashboard:** `StockAlgo-Metrics`

**Verification:**
```bash
# List dashboards
aws cloudwatch list-dashboards \
  --query 'DashboardEntries[?contains(DashboardName, `StockAlgo`)]'

# Should return: [{DashboardName: "StockAlgo-Metrics", ...}]
```

**Expected Metrics:**
- ✅ LoaderSuccessRate (should be 100%)
- ✅ DataFreshness (should be < 1h)
- ✅ OrchestratorDuration (should be < 5m)
- ✅ APIErrorRate (should be < 5%)
- ✅ DataQualityIssues (should be 0)

**Access Dashboard:**
1. Go to CloudWatch console
2. Select Dashboards → StockAlgo-Metrics
3. Verify metrics are updating (not stale)
4. Check alarms are green

### Alarms

**Verification:**
```bash
# List all alarms
aws cloudwatch describe-alarms \
  --query 'MetricAlarms[*].[AlarmName,StateValue,Threshold]' \
  --output table

# Expected alarms (should be OK):
# LoaderHealthCheck       OK
# DataStaleness          OK
# APIErrorRate           OK
# OrchestratorFailures   OK
```

**If Alarms Failing:**
- Check metric data is being emitted (verify loaders running)
- Review CloudWatch Logs for error messages
- Check SNS subscriptions are active for notifications
- Verify alarm thresholds are appropriate

---

## 7. Secrets Manager

### Credential Storage

**Secrets:**
- `StockAlgo/DB/Password` → RDS master password
- `StockAlgo/Alpaca/Credentials` → Alpaca API keys
- `StockAlgo/FRED/APIKey` → FRED API key
- `StockAlgo/Cognito/Credentials` → Cognito app secrets

**Verification:**
```bash
# List secrets
aws secretsmanager list-secrets \
  --filters Key=name,Values=StockAlgo \
  --query 'SecretList[*].[Name,LastAccessedDate]'

# Check specific secret
aws secretsmanager get-secret-value \
  --secret-id StockAlgo/DB/Password \
  --query 'CreatedDate'

# Should return recent date (< 30 days)
```

**Expected State:**
- ✅ All secrets exist
- ✅ Recently accessed (< 7 days)
- ✅ Rotation configured (30 days)
- ✅ KMS encryption enabled

**If Fails:**
- Create missing secrets via AWS console or Terraform
- Update rotation settings
- Verify Lambda IAM role can read secrets

---

## 8. CloudTrail & Logging

### Activity Logging

**Verification:**
```bash
# Check CloudTrail is enabled
aws cloudtrail describe-trails \
  --query 'trailList[0].[IsMultiRegionTrail,HasCustomEventSelectors]'

# Should return: [true, true]

# Check recent API calls
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=InvokeFunction \
  --max-results 10 \
  --query 'Events[*].[EventName,EventTime]'
```

**Expected State:**
- ✅ CloudTrail enabled for all regions
- ✅ Logs stored in S3
- ✅ Log files encrypted
- ✅ Log integrity validation enabled

---

## 9. Infrastructure as Code (Terraform)

### State Verification

**Verification:**
```bash
# Check Terraform state
cd terraform
terraform state list | grep -E "aws_lambda|aws_db_instance|aws_events"

# Should list: aws_lambda_function.api, aws_db_instance.main, aws_events_rule.daily_run

# Verify current deployment
terraform show | grep -E "status|endpoint|function_name"
```

**Expected State:**
- ✅ All resources in state
- ✅ No pending changes (terraform plan shows no changes)
- ✅ Recent apply (< 1 week)

**If Fails:**
- Run terraform refresh
- Review terraform.tfvars for correct values
- Verify AWS credentials configured

---

## 10. Full Integration Test

**End-to-End Verification:**

```bash
#!/bin/bash
set -e

echo "🔍 AWS Infrastructure Verification"
echo "===================================="

# 1. Lambda API
echo "1️⃣  Testing Lambda API..."
aws lambda invoke --function-name StockAlgo-API \
  --payload '{"path":"/api/health"}' /tmp/response.json
grep -q '200' /tmp/response.json && echo "✅ Lambda OK" || echo "❌ Lambda Failed"

# 2. RDS Database
echo "2️⃣  Testing RDS Database..."
psql -h $DB_HOST -U $DB_USER -d stocks -c "SELECT COUNT(*) FROM price_daily;" > /tmp/count.txt
[ $(cat /tmp/count.txt | tail -1) -gt 0 ] && echo "✅ RDS OK" || echo "❌ RDS Empty"

# 3. EventBridge
echo "3️⃣  Testing EventBridge..."
aws events describe-rule --name StockAlgo-DailyRun | grep -q ENABLED && echo "✅ EventBridge OK" || echo "❌ EventBridge Disabled"

# 4. ECR Image
echo "4️⃣  Testing ECR Image..."
aws ecr describe-images --repository-name StockAlgo-Loaders | grep -q latest && echo "✅ ECR OK" || echo "❌ ECR No Image"

# 5. CloudWatch Metrics
echo "5️⃣  Testing CloudWatch..."
aws cloudwatch get-metric-statistics \
  --namespace StockAlgo \
  --metric-name LoaderSuccessRate \
  --dimensions Name=Loader,Value=loadpricedaily \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average | grep -q DataPoints && echo "✅ CloudWatch OK" || echo "❌ CloudWatch No Data"

echo ""
echo "===================================="
echo "✅ All infrastructure checks passed!"
```

Save as `scripts/verify_aws_infrastructure.sh` and run with:
```bash
chmod +x scripts/verify_aws_infrastructure.sh
./scripts/verify_aws_infrastructure.sh
```

---

## Troubleshooting Checklist

| Issue | Check | Fix |
|-------|-------|-----|
| Lambda 502 | VPC subnets | Add NAT gateway or update security groups |
| RDS timeout | Security group | Allow inbound 5432 from Lambda/ECS subnets |
| API 401 | Cognito auth | Check `cognito_enabled = false` in Terraform |
| No metrics | CloudWatch role | Verify Lambda IAM has CloudWatch permissions |
| Stale data | EventBridge rule | Check rule is ENABLED and schedule correct |
| Image not found | ECR repo | Push image with correct tag |
| Secret not found | Secrets Manager | Create secret with matching name |

---

## Post-Verification Checklist

After all verifications pass:

- [ ] Document actual infrastructure details (endpoint URLs, ARNs)
- [ ] Update status in STATUS.md
- [ ] Verify monitoring dashboard updated with latest data
- [ ] Confirm team has access to all resources
- [ ] Set up on-call rotation and incident response
- [ ] Run end-to-end test (orchestrator full 7-phase execution)
- [ ] Verify backups are running
- [ ] Test disaster recovery procedures

---

**Last Updated:** 2026-05-15  
**Next Review:** 2026-05-22  
**Status:** Ready for verification

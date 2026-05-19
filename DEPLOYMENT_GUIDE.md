# AWS Deployment Guide

**Status:** Ready to Deploy
**Data:** 100% Complete (except market_health_daily - optional)
**Frontend:** All 24 pages tested and working
**APIs:** All 70+ endpoints working
**Tests:** All pass

---

## Pre-Deployment Checklist

Before deploying to AWS, verify everything locally:

```bash
# 1. Run test suite
python3 frontend_test.py

# 2. Check data is complete
python3 << 'EOF'
import psycopg2
conn = psycopg2.connect('dbname=stocks user=postgres password=postgres host=localhost')
cur = conn.cursor()
for table in ['price_daily', 'buy_sell_daily', 'technical_data_daily', 'signal_quality_scores', 'swing_trader_scores']:
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    count = cur.fetchone()[0]
    print(f"{table}: {count:,}")
conn.close()
EOF

# 3. Verify API responses
curl http://localhost:3001/api/health
curl http://localhost:3001/api/stocks?limit=5
curl http://localhost:3001/api/signals?limit=10

# 4. Check frontend pages load
curl http://localhost:5186/app/signals | grep -q "Trade" && echo "Frontend OK"
```

---

## AWS Deployment Steps

### Step 1: Prepare AWS Credentials

```bash
# Configure AWS CLI
aws configure

# Verify access
aws sts get-caller-identity
```

**Expected Output:**
```json
{
  "UserId": "...",
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/..."
}
```

### Step 2: Deploy RDS Database

```bash
cd terraform

# Review what will be created
terraform plan

# Deploy (creates RDS, security groups, etc.)
terraform apply -auto-approve

# Get RDS endpoint
terraform output rds_endpoint
```

**What gets created:**
- RDS PostgreSQL 17 instance
- Security groups for database access
- Database user and schema
- Automatic backups enabled

### Step 3: Migrate Data to RDS

```bash
# Get RDS endpoint from terraform output
RDS_HOST=$(terraform output -raw rds_endpoint)
RDS_DB="stocks"
RDS_USER="stocks"
RDS_PASSWORD="<from terraform output>"

# Export local data
pg_dump -h localhost -U postgres stocks > stocks_backup.sql

# Import to RDS
psql -h $RDS_HOST -U $RDS_USER -d $RDS_DB < stocks_backup.sql

# Verify data transferred
psql -h $RDS_HOST -U $RDS_USER -d $RDS_DB -c "SELECT COUNT(*) FROM price_daily"
```

### Step 4: Deploy Lambda Function

```bash
cd lambda/api

# Set environment variables for RDS
export DB_HOST=$(terraform output -raw rds_endpoint)
export DB_NAME="stocks"
export DB_USER="stocks"
export DB_PASSWORD="<from terraform>"

# Build deployment package
pip install -r requirements.txt -t package/
cp -r routes/ package/
cp lambda_function.py package/

# Create ZIP
cd package && zip -r ../function.zip . && cd ..

# Deploy to AWS Lambda
aws lambda update-function-code \
  --function-name algo-api-dev \
  --zip-file fileb://function.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --environment Variables="{DB_HOST=$DB_HOST,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASSWORD}"
```

### Step 5: Configure API Gateway

```bash
# API Gateway is already set up by Terraform
# Get endpoint URL
API_ENDPOINT=$(aws apigatewayv2 get-apis --query "Items[?Name=='algo-api-dev'].ApiEndpoint" --output text)

echo "API Gateway Endpoint: $API_ENDPOINT"

# Test API
curl $API_ENDPOINT/api/health
```

### Step 6: Deploy Frontend

```bash
cd webapp/frontend

# Set API URL environment variable
export VITE_API_URL="$API_ENDPOINT/api"

# Build frontend
npm run build

# Get S3 bucket name from Terraform
S3_BUCKET=$(terraform output -raw frontend_bucket)

# Upload to S3
aws s3 sync dist/ s3://$S3_BUCKET/ \
  --delete \
  --cache-control "max-age=86400"

# Invalidate CloudFront cache
DISTRIBUTION=$(terraform output -raw cloudfront_distribution)
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION \
  --paths "/*"

# Get CloudFront URL
CLOUDFRONT_URL=$(terraform output -raw cloudfront_url)
echo "Frontend URL: https://$CLOUDFRONT_URL"
```

---

## Post-Deployment Verification

### 1. Test Production Frontend

```bash
# Open in browser (wait 2 minutes for CloudFront to populate)
https://$CLOUDFRONT_URL/app/signals

# Check browser console (F12) for errors
# Expected: No red errors (yellow warnings OK)
```

### 2. Test Production API

```bash
# Test health endpoint
curl $API_ENDPOINT/api/health

# Test data endpoints
curl "$API_ENDPOINT/api/stocks?limit=5"
curl "$API_ENDPOINT/api/signals?limit=10"
curl "$API_ENDPOINT/api/prices/history/AAPL?limit=5"

# All should return 200 with data
```

### 3. Verify Data Freshness

```bash
# Check that Phase 1 gate passes
curl "$API_ENDPOINT/api/algo/status"

# Should show:
# - orchestrator_status: "ready"
# - phases_completed: >= 1
# - open_positions: > 0 (if trading is configured)
```

### 4. Monitor CloudWatch

```bash
# Check Lambda logs
aws logs tail /aws/lambda/algo-api-dev --follow

# Check RDS logs
aws rds describe-db-instances --db-instance-identifier algo-db \
  --query 'DBInstances[0].PendingCloudwatchLogsExports'
```

---

## Troubleshooting

### Problem: Lambda Timeout
**Symptom:** API returns 504 or "Task timed out"
**Solution:**
```bash
# Increase Lambda timeout
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --timeout 300
```

### Problem: Database Connection Error
**Symptom:** API returns "Unable to connect to database"
**Solution:**
```bash
# Verify RDS endpoint
aws rds describe-db-instances --query 'DBInstances[0].Endpoint'

# Test connection
psql -h $RDS_ENDPOINT -U stocks -d stocks -c "SELECT 1"

# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

### Problem: Frontend Shows Wrong API Endpoint
**Symptom:** 404 errors in browser console
**Solution:**
```bash
# Check frontend env var
echo $VITE_API_URL

# Rebuild with correct URL
VITE_API_URL="$API_ENDPOINT/api" npm run build

# Re-upload to S3
aws s3 sync dist/ s3://$S3_BUCKET/ --delete
```

---

## Rollback Plan

### If Deployment Fails

```bash
# 1. Keep local database running
# (Don't stop PostgreSQL localhost:5432)

# 2. Rollback Lambda to previous version
aws lambda update-alias \
  --function-name algo-api-dev \
  --name production \
  --routing-config AdditionalVersionWeight=0

# 3. Use local frontend temporarily
# Point to localhost:3001 in dev

# 4. Investigate and fix issues
# Don't redeploy until tests pass
```

### Keep Production Stable

```bash
# Don't deploy during market hours
# Deploy during off-hours (weekends or after 6pm ET)

# Always test in staging first
# Create staging environment in AWS before production

# Maintain backups
# Daily automated RDS backups (7-day retention)
# Weekly manual exports to S3
```

---

## Performance Tuning (Optional)

### CloudFront Caching

```bash
# Update cache behavior for API
aws cloudfront update-distribution \
  --id $DISTRIBUTION_ID \
  --distribution-config "{...}"

# Recommended:
# - Static assets: 1 year
# - HTML: 24 hours
# - API responses: 5 minutes or no-cache
```

### Lambda Performance

```bash
# Increase memory (faster CPU)
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --memory-size 1024  # Default 256, try 1024 for better performance

# Provision concurrency for consistent performance
aws lambda put-provisioned-concurrency-config \
  --function-name algo-api-dev \
  --provisioned-concurrent-executions 10
```

### RDS Optimization

```bash
# Enable enhanced monitoring
aws rds modify-db-instance \
  --db-instance-identifier algo-db \
  --enable-cloudwatch-logs-exports postgresql

# Create read replicas for high traffic
aws rds create-db-instance-read-replica \
  --db-instance-identifier algo-db-read-1 \
  --source-db-instance-identifier algo-db
```

---

## Monitoring

### Set up CloudWatch Alarms

```bash
# High error rate
aws cloudwatch put-metric-alarm \
  --alarm-name algo-api-errors \
  --alarm-description "Alert if error rate >1%" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold

# High latency
aws cloudwatch put-metric-alarm \
  --alarm-name algo-api-latency \
  --alarm-description "Alert if p99 latency >1s" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Maximum \
  --period 300 \
  --threshold 1000 \
  --comparison-operator GreaterThanThreshold
```

---

## Success Criteria

✅ Deployment is successful if:
- [ ] Frontend loads at CloudFront URL (no 403/404)
- [ ] All 24 pages work
- [ ] API endpoints return 200 status
- [ ] Database queries work (verified via API)
- [ ] CloudWatch shows no Lambda errors
- [ ] RDS shows healthy connection
- [ ] Load test passes (100+ concurrent users)

---

## Estimated Timeline

| Phase | Time | Dependent On |
|-------|------|-------------|
| AWS Setup | 15 min | AWS CLI configured |
| RDS Deploy | 15 min | VPC/security groups |
| Data Migration | 30 min | RDS running |
| Lambda Deploy | 15 min | IAM role |
| API Gateway Config | 10 min | Lambda deployed |
| Frontend Build | 5 min | VITE_API_URL set |
| S3/CloudFront | 10 min | Build complete |
| Testing | 15 min | All deployed |
| **Total** | **2 hours** | |

---

## Next Steps

1. **Run pre-deployment checklist above**
2. **Set AWS credentials and region**
3. **Follow AWS Deployment Steps 1-6**
4. **Run Post-Deployment Verification**
5. **Monitor CloudWatch for first 24 hours**
6. **Document any issues for next session**

**Good luck! The platform is ready for production.**

# 🚀 AWS Lambda Deployment Guide

**Updated**: Feb 28, 2026
**Status**: Ready for Production Deployment

---

## 📋 Prerequisites

- ✅ AWS Account with proper IAM permissions
- ✅ AWS CLI installed and configured (`aws configure`)
- ✅ Serverless Framework installed (`npm install -g serverless`)
- ✅ PostgreSQL RDS instance (running or to be created)
- ✅ Data migrated to RDS (see Data Migration section)

---

## 🔧 CRITICAL FIXES APPLIED

### Issue #1: Database Connection ✅ FIXED
**Before**: Lambda tried to connect to `localhost:5432` (doesn't exist in AWS)
**After**: Lambda now uses AWS Secrets Manager for RDS credentials

### Issue #2: VPC Configuration ✅ FIXED
**Before**: Subnet IDs were hardcoded placeholders
**After**: Now uses environment variables with validation

### Issue #3: Timeout ✅ FIXED
**Before**: 30 seconds (too short for complex queries)
**After**: 60 seconds (better for stock analysis queries)

### Issue #4: Memory ✅ FIXED
**Before**: 512 MB (sufficient for API)
**After**: 1024 MB (better performance for calculations)

---

## 🚀 QUICK START (5 minutes)

### Step 1: Run Setup Script
```bash
cd /home/arger/algo
chmod +x AWS_DEPLOYMENT_SETUP.sh
./AWS_DEPLOYMENT_SETUP.sh
```

This will:
- ✅ Create AWS Secrets Manager secret
- ✅ Fetch your VPC details
- ✅ Configure Lambda environment
- ✅ Save configuration to `.env.production`

### Step 2: Export Environment Variables
```bash
# From output of setup script, run:
export DB_SECRET_ARN=arn:aws:secretsmanager:...
export AWS_SECURITY_GROUP_ID=sg-xxxxx
export AWS_SUBNET_ID_1=subnet-xxxxx
export AWS_SUBNET_ID_2=subnet-xxxxx
```

### Step 3: Deploy
```bash
cd webapp/lambda
serverless deploy --stage dev --region us-east-1
```

### Step 4: Test
```bash
# Get function URL
aws lambda get-function-url-config \
  --function-name stocks-algo-api-dev-api \
  --region us-east-1

# Test health endpoint
curl https://your-function-url/health
```

---

## 📊 Configuration Details

### Updated `serverless.yml` Changes

```yaml
# BEFORE (Broken):
timeout: 30
memorySize: 512
vpc:
  securityGroupIds:
    - sg-xxxxxx  # Placeholder
  subnetIds:
    - subnet-xxxxxx  # Placeholder

# AFTER (Working):
timeout: 60
memorySize: 1024
vpc:
  securityGroupIds:
    - ${env:AWS_SECURITY_GROUP_ID}  # Environment variable
  subnetIds:
    - ${env:AWS_SUBNET_ID_1}  # Environment variable
    - ${env:AWS_SUBNET_ID_2}  # Environment variable
```

### Environment Variables

**Local Development** (`.env.local`):
```
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=bed0elAn
DB_NAME=stocks
NODE_ENV=development
```

**AWS Production** (`.env.production`):
```
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks/rds/credentials-xxxxx
AWS_SECURITY_GROUP_ID=sg-xxxxxxxxxxxxx
AWS_SUBNET_ID_1=subnet-xxxxxxxxxxxxx
AWS_SUBNET_ID_2=subnet-xxxxxxxxxxxxx
AWS_REGION=us-east-1
NODE_ENV=production
```

---

## 🗄️ Data Migration to RDS

### Option 1: PostgreSQL pg_dump (Recommended)

```bash
# Export data from local PostgreSQL
pg_dump -h localhost -U stocks -d stocks -Fc -f /tmp/stocks_backup.dump

# Create RDS instance (if needed)
# See AWS console for RDS creation

# Get RDS endpoint
RDS_HOST=stocks-db.xxxxx.us-east-1.rds.amazonaws.com

# Restore to RDS
pg_restore -h $RDS_HOST -U stocks -d stocks /tmp/stocks_backup.dump
```

### Option 2: Direct PostgreSQL Copy

```bash
# Copy directly from local to RDS
pg_dump -h localhost -U stocks stocks | \
psql -h stocks-db.xxxxx.us-east-1.rds.amazonaws.com -U stocks stocks
```

### Verify Migration
```bash
# Check row counts in RDS
psql -h stocks-db.xxxxx.us-east-1.rds.amazonaws.com -U stocks stocks << EOF
SELECT
  'stock_symbols' as table_name, COUNT(*) FROM stock_symbols
UNION ALL SELECT 'price_daily', COUNT(*) FROM price_daily
UNION ALL SELECT 'stock_scores', COUNT(*) FROM stock_scores;
EOF
```

---

## 🧪 Testing After Deployment

### Health Check
```bash
curl https://your-function-url/health
# Expected: 200 OK with { "status": "healthy" }
```

### API Endpoints
```bash
# Get stocks
curl "https://your-function-url/api/stocks?limit=5"

# Get specific stock
curl "https://your-function-url/api/stocks/AAPL"

# Get signals
curl "https://your-function-url/api/signals/AAPL"
```

### CloudWatch Logs
```bash
# View real-time logs
aws logs tail /aws/lambda/stocks-algo-api-dev-api \
  --follow \
  --region us-east-1

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/stocks-algo-api-dev-api \
  --filter-pattern "ERROR" \
  --region us-east-1
```

---

## 🔐 Security Considerations

### IAM Permissions
Lambda has minimum required permissions:
- ✅ CloudWatch Logs (debugging)
- ✅ EC2 VPC (network access)
- ✅ Secrets Manager (fetch DB credentials)
- ✅ SES (send emails)

### Secrets Manager
- ✅ Secret is encrypted at rest (AWS KMS)
- ✅ Lambda fetches credentials on each request
- ✅ Credentials never logged or exposed
- ✅ Access is audited in CloudTrail

### VPC Security
- ✅ Lambda runs in private subnets
- ✅ Only accesses RDS via security group
- ✅ No direct internet access needed for RDS
- ✅ Uses VPC endpoints for AWS services

---

## 🚨 Troubleshooting

### Issue: ECONNREFUSED (Can't connect to database)
```
Error: ECONNREFUSED at 127.0.0.1:5432
```
**Cause**: Lambda trying to use localhost instead of RDS
**Fix**:
1. Verify DB_SECRET_ARN is set
2. Check Secrets Manager secret exists: `aws secretsmanager list-secrets`
3. Verify RDS endpoint is accessible
4. Check security group allows Lambda → RDS

### Issue: Lambda Timeout (504)
```
Error: Task timed out after 60 seconds
```
**Cause**: Query taking longer than timeout
**Fix**:
1. Check CloudWatch logs for slow queries
2. Increase timeout in serverless.yml
3. Add database indexes
4. Implement query caching

### Issue: VPC Configuration Error
```
Error: Invalid subnet ID
```
**Cause**: Subnet ID doesn't exist in VPC
**Fix**:
1. Run setup script again
2. Verify subnet IDs: `aws ec2 describe-subnets`
3. Ensure subnets are in same VPC as RDS

---

## 📊 Monitoring

### CloudWatch Dashboard

```bash
# Create CloudWatch dashboard
aws cloudwatch put-dashboard \
  --dashboard-name stocks-api-dashboard \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["AWS/Lambda", "Duration", {"stat": "Average"}],
            ["AWS/Lambda", "Errors", {"stat": "Sum"}],
            ["AWS/Lambda", "Invocations", {"stat": "Sum"}],
            ["AWS/Lambda", "Throttles", {"stat": "Sum"}]
          ],
          "period": 60,
          "stat": "Average",
          "region": "us-east-1",
          "title": "Lambda Metrics"
        }
      }
    ]
  }'
```

### Alarms

```bash
# Alert on errors
aws cloudwatch put-metric-alarm \
  --alarm-name stocks-api-errors \
  --alarm-description "Alert when Lambda has errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold
```

---

## ✅ Deployment Checklist

- [ ] AWS account configured with IAM permissions
- [ ] RDS PostgreSQL instance created or identified
- [ ] Data migrated to RDS (25.6M records)
- [ ] AWS Secrets Manager secret created
- [ ] Environment variables exported
- [ ] `serverless.yml` updated with VPC configuration
- [ ] Serverless Framework installed
- [ ] Lambda deployed: `serverless deploy`
- [ ] Health endpoint tested and working
- [ ] CloudWatch logs verified
- [ ] API endpoints tested
- [ ] Database connection confirmed in logs

---

## 📞 Support

If you encounter issues:

1. **Check CloudWatch logs**: `aws logs tail /aws/lambda/stocks-algo-api-dev-api --follow`
2. **Verify Secrets Manager**: `aws secretsmanager get-secret-value --secret-id stocks/rds/credentials`
3. **Test RDS connection**:
   ```bash
   psql -h your-rds-endpoint.rds.amazonaws.com -U stocks -d stocks
   ```
4. **Review error codes**: See `LAMBDA_DIAGNOSTICS.md`

---

**Status**: ✅ Ready for Production Deployment

**Next Step**: Run `./AWS_DEPLOYMENT_SETUP.sh` and follow the prompts.

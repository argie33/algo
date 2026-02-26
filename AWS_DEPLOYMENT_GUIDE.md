# 🚀 AWS DEPLOYMENT GUIDE - STOCK PLATFORM

## Current Status
- ✅ All data loaded locally (32.4M records)
- ✅ All APIs tested and working
- ✅ Code pushed to GitHub
- ✅ Database backed up
- ⏳ Ready for AWS deployment

## Prerequisites
```bash
# Install AWS CLI
aws --version

# Configure AWS credentials
aws configure

# Install PostgreSQL client
psql --version
```

## Step 1: Get RDS Endpoint

### Option A: From AWS Console
1. Go to RDS → Databases
2. Find your "stocks" database
3. Copy the Endpoint (e.g., `stocks.xxxxx.us-east-1.rds.amazonaws.com`)

### Option B: Using AWS CLI
```bash
aws rds describe-db-instances \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text
```

Save this as `RDS_ENDPOINT`

## Step 2: Check RDS Security Group

```bash
# Allow inbound PostgreSQL (5432) from your IP
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --protocol tcp \
  --port 5432 \
  --cidr YOUR_IP/32
```

## Step 3: Restore Database to AWS RDS

### Option A: Direct Restore (Slow for 32GB)
```bash
# Using compressed backup
gunzip -c /tmp/stocks_backup_latest.sql.gz | \
  psql -h $RDS_ENDPOINT \
       -U stocks \
       -d stocks \
       -v ON_ERROR_STOP=1

# Or uncompressed (faster for large files)
psql -h $RDS_ENDPOINT \
     -U stocks \
     -d stocks \
     -f /tmp/stocks_backup_latest.sql
```

### Option B: Using S3 (Faster - Recommended)
```bash
# 1. Upload to S3
aws s3 cp /tmp/stocks_backup_latest.sql.gz \
  s3://your-bucket/database-backups/

# 2. Create IAM role for RDS to access S3
aws iam create-role \
  --role-name rds-s3-access \
  --assume-role-policy-document file://trust-policy.json

# 3. Use RDS import feature (if supported)
```

### Option C: Using AWS DMS (Data Migration Service)
```bash
# Create DMS task to migrate from local to RDS
# This is the most reliable for large datasets
```

## Step 4: Verify Data on RDS

```bash
# Connect to RDS
psql -h $RDS_ENDPOINT -U stocks -d stocks

# Count records on each table
SELECT tablename, (SELECT COUNT(*) FROM tablename) as count 
FROM pg_tables WHERE schemaname='public' ORDER BY tablename;

# Expected results (should match local counts):
# stock_symbols: 4,988
# price_daily: 22,451,317
# stock_scores: 4,988
# etc.
```

## Step 5: Update Lambda Environment Variables

```bash
# Get RDS secret ARN
aws secretsmanager describe-secret \
  --secret-id stocks-db-secret \
  --query 'ARN' \
  --output text

# Update Lambda environment variable
aws lambda update-function-configuration \
  --function-name stocks-webapp-function \
  --environment Variables={DB_SECRET_ARN=arn:aws:...,DB_ENDPOINT=$RDS_ENDPOINT}
```

## Step 6: Test Lambda Connection

```bash
# Invoke Lambda test
aws lambda invoke \
  --function-name stocks-webapp-function \
  --payload '{"path":"/api/health"}' \
  /tmp/lambda-test.json

# Check response
cat /tmp/lambda-test.json
```

## Step 7: Deploy Frontend

```bash
# Build frontend
cd webapp/frontend
npm run build

# Deploy to S3 + CloudFront
aws s3 sync dist/ s3://your-bucket-frontend/
aws cloudfront create-invalidation \
  --distribution-id E1234567890ABC \
  --paths "/*"
```

## Step 8: Monitor and Verify

### Check CloudWatch Logs
```bash
aws logs tail /aws/lambda/stocks-webapp-function --follow
```

### Test API Endpoints
```bash
# Get CloudFront URL
aws cloudfront list-distributions \
  --query 'DistributionList.Items[0].DomainName'

# Test endpoint
curl https://d1234567890.cloudfront.net/api/stocks?limit=5
curl https://d1234567890.cloudfront.net/api/health
```

### Monitor Performance
```bash
# CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=stocks-webapp-function \
  --start-time 2026-02-26T00:00:00Z \
  --end-time 2026-02-27T00:00:00Z \
  --period 300 \
  --statistics Average,Maximum
```

## Troubleshooting

### Database Connection Fails
```bash
# 1. Check security group
aws ec2 describe-security-groups --group-ids sg-xxx

# 2. Test connectivity
nc -zv $RDS_ENDPOINT 5432

# 3. Check RDS password in Secrets Manager
aws secretsmanager get-secret-value --secret-id stocks-db-secret
```

### Lambda Can't Find Tables
```bash
# 1. Verify data on RDS
psql -h $RDS_ENDPOINT -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols"

# 2. Check Lambda has correct DB_SECRET_ARN
aws lambda get-function-configuration \
  --function-name stocks-webapp-function

# 3. Restart Lambda (deploy empty change)
aws lambda update-function-code \
  --function-name stocks-webapp-function \
  --s3-bucket your-bucket --s3-key code.zip
```

### Slow Queries
```bash
# Add indexes for frequently queried columns
psql -h $RDS_ENDPOINT -U stocks -d stocks << SQL
CREATE INDEX idx_stock_symbols_symbol ON stock_symbols(symbol);
CREATE INDEX idx_price_daily_symbol_date ON price_daily(symbol, date DESC);
CREATE INDEX idx_stock_scores_symbol ON stock_scores(symbol);
SQL
```

## Performance Optimization

### RDS Parameter Group
```bash
# Set parameters for better performance
aws rds modify-db-parameter-group \
  --db-parameter-group-name stocks-pg \
  --parameters "ParameterName=shared_buffers,ParameterValue=262144,ApplyMethod=immediate"
```

### Connection Pooling
The Lambda already has connection pooling configured (10 max connections).

### Caching Strategy
- CloudFront caches static assets
- Lambda caches database connections
- Consider ElastiCache for frequently accessed data

## Cost Estimation

- **RDS PostgreSQL:** ~$50-150/month (db.t3.small)
- **Lambda:** ~$1-10/month (pay per request)
- **CloudFront:** ~$0.085/GB (depending on traffic)
- **S3:** ~$0.023/GB (storage)
- **Total:** ~$100-300/month for production

## Monitoring Checklist

- [ ] RDS backup automated (daily)
- [ ] CloudWatch alarms set up
- [ ] Error rate monitoring enabled
- [ ] Database query logging enabled
- [ ] API response time monitored
- [ ] Cost alerts configured

## Rollback Plan

If issues occur:
```bash
# 1. Rollback Lambda to previous version
aws lambda update-alias \
  --function-name stocks-webapp-function \
  --name live \
  --function-version PREVIOUS_VERSION

# 2. Restore RDS from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier stocks-db-restored \
  --db-snapshot-identifier stocks-snapshot

# 3. Update endpoint in Secrets Manager
aws secretsmanager update-secret \
  --secret-id stocks-db-secret \
  --secret-string '{"host":"new-endpoint"...}'
```

## Support Resources

- AWS RDS Documentation: https://docs.aws.amazon.com/rds/
- AWS Lambda Documentation: https://docs.aws.amazon.com/lambda/
- PostgreSQL Documentation: https://www.postgresql.org/docs/
- GitHub Actions CI/CD: https://docs.github.com/actions

---

**Last Updated:** 2026-02-26
**Data Size:** 32.4M records (~3.5GB)
**Estimated Deployment Time:** 30-60 minutes

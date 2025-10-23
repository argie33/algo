# AWS Deployment - Quick Start Checklist

## ✅ Pre-Deployment Verification (Do This First)

```bash
# 1. Verify AWS credentials and permissions
aws sts get-caller-identity

# Expected output:
# {
#     "UserId": "AIDAXXXXXXXXXXXXXXXX",
#     "Account": "626216981288",
#     "Arn": "arn:aws:iam::626216981288:user/YOUR_USERNAME"
# }

# ⚠️ If username is "reader", you need elevated permissions!

# 2. Verify database dump exists
ls -lh /tmp/stocks_database.sql
# Expected: 13G

# 3. Verify deployment scripts
ls -l /home/stocks/algo/deploy-to-aws.sh
ls -l /home/stocks/algo/AWS_DEPLOYMENT_GUIDE.md

# 4. Verify frontend builds
cd /home/stocks/algo/webapp/frontend
npm run build  # Should create dist/ folder
```

## 🚀 Automated Deployment (Once Permissions Are Granted)

### Step 1: Run the deployment script (10 minutes)
```bash
bash /home/stocks/algo/deploy-to-aws.sh
```

The script will:
- ✅ Verify AWS permissions
- ✅ Create RDS PostgreSQL instance (10-15 min wait)
- ✅ Create S3 buckets
- ✅ Upload database dump
- ✅ Build frontend
- ✅ Deploy frontend to S3

### Step 2: Restore database manually (30+ minutes)

The script will prompt you with instructions. Follow this:

```bash
# Get RDS endpoint from AWS console or CLI:
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

echo $RDS_ENDPOINT  # Write this down

# Create stocks database:
psql -h $RDS_ENDPOINT -U postgres -d postgres -c "CREATE DATABASE stocks;"

# Restore the full dump (this takes 30-60 minutes):
psql -h $RDS_ENDPOINT -U postgres -d stocks < /tmp/stocks_database.sql

# Verify the restore worked:
psql -h $RDS_ENDPOINT -U postgres -d stocks -c "SELECT COUNT(*) FROM company_profile;"
# Should return: 1098 rows
```

### Step 3: Deploy backend to Lambda (5 minutes)

```bash
# Install serverless framework if not already installed
npm install -g serverless

# Navigate to lambda directory
cd /home/stocks/algo/webapp/lambda

# Set environment variables for RDS
export DB_HOST=$RDS_ENDPOINT
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=YOUR_RDS_PASSWORD
export DB_NAME=stocks

# Deploy to AWS Lambda
serverless deploy --region us-east-1

# Note the API Gateway endpoint in the output
# It will look like: https://abc123xyz.execute-api.us-east-1.amazonaws.com
```

### Step 4: Update frontend API URL (2 minutes)

```bash
cd /home/stocks/algo/webapp/frontend

# Create .env.production file
cat > .env.production << EOF
VITE_API_URL=https://your-api-endpoint/api
EOF

# Rebuild frontend
npm run build

# Deploy updated frontend
aws s3 sync dist/ s3://stocks-algo-frontend-TIMESTAMP/ --delete
```

### Step 5: Test Everything (10 minutes)

```bash
# Test backend endpoints
API_URL="https://your-api-endpoint/api"

# Test sectors endpoint
curl $API_URL/sectors/sectors-with-history?limit=2
# Should return 2 sectors with performance_1d, performance_5d, performance_20d

# Test industries endpoint
curl $API_URL/sectors/industries-with-history?limit=5
# Should return 5 industries with performance metrics

# Test market endpoint
curl $API_URL/market/overview
# Should return market data

# Test frontend
# Open in browser: https://your-cloudfront-url
# Verify:
# ✓ All 145 industries load
# ✓ Charts display correctly
# ✓ Performance metrics show real values
# ✓ No console errors
```

## 📊 Post-Deployment Verification

### Verify Database
```bash
# Connect to AWS database
psql -h $RDS_ENDPOINT -U postgres -d stocks

# Check table row counts
SELECT count(*) FROM company_profile;     -- Should be 1098
SELECT count(*) FROM sector_ranking;      -- Should have data
SELECT count(*) FROM industry_ranking;    -- Should have data
SELECT count(DISTINCT sector) FROM company_profile;  -- Should be 11
SELECT count(DISTINCT industry) FROM company_profile; -- Should be 146
```

### Verify All Data Loaded
```bash
# Check if all industries are present
psql -h $RDS_ENDPOINT -U postgres -d stocks \
  -c "SELECT COUNT(DISTINCT industry) FROM company_profile WHERE industry IS NOT NULL;"
# Should return: 146

# Check if performance data exists
psql -h $RDS_ENDPOINT -U postgres -d stocks \
  -c "SELECT COUNT(*) FROM sector_ranking;"
# Should return: > 0
```

### Verify API Responses
```bash
# Check API response times
time curl $API_URL/sectors/sectors-with-history

# Check error rates
curl -i $API_URL/sectors/sectors-with-history | head -1
# Should return: HTTP/1.1 200 OK

# Check industries count
curl $API_URL/sectors/industries-with-history | grep -o '"industry"' | wc -l
# Should return: 145
```

## 🎯 Deployment Status Tracking

| Step | Status | Time | Command |
|------|--------|------|---------|
| Verify Permissions | ⏳ | 1 min | `aws sts get-caller-identity` |
| Create RDS | ⏳ | 15 min | `bash deploy-to-aws.sh` |
| Restore Database | ⏳ | 60 min | `psql -h $RDS_ENDPOINT ...` |
| Deploy Backend | ⏳ | 5 min | `serverless deploy` |
| Deploy Frontend | ⏳ | 5 min | `aws s3 sync dist/ s3://...` |
| Test Everything | ⏳ | 10 min | `curl $API_URL/...` |
| **TOTAL** | **⏳** | **~100 min** | - |

## ❌ Troubleshooting

### Problem: "Access Denied" errors
**Solution**: You still have reader-only permissions. Request elevation.

### Problem: Database restore is slow
**Solution**: This is normal for 13GB. Estimated time: 30-60 minutes. Be patient.

### Problem: RDS endpoint not found
**Solution**: Check RDS instance is fully available:
```bash
aws rds describe-db-instances --db-instance-identifier stocks-db \
  --query 'DBInstances[0].DBInstanceStatus'
# Should return: "available"
```

### Problem: API returns 502 Bad Gateway
**Solution**: Verify RDS connection:
```bash
# Check environment variables are set in Lambda
aws lambda get-function-configuration \
  --function-name stocks-algo-api \
  --query 'Environment.Variables'
```

### Problem: Frontend shows "Cannot reach API"
**Solution**: Verify API URL is correct:
```bash
# Check frontend .env.production
cat /home/stocks/algo/webapp/frontend/.env.production
# Should have: VITE_API_URL=https://your-api-endpoint/api
```

## 📱 URLs After Deployment

```
Frontend URL (S3 + CloudFront):
https://your-cloudfront-domain.cloudfront.net

Backend API URL (Lambda / API Gateway):
https://api-id.execute-api.us-east-1.amazonaws.com/api

Database Connection (RDS):
psql -h your-rds-endpoint.rds.amazonaws.com -U postgres -d stocks
```

## 💰 Monitor Costs

```bash
# Check AWS costs (requires permissions)
aws ce get-cost-and-usage \
  --time-period Start=2025-10-01,End=2025-10-31 \
  --granularity MONTHLY \
  --metrics "BlendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE

# Or use AWS Console: https://console.aws.amazon.com/cost-management
```

## ✅ Final Verification Checklist

- [ ] RDS instance is running and accessible
- [ ] Database restored successfully (1098 companies)
- [ ] All 11 sectors present in data
- [ ] All 146 industries present in data
- [ ] API Gateway / Lambda deployed and responding
- [ ] Frontend deployed to S3 and accessible via CloudFront
- [ ] All endpoints returning correct data
- [ ] Performance metrics show realistic values
- [ ] Frontend loads all 145 industries
- [ ] Charts and visualizations display correctly
- [ ] No console errors in browser
- [ ] Response times are < 500ms
- [ ] Cost monitoring is set up

## 🎉 Success Indicators

You'll know everything is working when:

1. **Frontend loads instantly** (< 2 seconds)
2. **All 145 industries appear** in the dropdown
3. **Performance metrics show real values** (e.g., -1.27%, +2.34%)
4. **Trend charts display** for all sectors and industries
5. **API responds in < 500ms** for all endpoints
6. **No 502/503 errors** from API Gateway
7. **Database queries complete in < 200ms**
8. **All 1098 companies loaded** in database

---

**Total Deployment Time**: ~100 minutes (mostly waiting for RDS and database restore)

**Ready to deploy?** Start with Step 1 of Automated Deployment! 🚀

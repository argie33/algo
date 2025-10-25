# AWS Deployment Guide - Stocks Analysis Platform

## Overview
This guide details the deployment of the Sentiment Analysis Platform to AWS. Current status shows the infrastructure is ready (RDS instance exists), but requires IAM permissions to complete the deployment.

## AWS Infrastructure Status

### ✓ Existing Resources
- **AWS Account**: 626216981288
- **Region**: us-east-1
- **RDS Database**: `stocks` (PostgreSQL 17.4)
  - **Endpoint**: `stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com:5432`
  - **Status**: available
  - **Instance Class**: db.t3.micro
  - **Storage**: 100GB
- **S3 Buckets**:
  - `stocks-webapp-frontend-dev-626216981288` (existing frontend bucket)
  - `stocks-webapp-frontend-code-626216981288` (code bucket)

### Current User Permissions
- **IAM User**: `reader` (restricted read-only role)
- **Available Actions**: Describe, List, Get operations
- **Restricted Actions**:
  - S3: PutObject, DeleteObject (need elevated privileges)
  - RDS: Modify, Create instances (need admin)
  - Lambda: CreateFunction, UpdateFunctionCode (need admin)

## Deployment Status

✓ **Completed**:
- Frontend built for production (14.5 MB)
- AWS credentials configured
- RDS instance running and accessible
- S3 buckets available
- Backend API tested locally on port 3002

⏳ **Pending** (Require Admin Privileges):
- Load sentiment data to AWS RDS
- Deploy backend to Lambda
- Configure API Gateway
- Upload frontend to S3
- Set up CORS policies

## Phase 1: Data Loading (Admin Only)

### Export Data from Local PostgreSQL

```bash
# Export schema
pg_dump -h localhost -U postgres -d stocks --schema-only \
  > /tmp/stocks_schema.sql

# Export sentiment and analyst data
pg_dump -h localhost -U postgres -d stocks \
  --table=analyst_sentiment_analysis \
  --table=social_sentiment_analysis \
  --table=sentiment_scores \
  --table=analyst_upgrade_downgrade \
  --table=analyst_estimates \
  --table=analyst_price_targets \
  --table=analyst_recommendations \
  --table=analyst_coverage \
  > /tmp/sentiment_data.sql

# Export all other stock data tables
pg_dump -h localhost -U postgres -d stocks \
  --exclude-table-data="*_daily" \
  > /tmp/all_schema.sql
```

### RDS Setup Commands

```bash
# First, modify RDS security group to allow your IP on port 5432

# Create database
PGPASSWORD="<admin_password>" psql \
  -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U postgres -d postgres \
  -c "CREATE DATABASE IF NOT EXISTS stocks;"

# Load schema
PGPASSWORD="<admin_password>" psql \
  -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U postgres -d stocks \
  -f /tmp/all_schema.sql

# Load sentiment data
PGPASSWORD="<admin_password>" psql \
  -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U postgres -d stocks \
  -f /tmp/sentiment_data.sql

# Verify
PGPASSWORD="<admin_password>" psql \
  -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com \
  -U postgres -d stocks -c \
  "SELECT COUNT(*) FROM analyst_sentiment_analysis;"
```

## Phase 2: Lambda Deployment (Admin Only)

### Prepare Function Package

```bash
cd /home/stocks/algo/webapp/lambda
npm install --production
zip -r /tmp/lambda-function.zip . -x "*.git*" "node_modules/aws-sdk/*"

# Upload and create function (requires admin)
aws lambda create-function \
  --function-name stocks-sentiment-api \
  --role arn:aws:iam::626216981288:role/lambda-execution-role \
  --handler server.handler \
  --runtime nodejs20.x \
  --zip-file fileb:///tmp/lambda-function.zip \
  --timeout 30 \
  --memory-size 512 \
  --environment Variables="{
    AWS_RDS_ENDPOINT=stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com,
    AWS_RDS_USER=postgres,
    AWS_RDS_PASSWORD=<password>,
    AWS_RDS_DATABASE=stocks,
    NODE_ENV=production
  }" \
  --region us-east-1
```

## Phase 3: API Gateway Setup (Admin Only)

```bash
# Create REST API
AWS_API_ID=$(aws apigateway create-rest-api \
  --name "stocks-sentiment-api" \
  --description "Sentiment analysis API" \
  --endpoint-configuration '{"types":["REGIONAL"]}' \
  --query 'id' --output text)

echo "API ID: $AWS_API_ID"

# Create deployment
aws apigateway create-deployment \
  --rest-api-id $AWS_API_ID \
  --stage-name prod

# Get endpoint
echo "API Endpoint: https://${AWS_API_ID}.execute-api.us-east-1.amazonaws.com/prod"
```

## Phase 4: Frontend Deployment to S3 (Admin Only)

```bash
# With elevated privileges
aws s3 sync /home/stocks/algo/webapp/frontend/dist/ \
  s3://stocks-webapp-frontend-dev-626216981288/ \
  --delete

# Enable static website
aws s3 website s3://stocks-webapp-frontend-dev-626216981288/ \
  --index-document index.html \
  --error-document index.html

# Set CORS
aws s3api put-bucket-cors \
  --bucket stocks-webapp-frontend-dev-626216981288 \
  --cors-configuration '{
    "CORSRules": [{
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "POST"],
      "AllowedOrigins": ["*"],
      "MaxAgeSeconds": 3000
    }]
  }'
```

## Local Testing (Can Do Now)

### Backend API

```bash
# Terminal 1: Start backend
cd /home/stocks/algo/webapp/lambda
PORT=3002 node server.js

# Terminal 2: Test endpoints
curl http://localhost:3002/api/sentiment/stocks
curl http://localhost:3002/api/sentiment/analyst/insights/AAPL
curl http://localhost:3002/api/analysts/AAPL/eps-revisions
curl http://localhost:3002/api/analysts/AAPL/sentiment-trend
curl http://localhost:3002/api/analysts/AAPL/analyst-momentum
```

### Frontend

```bash
cd /home/stocks/algo/webapp/frontend
npm run dev
# Open http://localhost:5174
```

## AWS Infrastructure Details

### RDS Instance

```
Name: stocks
Endpoint: stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com
Port: 5432
Engine: PostgreSQL 17.4
Instance Class: db.t3.micro
Storage: 100GB (gp2)
Multi-AZ: No
Public Access: Yes (but security group restricted)
VPC: vpc-01bac8b5a4479dad9
```

### S3 Buckets Available

```
1. stocks-webapp-frontend-dev-626216981288
   - Current: Old frontend build
   - Will: Deployment target for new frontend
   - Type: Static website hosting

2. stocks-webapp-frontend-code-626216981288
   - Type: Code/backup bucket
```

## API Endpoints (After Deployment)

```
GET  /api/sentiment/stocks
GET  /api/sentiment/analyst/insights/:symbol
GET  /api/analysts/:symbol/eps-revisions
GET  /api/analysts/:symbol/sentiment-trend
GET  /api/analysts/:symbol/analyst-momentum
GET  /health
```

## Environment Files

### Backend (.env)

```
AWS_RDS_ENDPOINT=stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com
AWS_RDS_USER=postgres
AWS_RDS_PASSWORD=<secure_password>
AWS_RDS_DATABASE=stocks
NODE_ENV=production
PORT=3001
CORS_ORIGIN=https://stocks-webapp-frontend-dev-626216981288.s3-website-us-east-1.amazonaws.com
```

### Frontend (.env.production)

```
VITE_API_BASE=https://<api-id>.execute-api.us-east-1.amazonaws.com/prod
VITE_ENV=production
```

## Troubleshooting

### Cannot Create Lambda Function
- **Error**: "User is not authorized to perform: lambda:CreateFunction"
- **Solution**: Request elevated IAM privileges (need lambda:CreateFunction, lambda:UpdateFunction)

### Cannot Upload to S3
- **Error**: "User: arn:aws:iam::626216981288:user/reader is not authorized"
- **Solution**: Request S3 write permissions or ask admin to upload

### RDS Connection Refused
- **Error**: "no pg_hba.conf entry for host"
- **Solution**: Modify RDS security group to allow your IP on port 5432

### API Gateway CORS Issues
- **Error**: "Access to XMLHttpRequest blocked by CORS policy"
- **Solution**: Configure CORS on API Gateway and S3

## Files Generated

```
/home/stocks/algo/deploy-to-aws-complete.sh
  - Automated deployment script (needs admin)

/home/stocks/algo/sync_data_to_aws.py
  - Python script for incremental data sync

/home/stocks/algo/AWS_DEPLOYMENT_GUIDE.md
  - This file: comprehensive deployment guide

/home/stocks/algo/webapp/frontend/dist/
  - Production frontend build ready to upload

/tmp/stocks_schema_*.sql
  - Database schema exports

/tmp/sentiment_data_*.sql
  - Sentiment and analyst data exports
```

## Next Steps

1. **Contact AWS Admin** - Request:
   - Elevated IAM privileges for this user
   - Modify RDS security group for your IP
   - Configure S3 bucket write access
   - Set up Lambda execution role

2. **After Admin Setup**:
   - Run data loading commands
   - Execute Lambda deployment
   - Configure API Gateway
   - Upload frontend to S3

3. **Testing**:
   - Test API endpoints
   - Verify frontend loads
   - Check sentiment data displays
   - Test analyst metrics display

4. **Production Hardening**:
   - Change default RDS password
   - Configure SSL/TLS certificates
   - Set up CloudFront distribution
   - Enable CloudWatch monitoring
   - Configure API Gateway authentication

---

**Created**: 2025-10-25
**Status**: Waiting for admin-level permissions
**Tested Components**: Backend API (local), Frontend build (local)
**Ready to Deploy**: Yes, once admin privileges granted

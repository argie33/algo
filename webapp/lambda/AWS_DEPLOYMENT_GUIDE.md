# AWS Deployment Guide - Stocks API

## Overview
This guide explains how to deploy the Stock Analysis API to AWS Lambda with API Gateway routing to a PostgreSQL database (RDS or local).

## Problem: 404 API Errors

The current issue is that all API endpoints return **404 HTML errors** instead of JSON responses. This indicates **API Gateway routing is not configured correctly**.

### Root Causes
1. **VPC Configuration**: serverless.yml has placeholder values for security groups/subnets
2. **Environment Variables**: `.env` file points to localhost, not AWS RDS
3. **API Gateway**: HTTP API may not be properly routing `/{proxy+}` requests to Lambda

## Solution Path

### Step 1: Configure Database Connection

You have two options:

#### Option A: Use AWS RDS (Recommended for Production)
```bash
# Create/configure an RDS PostgreSQL instance
# In AWS Console:
# 1. RDS Dashboard → Create Database
# 2. PostgreSQL, DB instance identifier: stocks-db
# 3. Master username: postgres
# 4. Auto-generate password (store in AWS Secrets Manager)
# 5. VPC: Same as where Lambda will run
# 6. Public access: No (use VPC security group)
# 7. Database name: stocks

# Then set environment variables:
export DB_HOST="stocks-db.xxxxxx.rds.amazonaws.com"  # RDS endpoint
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="<your-secure-password>"
export DB_NAME="stocks"
export AWS_REGION="us-east-1"
```

#### Option B: Use Local PostgreSQL (Development)
```bash
# If running Lambda locally or with local database
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="password"
export DB_NAME="stocks"
```

### Step 2: Deploy with Serverless Framework

```bash
# Install dependencies
npm install

# Deploy to AWS (using environment variables)
serverless deploy \
  --param="dbHost=$DB_HOST" \
  --param="dbPort=$DB_PORT" \
  --param="dbUser=$DB_USER" \
  --param="dbPassword=$DB_PASSWORD" \
  --param="dbName=$DB_NAME" \
  --region $AWS_REGION \
  --stage dev

# OR with environment file
export AWS_PROFILE=default  # Your AWS credentials profile
serverless deploy --region us-east-1 --stage dev
```

### Step 3: Verify API Gateway Configuration

In AWS Console:

1. **API Gateway → APIs → stocks-algo-api**
2. **Verify Resource Structure**:
   ```
   / (root)
   └── {proxy+} (catchall for all paths)
   ```
3. **Check Method Configuration**:
   - Method: `ANY`
   - Integration Type: `Lambda`
   - Lambda Function: `stocks-algo-api-dev-api`
   - Payload Format Version: `2.0`

4. **Test Route** (in API Gateway Console):
   - Test `GET /api/sectors`
   - Should return JSON response from Lambda

### Step 4: Deploy Data Loaders to AWS

Data loaders must run against the AWS database:

```bash
# Export AWS database variables
export DB_HOST="your-rds-endpoint.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="your-password"
export DB_NAME="stocks"

# Option 1: Run locally to populate AWS database
python3 loadsectors.py
python3 loadbuyselldaily.py
python3 loadbuysellyweekly.py
python3 loadbuysellmonthly.py

# Option 2: Run in AWS Lambda/EC2 with same environment variables
```

### Step 5: Test All Endpoints

```bash
# Get your API Gateway endpoint
API_ENDPOINT=$(aws apigateway get-rest-apis --query "items[?name=='stocks-algo-api'].id" --output text)
API_STAGE_ENDPOINT="https://${API_ENDPOINT}.execute-api.us-east-1.amazonaws.com/dev"

# Test endpoints
curl "$API_STAGE_ENDPOINT/api/sectors"
curl "$API_STAGE_ENDPOINT/api/signals"
curl "$API_STAGE_ENDPOINT/api/scores"
curl "$API_STAGE_ENDPOINT/api/market/overview"
```

## Troubleshooting

### Issue: Still Getting 404 HTML Errors

**Cause 1: API Gateway not routing to Lambda**
- Check CloudWatch logs: `aws logs tail /aws/lambda/stocks-algo-api-dev-api --follow`
- Verify resource path is `{proxy+}` and method is `ANY`
- Check Lambda function permissions

**Cause 2: Lambda not connecting to database**
- Check Lambda logs for connection errors
- Verify VPC security group allows outbound to RDS on port 5432
- Test RDS connectivity from Lambda VPC

**Cause 3: Incorrect environment variables**
- Verify Lambda environment variables in AWS Console
- Check `serverless.yml` provider.environment section
- Make sure variables are set at deployment time

### Verify Lambda Handler

The handler should match: `index.handler` (exports from `index.js`)

```javascript
// index.js should contain:
const serverless = require('serverless-http');
const app = require('./index'); // Express app

module.exports.handler = serverless(app, {
  request: (request, event, context) => {
    request.event = event;
    request.context = context;
  },
});
```

## Deployment Checklist

- [ ] AWS account and credentials configured
- [ ] RDS database created (or using local DB)
- [ ] Database credentials stored in environment variables or AWS Secrets Manager
- [ ] Serverless Framework installed: `npm install -g serverless`
- [ ] AWS credentials configured: `aws configure`
- [ ] `serverless deploy` runs without errors
- [ ] API Gateway routes configured with `{proxy+}` pattern
- [ ] Lambda has RDS security group access (if using RDS)
- [ ] Test endpoint returns JSON (not 404 HTML)
- [ ] Data loaders have run against AWS database
- [ ] All 17 endpoints tested and working

## Environment Variables Reference

```bash
# AWS Configuration
AWS_REGION=us-east-1              # AWS region
STAGE=dev                          # Deployment stage

# Database Configuration
DB_HOST=<rds-endpoint-or-localhost>
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=<secure-password>
DB_NAME=stocks

# API Configuration
NODE_ENV=production
API_STAGE=dev

# Cognito (optional)
COGNITO_USER_POOL_ID=<pool-id>
COGNITO_CLIENT_ID=<client-id>
```

## Quick Deploy Script

```bash
#!/bin/bash
set -e

# Set your configuration
export AWS_REGION="us-east-1"
export DB_HOST="your-rds-endpoint.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_PASSWORD="your-password"
export DB_NAME="stocks"

echo "Deploying to AWS..."
cd webapp/lambda
npm install
serverless deploy \
  --region $AWS_REGION \
  --stage dev \
  --param="dbHost=$DB_HOST" \
  --param="dbPort=$DB_PORT" \
  --param="dbUser=$DB_USER" \
  --param="dbPassword=$DB_PASSWORD" \
  --param="dbName=$DB_NAME"

echo "✅ Deployment complete!"
echo "Test your API at: https://<api-id>.execute-api.us-east-1.amazonaws.com/dev"
```

## Next Steps

1. Complete the checklist above
2. Deploy using Serverless Framework
3. Run data loaders against AWS database
4. Test all 17 endpoints
5. Monitor CloudWatch logs for errors
6. Set up CI/CD pipeline for automatic deployments

## Support

For issues:
1. Check CloudWatch logs: `aws logs tail /aws/lambda/stocks-algo-api-dev-api`
2. Test locally first: `npm start` in lambda directory
3. Verify RDS connectivity: `psql -h <rds-endpoint> -U postgres -d stocks`
4. Check API Gateway configuration in AWS Console

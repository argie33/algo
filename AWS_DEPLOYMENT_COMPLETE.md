# AWS DEPLOYMENT GUIDE - STOCK ANALYSIS DASHBOARD

## Overview

This guide provides step-by-step instructions to deploy the complete stock analysis dashboard to AWS, including:
- Frontend (React) → S3 + CloudFront
- Backend (Express API) → Lambda + API Gateway
- Database (PostgreSQL) → RDS
- All data tables (5.3M+ records) → RDS

## Current Status ✅

**Local Data** (Ready for migration):
```
✅ stock_scores:           5,278/5,278 (100%)
✅ momentum_metrics:       5,004/5,307 (94.3%)
✅ positioning_metrics:    5,314/5,315 (100%)
✅ company_profile:        5,315/5,315 (100%)
✅ market_data:            5,282/5,315 (99.4%)
✅ sector_ranking:         9,036 rows
✅ price_daily:           23,367,073 rows
```

**Application** (Built & tested):
- Frontend: `/home/stocks/algo/webapp/frontend/dist/` (production ready)
- Backend: `/home/stocks/algo/webapp/lambda/` (Express API, 11 endpoints)
- APIs: All endpoints tested locally ✓

---

## DEPLOYMENT OPTIONS

### Option 1: Terraform (Recommended - Fully Automated)

**Prerequisites:**
```bash
# Install Terraform
brew install terraform  # macOS
# OR
apt-get install terraform  # Linux

# Configure AWS
aws configure
```

**Deploy:**
```bash
cd /home/stocks/algo

# Initialize Terraform
terraform init

# Review what will be created
terraform plan

# Deploy infrastructure
terraform apply \
  -var="aws_region=us-east-1" \
  -var="db_password=YourSecurePassword123!" \
  -auto-approve

# Get outputs
terraform output
```

**This creates:**
- VPC with public/private subnets
- RDS PostgreSQL database (Multi-AZ, automated backups)
- Lambda function with environment variables
- API Gateway (HTTP API)
- S3 bucket for frontend
- CloudFront distribution
- CloudWatch logs

---

### Option 2: AWS CLI (Manual but Direct)

#### Step 1: Create S3 Bucket for Frontend

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
S3_BUCKET="stock-analysis-frontend-$ACCOUNT_ID"

aws s3 mb s3://$S3_BUCKET --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket $S3_BUCKET \
  --versioning-configuration Status=Enabled

# Deploy frontend
aws s3 sync /home/stocks/algo/webapp/frontend/dist/ s3://$S3_BUCKET/ \
  --region us-east-1 \
  --cache-control "max-age=31536000" \
  --exclude "index.html" \
  --delete

# Set index.html with no caching
aws s3 cp /home/stocks/algo/webapp/frontend/dist/index.html \
  s3://$S3_BUCKET/index.html \
  --cache-control "no-cache" \
  --content-type "text/html"

echo "✅ Frontend deployed to: s3://$S3_BUCKET"
```

#### Step 2: Create RDS Database

```bash
# Create security group
aws ec2 create-security-group \
  --group-name stock-analysis-rds \
  --description "Security group for Stock Analysis RDS"

SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=stock-analysis-rds" \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

# Allow PostgreSQL access
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 5432 \
  --cidr 0.0.0.0/0

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier stock-analysis-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.3 \
  --master-username postgres \
  --master-user-password "StockAnalysis2024!" \
  --allocated-storage 100 \
  --storage-type gp3 \
  --vpc-security-group-ids $SG_ID \
  --publicly-accessible \
  --backup-retention-period 7 \
  --region us-east-1

# Wait for RDS to be ready (5-10 minutes)
aws rds wait db-instance-available \
  --db-instance-identifier stock-analysis-db

# Get endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stock-analysis-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

echo "✅ RDS Database ready at: $RDS_ENDPOINT"
```

#### Step 3: Migrate Local Database to RDS

```bash
# Export local database
pg_dump -h localhost -U postgres -d stocks > /tmp/stocks_local.sql

# Import to RDS (replace with your RDS endpoint)
psql -h $RDS_ENDPOINT \
  -U postgres \
  -d stocks \
  -f /tmp/stocks_local.sql

echo "✅ Data migrated to RDS"
```

#### Step 4: Deploy Lambda Function

```bash
# Package Lambda function
cd /home/stocks/algo/webapp/lambda
npm install --production
cd /home/stocks/algo
zip -r /tmp/lambda_function.zip webapp/lambda/

# Create IAM role for Lambda
aws iam create-role \
  --role-name stock-analysis-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Action": "sts:AssumeRole",
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"}
    }]
  }'

# Attach policies
aws iam attach-role-policy \
  --role-name stock-analysis-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam attach-role-policy \
  --role-name stock-analysis-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole

# Create Lambda function
ROLE_ARN=$(aws iam get-role \
  --role-name stock-analysis-lambda-role \
  --query 'Role.Arn' \
  --output text)

aws lambda create-function \
  --function-name stock-analysis-api \
  --runtime nodejs18.x \
  --role $ROLE_ARN \
  --handler index.handler \
  --zip-file fileb:///tmp/lambda_function.zip \
  --timeout 30 \
  --memory-size 512 \
  --environment "Variables={DB_HOST=$RDS_ENDPOINT,DB_PORT=5432,DB_USER=postgres,DB_PASSWORD=StockAnalysis2024!,DB_NAME=stocks}" \
  --region us-east-1

echo "✅ Lambda function deployed"
```

#### Step 5: Create API Gateway

```bash
# Create HTTP API
API_ID=$(aws apigatewayv2 create-api \
  --name stock-analysis-api \
  --protocol-type HTTP \
  --cors-configuration AllowOrigins="*",AllowMethods="*",AllowHeaders="*" \
  --query 'ApiId' \
  --output text)

# Create Lambda integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
  --api-id $API_ID \
  --integration-type AWS_PROXY \
  --integration-method POST \
  --integration-uri "arn:aws:apigatewayv2:us-east-1:$(aws sts get-caller-identity --query Account --output text):integrations/$(aws lambda get-function --function-name stock-analysis-api --query 'Configuration.FunctionArn' --output text)" \
  --query 'IntegrationId' \
  --output text)

# Create route
aws apigatewayv2 create-route \
  --api-id $API_ID \
  --route-key "ANY /{proxy+}" \
  --target "integrations/$INTEGRATION_ID"

# Create deployment
aws apigatewayv2 create-stage \
  --api-id $API_ID \
  --stage-name default \
  --auto-deploy

# Get API endpoint
API_ENDPOINT="https://$API_ID.execute-api.us-east-1.amazonaws.com"

echo "✅ API Gateway deployed at: $API_ENDPOINT"
```

#### Step 6: Create CloudFront Distribution

```bash
# Create CloudFront distribution pointing to S3
DISTRIBUTION_ID=$(aws cloudfront create-distribution \
  --distribution-config '{
    "CallerReference": "'$(date +%s)'",
    "Comment": "Stock Analysis Dashboard Frontend",
    "DefaultRootObject": "index.html",
    "Origins": {
      "Quantity": 1,
      "Items": [{
        "Id": "S3Origin",
        "DomainName": "'$S3_BUCKET'.s3.amazonaws.com",
        "S3OriginConfig": {}
      }]
    },
    "DefaultCacheBehavior": {
      "TargetOriginId": "S3Origin",
      "ViewerProtocolPolicy": "redirect-to-https",
      "AllowedMethods": {
        "Quantity": 2,
        "Items": ["GET", "HEAD"]
      },
      "ForwardedValues": {
        "QueryString": false,
        "Cookies": {"Forward": "none"}
      },
      "TrustedSigners": {
        "Enabled": false,
        "Quantity": 0
      }
    },
    "Enabled": true
  }' \
  --query 'Distribution.DomainName' \
  --output text)

echo "✅ CloudFront distribution deployed at: $DISTRIBUTION_ID"
```

---

## VERIFICATION

### Test Database Connection

```bash
psql -h $RDS_ENDPOINT \
  -U postgres \
  -d stocks \
  -c "SELECT COUNT(*) FROM stock_scores;"
```

### Test API Endpoints

```bash
# Get scores
curl "$API_ENDPOINT/api/scores?limit=5"

# Get momentum leaders
curl "$API_ENDPOINT/api/momentum/leaders?limit=3"

# Get positioning metrics
curl "$API_ENDPOINT/api/positioning-metrics/short-interest?limit=3"

# Get sectors data
curl "$API_ENDPOINT/api/sectors/sectors-with-history"
```

### Access Frontend

Open browser and navigate to:
- CloudFront: `https://$DISTRIBUTION_ID`
- S3 Direct: `https://$S3_BUCKET.s3.amazonaws.com/index.html`

---

## MONITORING & LOGS

### Lambda Logs

```bash
aws logs tail /aws/lambda/stock-analysis-api --follow
```

### RDS Monitoring

```bash
# Database metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=stock-analysis-db \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

### CloudFront Analytics

```bash
# View cache hit ratio
aws cloudfront get-distribution-statistics \
  --id $DISTRIBUTION_ID
```

---

## COST ESTIMATION

| Component | Size | Monthly Cost |
|-----------|------|-------------|
| Lambda | 1M requests | $20-30 |
| RDS (db.t3.micro) | 100GB | $30-40 |
| S3 | 2GB | $0.05 |
| CloudFront | 50GB/month | $5-10 |
| Data Transfer | Regional | $2-5 |
| **TOTAL** | | **$57-85** |

---

## TROUBLESHOOTING

### Lambda Timeout

**Problem:** Lambda function times out before query completes
**Solution:**
1. Increase timeout to 60 seconds
2. Add RDS connection pooling
3. Optimize queries

```bash
aws lambda update-function-configuration \
  --function-name stock-analysis-api \
  --timeout 60
```

### Database Connection Failed

**Problem:** Lambda can't connect to RDS
**Solution:**
1. Check security group allows access from Lambda security group
2. Verify RDS endpoint is publicly accessible
3. Confirm credentials in environment variables

```bash
# Add Lambda security group to RDS
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --source-group $LAMBDA_SG_ID \
  --protocol tcp \
  --port 5432
```

### CloudFront Cache Issues

**Problem:** Frontend shows old data
**Solution:**
1. Invalidate cache
2. Set shorter TTL for index.html

```bash
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"
```

---

## CLEANUP

To delete all AWS resources:

```bash
# Delete CloudFront distribution
aws cloudfront delete-distribution --id $DISTRIBUTION_ID

# Delete API Gateway
aws apigatewayv2 delete-api --api-id $API_ID

# Delete Lambda function
aws lambda delete-function --function-name stock-analysis-api

# Delete RDS database
aws rds delete-db-instance \
  --db-instance-identifier stock-analysis-db \
  --skip-final-snapshot

# Delete S3 bucket
aws s3 rb s3://$S3_BUCKET --force

# Delete IAM role
aws iam delete-role --role-name stock-analysis-lambda-role
```

---

## NEXT STEPS

1. ✅ Deploy infrastructure (Terraform or CLI)
2. ✅ Migrate local data to RDS
3. ✅ Test all API endpoints
4. ✅ Access frontend via CloudFront
5. ✅ Set up monitoring and alerts
6. ✅ Configure custom domain (optional)
7. ✅ Set up CI/CD for deployments

---

**Ready to deploy? Start with Option 1 (Terraform) for the smoothest experience!**

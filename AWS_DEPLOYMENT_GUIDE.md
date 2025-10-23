# AWS Deployment Guide for Stock Analysis Dashboard

## Overview
This guide will deploy the entire stock analysis application to AWS with:
- **Backend**: Lambda (serverless) or EC2
- **Frontend**: S3 + CloudFront
- **Database**: RDS PostgreSQL
- **Data Loaders**: EC2 Instance or Lambda scheduled tasks

## Prerequisites
- AWS Account with appropriate permissions (NOT just "reader")
- AWS CLI configured (`aws sts get-caller-identity` works)
- Database dump ready: `/tmp/stocks_database.sql` (13GB)

## Step 1: Create RDS Database Instance

```bash
# Create RDS instance for PostgreSQL
aws rds create-db-instance \
  --db-instance-identifier stocks-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16.1 \
  --master-username postgres \
  --master-user-password YOUR_STRONG_PASSWORD \
  --allocated-storage 500 \
  --storage-type gp3 \
  --publicly-accessible true \
  --region us-east-1

# Wait for instance to be available (10-15 minutes)
aws rds describe-db-instances \
  --db-instance-identifier stocks-db \
  --region us-east-1 \
  --query 'DBInstances[0].DBInstanceStatus'
```

## Step 2: Create S3 Bucket for Database Backup

```bash
# Create S3 bucket for database backups
aws s3 mb s3://stocks-algo-backups-$(date +%s) --region us-east-1

# Upload database dump
aws s3 cp /tmp/stocks_database.sql s3://stocks-algo-backups-TIMESTAMP/

# Create bucket for frontend deployment
aws s3 mb s3://stocks-algo-frontend-$(date +%s) --region us-east-1
```

## Step 3: Restore Database to RDS

```bash
# Get RDS endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier stocks-db \
  --region us-east-1 \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# Restore database (this will take time)
psql -h $RDS_ENDPOINT -U postgres -d postgres << EOF
CREATE DATABASE stocks;
EOF

# Restore the dump
psql -h $RDS_ENDPOINT -U postgres -d stocks < /tmp/stocks_database.sql
```

## Step 4: Package and Deploy Backend

### Option A: Deploy to Lambda

```bash
# Install serverless framework
npm install -g serverless

# Create serverless.yml in /home/stocks/algo/webapp/lambda/
# Then deploy
serverless deploy --region us-east-1
```

### Option B: Deploy to EC2

```bash
# Create EC2 instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key \
  --security-groups default \
  --region us-east-1

# SSH into instance and:
# 1. Install Node.js and npm
# 2. Clone the repo
# 3. Install dependencies
# 4. Set environment variables for RDS
# 5. Start the server (use PM2 or systemd)
```

## Step 5: Build and Deploy Frontend

```bash
# Build frontend for production
cd /home/stocks/algo/webapp/frontend
npm run build

# Deploy to S3
BUCKET_NAME=$(aws s3 ls | grep stocks-algo-frontend | awk '{print $3}')
aws s3 sync dist/ s3://$BUCKET_NAME/ --delete

# Enable website hosting
aws s3 website s3://$BUCKET_NAME/ \
  --index-document index.html \
  --error-document index.html
```

## Step 6: Set Up CloudFront Distribution

```bash
# Create CloudFront distribution
aws cloudfront create-distribution \
  --origin-domain-name $BUCKET_NAME.s3.amazonaws.com \
  --default-root-object index.html
```

## Step 7: Run Data Loaders on RDS

```bash
# Update environment variables to point to RDS
export DB_HOST=$RDS_ENDPOINT
export DB_USER=postgres
export DB_PASSWORD=YOUR_PASSWORD
export DB_NAME=stocks

# Run all loaders
python3 loadsectors.py
python3 load_sector_performance.py
# ... run other loaders as needed
```

## Step 8: Verify Deployment

```bash
# Test backend API
curl https://your-api-endpoint/api/sectors/sectors-with-history

# Test frontend
# Visit https://your-cloudfront-domain.cloudfront.net
```

## Environment Variables for AWS Deployment

```bash
# Backend (.env or Lambda environment variables)
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=stocks
NODE_ENV=production
PORT=3001

# Frontend (.env.production)
VITE_API_URL=https://your-api-endpoint
```

## Cost Estimate
- **RDS db.t3.medium**: ~$60/month
- **EC2 t3.medium** (if used): ~$30/month
- **S3 Storage**: ~$5/month
- **CloudFront**: Based on usage, typically $20-50/month
- **Total**: ~$115-160/month

## Cleanup

To avoid charges, delete resources when done:

```bash
# Delete RDS instance
aws rds delete-db-instance \
  --db-instance-identifier stocks-db \
  --skip-final-snapshot

# Delete S3 buckets
aws s3 rm s3://bucket-name --recursive
aws s3api delete-bucket --bucket bucket-name

# Delete EC2 instances (if used)
aws ec2 terminate-instances --instance-ids i-xxxxx

# Delete CloudFront distribution
aws cloudfront delete-distribution --id DISTRIBUTION_ID
```

## Important Notes

⚠️ **Current Issue**: Your AWS user account has "reader" permissions only.
- You may not have permissions to create RDS, EC2, or other resources
- Contact your AWS administrator to grant appropriate permissions
- Required permissions: RDS (full), EC2 (full), S3 (full), CloudFront (full), IAM (limited)

📝 **Next Steps**:
1. Get proper AWS permissions from account administrator
2. Set up an IAM role with deployment permissions
3. Run the deployment script with elevated permissions
4. Monitor costs and cleanup after verification

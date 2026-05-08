# Lambda Loader Deployment Guide

## Overview

Move 10 lightweight loaders from ECS to AWS Lambda for **70% cost reduction** and **simpler operations**.

### Loaders Moving to Lambda (Tier 1: Small, Fast)
```
econ-data        101 lines  <5 min   <100MB
calendar         101 lines  <2 min   <100MB
sentiment        101 lines  <5 min   <100MB
feargreed        101 lines  <2 min   <100MB
naaim            101 lines  <3 min   <100MB
analyst_sentiment 101 lines  <3 min   <100MB
analyst_upgrade  101 lines  <3 min   <100MB
benchmark        101 lines  <2 min   <100MB
commodities      100 lines  <2 min   <100MB
news             100 lines  <5 min   <100MB
```

**Why Lambda?**
- No idle cost (pay per execution)
- Perfect fit: <5min, <512MB memory
- Automatic scaling (no concurrency tuning)
- EventBridge scheduling built-in
- Result: $5-10/month vs $30-40 on ECS per loader

## Architecture

```
EventBridge Schedule (5:30am ET)
    ↓
Lambda Function (loader-econ, etc.)
    ↓
RDS Database (watermark tracking, insert)
    ↓
Success → CloudWatch Logs
         Metrics (execution time, rows inserted)
```

## Local Testing

### 1. Start Docker Compose
```bash
docker-compose up -d postgres redis

# Optional: Add UI tools
docker-compose --profile ui up -d pgadmin redis-commander
```

### 2. Test Loader Locally
```bash
# Set environment
export DB_HOST=localhost
export DB_USER=stocks
export DB_PASSWORD=''
export REDIS_URL=redis://localhost:6379

# Run via Lambda wrapper (simulates Lambda invocation)
python3 lambda_loader_wrapper.py econ --symbols AAPL,MSFT

# Or test the loader directly
python3 loadecondata.py --symbols AAPL,MSFT --parallelism 2
```

### 3. Expected Output
```
INFO: LambdaLoaderWrapper invoked: loader=econ symbols=['AAPL', 'MSFT']
INFO: [econ_data] Starting load: 2 symbols (parallelism=2)
INFO: [econ_data] Done. fetched=10 dedup_skip=0 quality_drop=0 inserted=10
      (processed=2 skipped_wm=0 failed=0) 2.5s sources={'yfinance': 2}
{
  "status": "success",
  "stats": {
    "rows_fetched": 10,
    "rows_inserted": 10,
    "symbols_processed": 2,
    "symbols_failed": 0,
    "duration_sec": 2.5,
    "source_distribution": {"yfinance": 2}
  },
  "execution_time_seconds": 2.5,
  "timestamp": "2026-05-08T..."
}
```

## Deployment to AWS

### Step 1: Create Lambda Layer (Shared Dependencies)

```bash
# Create layer directory
mkdir -p lambda-layer/python/lib/python3.11/site-packages

# Install dependencies
pip install -r requirements-lambda.txt \
  -t lambda-layer/python/lib/python3.11/site-packages/

# Create zip
cd lambda-layer
zip -r ../layer-loader-deps.zip .
cd ..

# Upload to S3
aws s3 cp layer-loader-deps.zip \
  s3://stocks-{account-id}-artifacts-us-east-1/layer-loader-deps.zip
```

### Step 2: Package Lambda Functions

```bash
# Create deployment package
zip -r lambda-loaders.zip \
  lambda_loader_wrapper.py \
  loadecondata.py \
  loadcalendar.py \
  loadsentiment.py \
  loadfeargreed.py \
  loadnaaim.py \
  loadanalystsentiment.py \
  loadanalystupgradedowngrade.py \
  loadbenchmark.py \
  loadcommodities.py \
  loadnews.py \
  optimal_loader.py \
  watermark_loader.py \
  bloom_dedup.py \
  data_source_router.py

# Upload to S3
aws s3 cp lambda-loaders.zip \
  s3://stocks-{account-id}-artifacts-us-east-1/lambda-loaders.zip
```

### Step 3: Deploy CloudFormation Stack

```bash
# Validate template
aws cloudformation validate-template \
  --template-body file://template-loader-lambda.yml

# Create stack
aws cloudformation create-stack \
  --stack-name stocks-loaders-lambda \
  --template-body file://template-loader-lambda.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# Monitor deployment
aws cloudformation wait stack-create-complete \
  --stack-name stocks-loaders-lambda \
  --region us-east-1

# Check status
aws cloudformation describe-stacks \
  --stack-name stocks-loaders-lambda \
  --region us-east-1 \
  --query 'Stacks[0].StackStatus'
```

### Step 4: Verify Deployment

```bash
# List Lambda functions
aws lambda list-functions --region us-east-1 \
  --query 'Functions[?contains(FunctionName, `loader`)].FunctionName'

# Test invoke econ loader
aws lambda invoke \
  --function-name loader-econ-data \
  --payload '{"symbols":"AAPL,MSFT","parallelism":2}' \
  --region us-east-1 \
  /tmp/response.json

# Check response
cat /tmp/response.json | jq '.'

# View logs
aws logs tail /aws/lambda/loader-econ-data --follow --region us-east-1
```

## Monitoring

### CloudWatch Metrics

```bash
# Execution duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=loader-econ-data \
  --start-time 2026-05-01T00:00:00Z \
  --end-time 2026-05-08T00:00:00Z \
  --period 3600 \
  --statistics Average,Maximum,Minimum

# Error count
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=loader-econ-data \
  --start-time 2026-05-01T00:00:00Z \
  --end-time 2026-05-08T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

### Check Watermarks

```bash
# View watermarks for Lambda-loaded tables
psql -h <rds-endpoint> -U stocks -d stocks -c "
  SELECT loader, COUNT(symbol) as symbols, MAX(watermark) as latest_date
  FROM loader_watermarks
  WHERE loader IN ('econ_data', 'calendar', 'sentiment', 'feargreed', 'naaim')
  GROUP BY loader
  ORDER BY loader;
"
```

## Cost Comparison

### Old (ECS-only, all loaders)
```
ECS Fargate Spot: ~$30-40/month
Bandwidth: ~$5/month
RDS: included (price_daily, etf prices)
Total: ~$35-45/month
```

### New (ECS + Lambda hybrid)
```
ECS Fargate Spot (large loaders): ~$15-20/month
Lambda (small loaders): ~$5-10/month
  - 10 loaders × $0.50-1/month = $5-10
Bandwidth: ~$5/month
RDS: included
Total: ~$25-35/month
Savings: 30-40% ($10-20/month)
```

## Troubleshooting

### Lambda Function Times Out
- Check CloudWatch logs: `/aws/lambda/loader-*`
- Increase timeout (current: 300s, can go to 900s)
- Reduce parallelism or symbol count via event payload
- Check RDS connection limits

### "Unable to import module" Error
- Verify lambda_loader_wrapper.py is in package root
- Check all dependencies are in layer
- View error in CloudWatch Logs

### Watermark Not Advancing
- Check RDS connectivity (test from Lambda)
- Verify IAM role has Secrets Manager permissions
- Check loader_watermarks table for error_count

### EventBridge Not Triggering
- Verify schedule is enabled: `aws events describe-rule --name loader-econ-daily`
- Check permissions: Lambda needs `lambda:InvokeFunction` from events.amazonaws.com
- View EventBridge metrics: "Invocations" and "FailedInvocations"

## Rollback

If you need to rollback from Lambda to ECS:

```bash
# Disable EventBridge rules
aws events disable-rule --name loader-econ-daily
aws events disable-rule --name loader-calendar-daily
# ... etc for all loaders

# Add loaders back to ECS task definition
# (edit template-app-ecs-tasks.yml, re-add task definitions)

# Delete Lambda stack
aws cloudformation delete-stack \
  --stack-name stocks-loaders-lambda \
  --region us-east-1
```

## References

- `lambda_loader_wrapper.py` — Lambda entry point
- `template-loader-lambda.yml` — CloudFormation template
- `docker-compose.yml` — Local testing setup
- [AWS Lambda Handler Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html)
- [EventBridge Scheduling](https://docs.aws.amazon.com/eventbridge/latest/userguide/create-eventbridge-scheduled-rule.html)

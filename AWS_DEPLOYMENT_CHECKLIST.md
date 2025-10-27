# AWS Deployment Checklist - Stocks Financial Dashboard

Complete guide for deploying the stocks financial dashboard to AWS production.

---

## Phase 1: Pre-Deployment Prerequisites

### 1.1 AWS Account Setup
- [ ] AWS Account created and verified
- [ ] AWS CLI configured (`aws configure` with credentials)
- [ ] AWS Account ID noted: `________________`
- [ ] AWS Region set to: `us-east-1` (default)

### 1.2 GitHub Configuration
- [ ] GitHub repository connected to AWS (push access required)
- [ ] GitHub Secrets configured:
  - [ ] `AWS_ACCOUNT_ID` - Your 12-digit AWS account number
  - [ ] `AWS_OIDC_ROLE_ARN` - OIDC role ARN for GitHub Actions (create in step 1.3)

### 1.3 GitHub OIDC Identity Provider Setup
```bash
# This allows GitHub Actions to authenticate to AWS without long-lived credentials

# 1. Create OIDC Identity Provider in AWS:
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --region us-east-1

# 2. Create IAM Role for GitHub Actions:
aws iam create-role \
  --role-name GitHubActionsDeployRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:USERNAME/REPO:ref:refs/heads/main"
        }
      }
    }]
  }' \
  --region us-east-1

# 3. Attach permissions:
aws iam attach-role-policy \
  --role-name GitHubActionsDeployRole \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess \
  --region us-east-1
```

- [ ] OIDC provider created in IAM
- [ ] `GitHubActionsDeployRole` created with OIDC trust relationship
- [ ] Role ARN noted: `arn:aws:iam::ACCOUNT_ID:role/GitHubActionsDeployRole`

### 1.4 Database Preparation
- [ ] RDS PostgreSQL instance created (or existing)
  - Instance endpoint: `________________`
  - Database name: `stocks`
  - Master username: `postgres`
  - Port: `5432`

- [ ] RDS credentials stored in AWS Secrets Manager
  ```bash
  aws secretsmanager create-secret \
    --name stocks-db-credentials \
    --description "Stocks database credentials" \
    --secret-string '{
      "username": "postgres",
      "password": "YOUR_PASSWORD",
      "engine": "postgres",
      "host": "stocks-db.XXXXX.us-east-1.rds.amazonaws.com",
      "port": 5432,
      "dbname": "stocks"
    }' \
    --region us-east-1
  ```
  - [ ] Secret ARN noted: `arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:stocks-db-credentials`

- [ ] Database tables created (already populated with initial data)
  - [ ] Verify with: `psql -h ENDPOINT -U postgres -d stocks -c "SELECT COUNT(*) FROM stock_scores;"`

### 1.5 VPC & Networking Setup
- [ ] VPC created (or use default)
  - VPC ID: `________________`

- [ ] Private Subnet created for ECS tasks
  - [ ] Tag with `Name=private-subnet-1`
  - [ ] Subnet ID: `________________`

- [ ] Security Group created for ECS tasks
  - [ ] Name: `ecs-security-group`
  - [ ] Tag with `Name=ecs-security-group`
  - [ ] Inbound: Allow PostgreSQL (5432) from RDS security group
  - [ ] Outbound: Allow all (for external API calls)
  - [ ] Security Group ID: `________________`

- [ ] RDS Security Group configured
  - [ ] Inbound: Allow 5432 from ECS security group
  - [ ] Outbound: Allow all

### 1.6 ECR Repository Setup
```bash
# Create ECR repository for data loaders
aws ecr create-repository \
  --repository-name stocks-data-loader \
  --region us-east-1
```

- [ ] ECR repository created: `stocks-data-loader`
  - Repository URI: `ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-data-loader`

### 1.7 ECS Cluster Setup
```bash
# Create ECS cluster for running data loaders
aws ecs create-cluster \
  --cluster-name stocks-ecs-cluster \
  --region us-east-1
```

- [ ] ECS cluster created: `stocks-ecs-cluster`

### 1.8 CloudWatch Log Groups
```bash
# Create log group for data loaders
aws logs create-log-group \
  --log-group-name /ecs/stocks-data-loader \
  --region us-east-1

# Set retention policy (7 days)
aws logs put-retention-policy \
  --log-group-name /ecs/stocks-data-loader \
  --retention-in-days 7 \
  --region us-east-1
```

- [ ] CloudWatch log group created: `/ecs/stocks-data-loader`
- [ ] Retention policy set to 7 days

### 1.9 IAM Roles for ECS Tasks
```bash
# Create ECS task execution role
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' \
  --region us-east-1

# Attach policies
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
  --region us-east-1

aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess \
  --region us-east-1

# Create ECS task role (for accessing Secrets Manager)
aws iam create-role \
  --role-name ecsTaskRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }' \
  --region us-east-1

# Add Secrets Manager access policy
aws iam put-role-policy \
  --role-name ecsTaskRole \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:stocks-db-credentials"
    }]
  }' \
  --region us-east-1
```

- [ ] `ecsTaskExecutionRole` created and configured
  - Role ARN: `arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole`

- [ ] `ecsTaskRole` created with Secrets Manager access
  - Role ARN: `arn:aws:iam::ACCOUNT_ID:role/ecsTaskRole`

---

## Phase 2: Deployment - Data Loaders (ECS Fargate)

### 2.1 Build and Push Docker Image
The GitHub Actions workflow `.github/workflows/run-data-loaders.yml` handles this automatically, but can also be done manually:

```bash
# Build Docker image
docker build -f Dockerfile.loaders -t stocks-data-loader:latest .

# Tag for ECR
docker tag stocks-data-loader:latest ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-data-loader:latest

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
docker push ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-data-loader:latest
```

- [ ] Docker image built successfully
- [ ] Image pushed to ECR

### 2.2 Register ECS Task Definition
The GitHub Actions workflow does this automatically on each execution. Manual registration:

```bash
aws ecs register-task-definition \
  --family stocks-data-loader \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu 256 \
  --memory 512 \
  --execution-role-arn arn:aws:iam::ACCOUNT_ID:role/ecsTaskExecutionRole \
  --task-role-arn arn:aws:iam::ACCOUNT_ID:role/ecsTaskRole \
  --container-definitions '[{
    "name": "data-loader",
    "image": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/stocks-data-loader:latest",
    "essential": true,
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/stocks-data-loader",
        "awslogs-region": "us-east-1",
        "awslogs-stream-prefix": "loader"
      }
    },
    "secrets": [{
      "name": "DB_SECRET_ARN",
      "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:stocks-db-credentials"
    }]
  }]' \
  --region us-east-1
```

- [ ] Task definition registered: `stocks-data-loader`

### 2.3 Test Data Loader Execution
```bash
# Run a test task
aws ecs run-task \
  --cluster stocks-ecs-cluster \
  --task-definition stocks-data-loader \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-XXXXX],securityGroups=[sg-XXXXX],assignPublicIp=ENABLED}" \
  --overrides '{
    "containerOverrides": [{
      "name": "data-loader",
      "command": ["loadstockscores.py"]
    }]
  }' \
  --region us-east-1

# Monitor execution
aws logs tail /ecs/stocks-data-loader --follow --region us-east-1
```

- [ ] Test loader execution completed successfully
- [ ] Verify data in database: `SELECT COUNT(*) FROM stock_scores;`

### 2.4 Activate GitHub Actions Workflow
The workflow `.github/workflows/run-data-loaders.yml` will automatically:
- Run daily at 6 AM UTC
- Can be triggered manually via `workflow_dispatch`
- Automatically runs on push to any `load*.py` file

- [ ] GitHub Actions workflow active
- [ ] Manual trigger tested: Go to Actions → "Run Data Loaders" → "Run workflow"
- [ ] CloudWatch logs monitored: `aws logs tail /ecs/stocks-data-loader --follow`

---

## Phase 3: Deployment - Lambda API Gateway

### 3.1 Prepare SAM Template
The `template-webapp-lambda.yml` contains the complete Lambda + API Gateway configuration.

Required parameters:
- `EnvironmentName`: dev (or staging/prod)
- `DatabaseSecretArn`: `arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:stocks-db-credentials`
- `DatabaseEndpoint`: RDS endpoint (e.g., `stocks-db.XXXXX.us-east-1.rds.amazonaws.com`)

### 3.2 Build Lambda Package
```bash
# Install dependencies
cd webapp/lambda
npm install

# SAM will handle the build
```

- [ ] Lambda dependencies installed

### 3.3 Deploy via SAM CLI
```bash
# Initial deployment with guided prompts
sam deploy --guided \
  --template-file template-webapp-lambda.yml \
  --stack-name stocks-webapp-dev \
  --parameter-overrides \
      EnvironmentName=dev \
      DatabaseSecretArn=arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:stocks-db-credentials \
      DatabaseEndpoint=stocks-db.XXXXX.us-east-1.rds.amazonaws.com \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1

# Or use the GitHub Actions workflow:
# Go to "Actions" → "deploy-webapp" → "Run workflow"
```

- [ ] SAM deployment completed successfully
- [ ] Stack name: `stocks-webapp-dev`

### 3.4 Verify API Deployment
```bash
# Get API Gateway URL
aws apigateway get-rest-apis \
  --query "items[?name=='stocks-webapp-api-dev'].id" \
  --output text \
  --region us-east-1

# Retrieve full API endpoint
API_ID=$(aws apigateway get-rest-apis \
  --query "items[?name=='stocks-webapp-api-dev'].id" \
  --output text \
  --region us-east-1)

API_ENDPOINT="https://${API_ID}.execute-api.us-east-1.amazonaws.com/dev"

# Test API
curl -X GET "${API_ENDPOINT}/api/stocks?symbol=AAPL"
```

- [ ] API endpoint operational: `https://XXXXX.execute-api.us-east-1.amazonaws.com/dev`
- [ ] Health check passed

### 3.5 API Routes Verification
All routes in `webapp/lambda/routes/` are automatically served by the Lambda proxy handler:

**Core Routes**:
- [ ] `/api/stocks` - Stock data with prices and technicals
- [ ] `/api/sentiment` - Sentiment analysis (social, analyst, market)
- [ ] `/api/signals` - Trading signals with market stage
- [ ] `/api/metrics` - Fundamental metrics
- [ ] `/api/momentum` - Momentum indicators
- [ ] `/api/positioning` - Market positioning data

**Test Commands**:
```bash
# Get all active trading signals
curl "${API_ENDPOINT}/api/signals?timeframe=daily&signal_type=buy"

# Get sentiment for specific stock
curl "${API_ENDPOINT}/api/sentiment/analysis?symbol=AAPL"

# Get market-wide sentiment
curl "${API_ENDPOINT}/api/sentiment/market"

# Get stock metrics
curl "${API_ENDPOINT}/api/stocks?symbol=MSFT&include=metrics,sentiment"
```

- [ ] All core routes returning data
- [ ] No 500 errors in CloudWatch logs

---

## Phase 4: Deployment - Frontend

### 4.1 Frontend Build
```bash
cd webapp/frontend
npm install
npm run build
```

- [ ] Frontend build completed successfully
- [ ] `dist/` directory created

### 4.2 Deploy Frontend
Options:

**Option A: AWS S3 + CloudFront (SAM handles this)**
```bash
# SAM deployment includes frontend deployment to S3/CloudFront
sam deploy
```

**Option B: Manual S3 deployment**
```bash
# Upload to S3
aws s3 sync dist/ s3://stocks-webapp-frontend-dev-ACCOUNT_ID/

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id EXXXXXX \
  --paths "/*" \
  --region us-east-1
```

- [ ] Frontend deployed to S3
- [ ] CloudFront distribution active
- [ ] CloudFront domain accessible

---

## Phase 5: Monitoring & Verification

### 5.1 CloudWatch Logs
```bash
# Data loader logs
aws logs tail /ecs/stocks-data-loader --follow --region us-east-1

# Lambda logs
aws logs tail /aws/lambda/stocks-webapp-api-dev --follow --region us-east-1

# API Gateway logs
aws logs tail /aws/apigateway/stocks-webapp-dev --follow --region us-east-1
```

- [ ] Log groups created and accessible
- [ ] Recent logs showing successful executions

### 5.2 Database Verification
```bash
# Connect to RDS
psql -h stocks-db.XXXXX.us-east-1.rds.amazonaws.com -U postgres -d stocks

# Check record counts
SELECT
  (SELECT COUNT(*) FROM stock_scores) as stock_scores,
  (SELECT COUNT(*) FROM price_daily) as price_daily,
  (SELECT COUNT(*) FROM sentiment_analysis) as sentiment,
  (SELECT COUNT(*) FROM buy_sell_daily) as trading_signals;
```

- [ ] Database populated with recent data
- [ ] Stock scores: 5,280 records
- [ ] Trading signals: 100+ records
- [ ] Sentiment: 10,000+ records

### 5.3 API Response Verification
```bash
# Test key endpoints
curl -X GET "https://API_ID.execute-api.us-east-1.amazonaws.com/dev/api/stocks?symbol=AAPL" \
  -H "Content-Type: application/json"

# Expected: 200 OK with stock data
# Verify: prices, technicals, sentiment populated
```

- [ ] All API endpoints return 200 OK
- [ ] Response times < 1 second
- [ ] Data is current (recent timestamps)

### 5.4 Frontend Verification
```bash
# Test frontend deployment
open https://d1234.cloudfront.net/

# Verify:
# - Dashboard loads
# - Sentiment page shows data
# - Trading signals visible
# - No console errors
```

- [ ] Frontend loads without errors
- [ ] Dashboard pages functional
- [ ] API integration working

---

## Phase 6: Automation & Scheduling

### 6.1 Data Loader Schedule
GitHub Actions workflow runs automatically:

**Schedule**: Daily at 6 AM UTC (1 AM EST)
**Loaders**: 21 data sources (stock scores, prices, technicals, sentiment, metrics, signals)

```bash
# View recent executions
gh run list --workflow run-data-loaders.yml

# View specific run logs
gh run view RUN_ID --log
```

- [ ] Workflow running on schedule
- [ ] Last execution successful
- [ ] Next execution scheduled

### 6.2 Manual Workflow Triggers
```bash
# Trigger data loader workflow manually
gh workflow run run-data-loaders.yml

# Trigger webapp deployment
gh workflow run deploy-webapp.yml
```

- [ ] Manual triggers tested
- [ ] Deployments complete successfully

### 6.3 Monitoring Alerts (Optional)
Set up CloudWatch alarms for:
- Lambda errors
- ECS task failures
- Database connection failures
- API latency

```bash
# Example: Alert on Lambda errors
aws cloudwatch put-metric-alarm \
  --alarm-name stocks-api-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=stocks-webapp-api-dev \
  --evaluation-periods 1 \
  --region us-east-1
```

- [ ] CloudWatch alarms configured (optional)
- [ ] SNS notifications set up (optional)

---

## Phase 7: Post-Deployment Validation

### 7.1 End-to-End Test
```bash
# 1. Trigger data loader
gh workflow run run-data-loaders.yml

# 2. Wait 5 minutes for execution
sleep 300

# 3. Check database updated
psql -h ENDPOINT -U postgres -d stocks -c "SELECT MAX(fetched_at) FROM stock_scores;"

# 4. Test API returns new data
curl "https://API_ENDPOINT/api/stocks?symbol=AAPL"

# 5. Verify frontend displays data
open https://CLOUDFRONT_DOMAIN
```

- [ ] Data loader execution completed
- [ ] Database records updated with recent timestamps
- [ ] API returns fresh data
- [ ] Frontend displays updated information

### 7.2 Performance Validation
```bash
# Check API response times (target: <1 second)
time curl "https://API_ENDPOINT/api/stocks?symbol=AAPL"

# Check Lambda duration in CloudWatch
aws logs filter-log-events \
  --log-group-name /aws/lambda/stocks-webapp-api-dev \
  --query 'events[0].message' \
  --region us-east-1
```

- [ ] API response time < 1 second
- [ ] Lambda execution time < 30 seconds
- [ ] No throttling errors

### 7.3 Data Quality Validation
```bash
# Verify no fake/fallback data
psql -h ENDPOINT -U postgres -d stocks -c "
  SELECT symbol, COUNT(*) as count
  FROM stock_scores
  WHERE composite_score = 50 OR momentum_score = 50
  GROUP BY symbol;
"
# Expected: 0 rows (no fake default values)
```

- [ ] No hardcoded defaults (50, 0, "neutral")
- [ ] All data from real sources
- [ ] No transaction errors in logs

---

## Phase 8: Ongoing Maintenance

### 8.1 Daily Checks
- [ ] Data loader workflow ran successfully
- [ ] No errors in CloudWatch logs
- [ ] API responding normally
- [ ] Database growing with new data

### 8.2 Weekly Tasks
- [ ] Review CloudWatch metrics
- [ ] Check API performance
- [ ] Verify data freshness
- [ ] Review error logs

### 8.3 Monthly Tasks
- [ ] Update loader code as needed
- [ ] Review and optimize queries
- [ ] Check for storage issues
- [ ] Capacity planning for growth

### 8.4 Update Procedures
```bash
# Update a loader
git pull origin main
git add loadstockscores.py
git commit -m "Update: Improved stock score calculation"
git push origin main
# GitHub Actions automatically deploys!

# Update Lambda API
git add webapp/lambda/routes/sentiment.js
git commit -m "Fix: Sentiment aggregation logic"
git push origin main
# GitHub Actions automatically deploys webapp!
```

- [ ] Git workflow understood
- [ ] Deployment procedures documented
- [ ] Rollback procedures planned

---

## Troubleshooting Guide

### Data Loader Issues

**Issue**: ECS task fails with "Cannot connect to database"
```bash
# Check security groups
aws ec2 describe-security-groups --group-ids sg-XXXXX --region us-east-1

# Check database endpoint
aws rds describe-db-instances --query 'DBInstances[0].Endpoint' --region us-east-1

# Check Secrets Manager access
aws secretsmanager get-secret-value --secret-id stocks-db-credentials --region us-east-1
```

**Issue**: CloudWatch logs showing "File not found"
- Verify loader files exist in repository
- Check ECR image was rebuilt
- Verify Dockerfile.loaders includes loader files

### API Issues

**Issue**: Lambda returns 500 error
```bash
# Check Lambda logs
aws logs tail /aws/lambda/stocks-webapp-api-dev --follow --region us-east-1

# Check for database connection issues
psql -h ENDPOINT -U postgres -d stocks -c "SELECT 1;"
```

**Issue**: API Gateway returns 403 Forbidden
- Check CORS configuration in SAM template
- Verify IAM permissions on Lambda
- Check API Gateway authorizers

### Frontend Issues

**Issue**: Frontend not loading from CloudFront
- Verify S3 bucket policy allows CloudFront access
- Check CloudFront distribution settings
- Invalidate CloudFront cache

---

## Useful Commands Reference

```bash
# Data Loaders
aws ecs list-tasks --cluster stocks-ecs-cluster --region us-east-1
aws ecs describe-tasks --cluster stocks-ecs-cluster --tasks TASK_ARN --region us-east-1
aws logs tail /ecs/stocks-data-loader --follow --region us-east-1

# Lambda
aws lambda invoke --function-name stocks-webapp-api-dev response.json --region us-east-1
aws logs tail /aws/lambda/stocks-webapp-api-dev --follow --region us-east-1

# API Gateway
aws apigateway get-rest-apis --region us-east-1
aws apigateway get-stages --rest-api-id API_ID --region us-east-1

# Database
psql -h ENDPOINT -U postgres -d stocks

# GitHub Actions
gh workflow list
gh run list --workflow run-data-loaders.yml
gh workflow run run-data-loaders.yml
gh run view RUN_ID --log
```

---

## Deployment Summary

**Deployed Components**:
- ✅ GitHub OIDC for CI/CD authentication
- ✅ AWS Secrets Manager for credentials
- ✅ RDS PostgreSQL database (23.6M records)
- ✅ ECS Fargate for data loaders (21 daily sources)
- ✅ Lambda API Gateway (20 endpoints)
- ✅ S3 + CloudFront for frontend
- ✅ CloudWatch for monitoring
- ✅ GitHub Actions workflows (automated deployment)

**Data Sources** (automated daily):
1. Stock Scores (5,280)
2. Price Daily
3. Price Weekly
4. Price Monthly
5. Technicals Daily
6. Technicals Weekly
7. Technicals Monthly
8. Fundamental Metrics
9. Quality Metrics
10. Value Metrics
11. Growth Metrics
12. Momentum
13. Positioning
14. Social Sentiment
15. Analyst Sentiment
16. News Sentiment
17. AAII Market Sentiment
18. NAAIM Fund Exposure
19. CNN Fear & Greed Index
20. Signal Metrics
21. Population Script

**API Endpoints** (20 routes):
- `/api/stocks` - Core stock data
- `/api/sentiment` - Multi-source sentiment
- `/api/signals` - Trading signals
- `/api/metrics` - Fundamental metrics
- `/api/momentum` - Momentum indicators
- `/api/positioning` - Market positioning
- And 14+ more analytical endpoints

---

**Status**: Production Ready ✅

**Next Steps**:
1. Complete all Phase 1 prerequisites
2. Execute Phase 2-4 deployment steps
3. Verify Phase 5 monitoring
4. Monitor Phase 6 automation
5. Validate Phase 7 testing
6. Begin Phase 8 maintenance

All infrastructure code is in `/home/stocks/algo/`:
- `.github/workflows/run-data-loaders.yml` - Data loader automation
- `.github/workflows/deploy-webapp.yml` - Lambda deployment
- `template-webapp-lambda.yml` - SAM template (Lambda + API + Frontend)
- `Dockerfile.loaders` - Data loader container
- `webapp/lambda/` - All API routes
- `webapp/frontend/` - React UI

**Support**: Review AWS_DEPLOYMENT_CHECKLIST.md or check CloudWatch logs for issues.

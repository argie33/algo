# Financial Platform Deployment Guide

## Overview

This guide explains how to deploy the institutional-grade financial analysis platform with Step Functions orchestration and metrics calculation.

## Components

### 1. Core Infrastructure
- **File**: `template-core.yml` (existing)
- **Purpose**: VPC, subnets, security groups, RDS database

### 2. Application Infrastructure  
- **File**: `template-app-*.yml` (existing)
- **Purpose**: ECS cluster, load balancer, basic application setup

### 3. ECS Task Definitions
- **File**: `template-app-ecs-tasks.yml` (existing)
- **Purpose**: All data loading task definitions (loadinfo, price data, technicals, earnings, etc.)

### 4. Step Functions Orchestration (NEW)
- **File**: `template-step-functions-orchestration.yml`
- **Purpose**: Workflow orchestration with proper dependencies, replaces EventBridge scheduling

### 5. Metrics Calculation Scripts (NEW)
- **Files**: `calculate_quality_metrics.py`, `calculate_value_metrics.py`
- **Purpose**: Institutional-grade stock analysis using academic research models

### 6. Updated API and Frontend (UPDATED)
- **Files**: `webapp/lambda/routes/metrics.js`, `webapp/frontend/src/pages/MetricsDashboard.jsx`
- **Purpose**: Changed from "scores" to "metrics" terminology throughout

## Deployment Order

### 1. Deploy Core Infrastructure (if not already done)
```bash
aws cloudformation deploy \
  --template-file template-core.yml \
  --stack-name StocksCore \
  --capabilities CAPABILITY_IAM
```

### 2. Deploy Application Infrastructure (if not already done)
```bash
aws cloudformation deploy \
  --template-file template-app-stocks.yml \
  --stack-name StocksApp \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides CoreStackName=StocksCore
```

### 3. Deploy ECS Tasks (if not already done)
```bash
aws cloudformation deploy \
  --template-file template-app-ecs-tasks.yml \
  --stack-name StocksECSTasks \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    StockSymbolsImageTag=latest \
    LoadInfoImageTag=latest \
    # ... other image tags
```

### 4. Build and Push Metrics Calculator Images

#### Quality Metrics Calculator
```bash
# Build Docker image for quality metrics
docker build -f Dockerfile.quality-metrics -t stocks-quality-metrics .
docker tag stocks-quality-metrics:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/stocks-quality-metrics:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/stocks-quality-metrics:latest
```

#### Value Metrics Calculator  
```bash
# Build Docker image for value metrics
docker build -f Dockerfile.value-metrics -t stocks-value-metrics .
docker tag stocks-value-metrics:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/stocks-value-metrics:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/stocks-value-metrics:latest
```

### 5. Deploy Step Functions Orchestration
```bash
aws cloudformation deploy \
  --template-file template-step-functions-orchestration.yml \
  --stack-name StocksStepFunctions \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    UseStackImports=true \
    CoreStackName=StocksCore \
    AppStackName=StocksApp
```

## Integration Notes

### Step Functions Integration
The Step Functions template is designed to integrate with your existing infrastructure:

1. **Uses CloudFormation Imports**: References existing VPC, subnets, security groups from your core/app stacks
2. **References Existing Task Definitions**: Points to task definitions created by `template-app-ecs-tasks.yml`
3. **Modular Approach**: Keeps complex ECS definitions separate while adding orchestration

### Pipeline Dependencies
The Step Functions implement proper dependency management:

1. **Daily Pipeline**:
   - Data Collection (parallel): Price data, company info, earnings data
   - Technical Analysis: Runs after price data collection
   - Metrics Calculation (parallel): Quality and value metrics run after all data is loaded

2. **Weekly Pipeline**:
   - Stock symbols update → Weekly data collection → Weekly technical analysis

3. **Monthly Pipeline**:
   - Financial statements (parallel) → Monthly prices → Monthly technical analysis

### API Changes
- **New Endpoint**: `/api/metrics` replaces `/api/scores`
- **Scale Change**: Metrics use 0-1 scale instead of 0-100 for academic consistency
- **Enhanced Data**: Includes Piotroski F-Score, Altman Z-Score, DCF analysis

### Frontend Changes
- **New Component**: `MetricsDashboard.jsx` replaces `ScoresDashboard.jsx`
- **Route Update**: `/metrics` instead of `/scores`
- **Terminology**: All "scores" references changed to "metrics"

## Testing Deployment

### 1. Verify Step Functions
```bash
# List state machines
aws stepfunctions list-state-machines

# Execute a test run (optional)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:REGION:ACCOUNT:stateMachine:daily-data-pipeline-orchestration \
  --name test-execution-$(date +%s)
```

### 2. Check ECS Task Definitions
```bash
# Verify metrics task definitions exist
aws ecs describe-task-definition --task-definition calculate-quality-metrics
aws ecs describe-task-definition --task-definition calculate-value-metrics
```

### 3. Test API Endpoints
```bash
# Test metrics endpoint
curl https://your-api-domain/api/metrics/ping

# Test metrics data
curl "https://your-api-domain/api/metrics?limit=5"
```

### 4. Frontend Testing
- Navigate to `/metrics` in your web application
- Verify data loads and displays correctly
- Check that filtering and sorting work

## Monitoring

### CloudWatch Logs
- **Step Functions**: `/aws/stepfunctions/data-pipeline`
- **Quality Metrics**: `/ecs/calculate-quality-metrics`
- **Value Metrics**: `/ecs/calculate-value-metrics`

### Alarms
- Step Functions execution failures
- ECS task failures
- API response errors

## Troubleshooting

### Common Issues
1. **Task Definition Not Found**: Ensure ECS tasks template is deployed first
2. **Permission Denied**: Verify IAM roles have necessary permissions
3. **Network Issues**: Check security groups allow ECS task communication
4. **Database Connection**: Ensure RDS security group allows connections from ECS tasks

### Rollback Strategy
1. **Step Functions**: Delete the Step Functions stack, original EventBridge rules will remain
2. **API**: Revert to `/api/scores` endpoints if needed
3. **Frontend**: Revert to `ScoresDashboard.jsx` component

## Performance Optimization

### Resource Sizing
- **Quality Metrics**: 1024 CPU, 2048 MB memory (can be reduced for smaller datasets)
- **Value Metrics**: 1024 CPU, 2048 MB memory (DCF calculations are CPU intensive)

### Execution Frequency
- **Daily**: Market close + 30 minutes (4:30 PM ET)
- **Weekly**: Sundays 6:00 AM ET
- **Monthly**: First Sunday 9:00 AM ET

### Cost Optimization
- Use scheduled ECS tasks (Fargate Spot) for non-time-critical calculations
- Implement data retention policies for historical metrics
- Monitor CloudWatch costs for excessive logging

## Next Steps

1. **Deploy in Order**: Follow the deployment sequence above
2. **Monitor Initial Runs**: Watch first few Step Functions executions
3. **Validate Data**: Check that metrics are being calculated correctly
4. **Set Up Alerts**: Configure SNS notifications for failures
5. **Optimize Performance**: Adjust resource allocation based on actual usage

## Support

For issues or questions:
1. Check CloudWatch logs for detailed error messages
2. Verify all stack dependencies are properly deployed
3. Test individual ECS tasks before running full pipeline
4. Review IAM permissions if seeing access denied errors
# Data Loading Pipeline - Deployment & Operations Runbook

**Status**: Production-Ready  
**Last Updated**: 2026-05-02 21:30 UTC  
**Phases**: A (LIVE), C (Ready), D (Ready), E (Ready)

---

## Quick Start

### Pre-Deployment Validation
```bash
# Run test suite (all tests should pass)
./test-phase-integration.sh

# Check git status (clean working directory)
git status

# View what will be deployed
git log --oneline -5
```

### Deploy All Phases to AWS
```bash
# Set environment variables
export AWS_REGION=us-east-1
export ENVIRONMENT=prod

# 1. Phase A (already live, verify it's enabled)
aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack \
  --query 'Stacks[0].StackStatus'

# 2. Deploy Phase C Lambda infrastructure
aws cloudformation deploy \
  --stack-name stocks-lambda-phase-c \
  --template-file template-lambda-phase-c.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=prod

# 3. Deploy Phase D Step Functions
aws cloudformation deploy \
  --stack-name stocks-stepfunctions-phase-d \
  --template-file template-step-functions-phase-d.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides ECSClusterArn=<your-cluster-arn>

# 4. Deploy Phase E DynamoDB & caching
aws cloudformation deploy \
  --stack-name stocks-phase-e-incremental \
  --template-file template-phase-e-dynamodb.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=prod

# 5. Deploy EventBridge scheduling
STATE_MACHINE_ARN=$(aws cloudformation describe-stack-resource \
  --stack-name stocks-stepfunctions-phase-d \
  --logical-resource-id DataLoadingStateMachine \
  --query 'StackResourceDetail.PhysicalResourceId' --output text)

aws cloudformation deploy \
  --stack-name stocks-pipeline-scheduling \
  --template-file template-eventbridge-scheduling.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    StateMachineArn=$STATE_MACHINE_ARN \
    ScheduleTime='cron(0 2 * * ? *)' \
    Environment=prod
```

---

## Phase A: ECS S3 Staging + Fargate Spot (LIVE)

### Status
✅ Deployed 2026-05-02T20:15Z  
✅ Active in all 59 ECS task definitions  
✅ No deployment needed (already live)

### Expected Impact
| Loader | Before | After | Speedup |
|--------|--------|-------|---------|
| pricedaily | 1-2 min | 30-45 sec | 2-3x |
| priceweekly | 30 sec | 15-20 sec | 1.5-2x |
| technicals | 45 min | 20-30 min | 1.5-2.3x |
| buyselldaily | 3-4 hours | 30-45 min | (waiting Phase C) |
| stockscores | 15 min | 5-10 min | 1.5-3x |

### Verification
```bash
# Check S3 staging is enabled
aws ecs describe-task-definition --task-definition pricedaily:1 \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  | grep USE_S3_STAGING

# Check Fargate Spot ratio
aws ec2 describe-spot-fleet-requests

# Monitor S3 COPY in CloudWatch
aws logs tail /ecs/pricedaily-loader --follow | grep -i "copy\|insert"
```

---

## Phase C: Lambda Fan-Out Orchestration

### Deploy
```bash
aws cloudformation deploy \
  --stack-name stocks-lambda-phase-c \
  --template-file template-lambda-phase-c.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Test
```bash
# Option 1: Automatic (trigger on code change)
git commit --allow-empty -m "Test Phase C"
git push
# Watch GitHub Actions: execute-phase-c-lambda-orchestrator

# Option 2: Manual
aws lambda invoke \
  --function-name buyselldaily-orchestrator \
  --payload '{"symbol_count": 5000, "batch_size": 50}' \
  /tmp/phase-c-result.json
cat /tmp/phase-c-result.json | jq .
```

### Expected Results
- Execution time: ~7 minutes (vs 3-4 hours ECS)
- 100 Lambda workers invoked in parallel
- 5000 symbols × 50/batch = 100 batches
- Cost: $2.50 (vs $5-10 ECS Fargate)
- Speedup: 25x

### Monitor
```bash
# CloudWatch Logs
aws logs tail /aws/lambda/buyselldaily-orchestrator --follow

# Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=buyselldaily-orchestrator \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 \
  --statistics Average,Maximum

# S3 outputs
aws s3 ls s3://stocks-app-data/buyselldaily-phase-c/ --recursive
```

---

## Phase D: Step Functions DAG Orchestration

### Deploy
```bash
# Get cluster ARN
CLUSTER_ARN=$(aws cloudformation list-exports \
  --query "Exports[?Name=='StocksApp-ClusterArn'].Value" \
  --output text)

aws cloudformation deploy \
  --stack-name stocks-stepfunctions-phase-d \
  --template-file template-step-functions-phase-d.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides ECSClusterArn=$CLUSTER_ARN
```

### Test
```bash
# List state machines
aws stepfunctions list-state-machines

# Get state machine ARN
STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines \
  --query 'stateMachines[?name==`DataLoadingStateMachine`].stateMachineArn' \
  --output text)

# Trigger execution
aws stepfunctions start-execution \
  --state-machine-arn $STATE_MACHINE_ARN \
  --input '{"test": true}' \
  --name "manual-test-$(date +%s)"

# Monitor execution
aws stepfunctions get-execution-history \
  --execution-arn <execution-arn> \
  --query 'events[*].[type,executionFailedEventDetails]'
```

### Expected Results
- Full pipeline execution: 10-15 minutes
- Automatic retry on failure: 2-3 attempts with exponential backoff
- Proper dependency ordering: Symbols → Prices → Signals → Scores
- Error visibility: Each stage can fail independently

### Monitor
```bash
# CloudWatch Logs
aws logs tail /stepfunctions/data-loading-pipeline --follow

# Step Functions metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionTime \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum
```

---

## Phase E: Smart Incremental Loading & Caching

### Deploy
```bash
aws cloudformation deploy \
  --stack-name stocks-phase-e-incremental \
  --template-file template-phase-e-dynamodb.yml \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides Environment=prod
```

### Verify
```bash
# Check DynamoDB table
aws dynamodb list-tables | grep loader_execution_metadata

# Check S3 cache bucket
aws s3 ls s3://stocks-app-data/cache/ --recursive | head -10

# View execution metadata
aws dynamodb scan --table-name loader_execution_metadata
```

### Expected Results
- Cache hits within 24h (no API calls)
- Incremental processing for 1-7 day window (only changed symbols)
- Full refresh if >7 days since last run
- 5x reduction in API calls (80% fewer)

### Monitor
```bash
# DynamoDB metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedWriteCapacityUnits \
  --table-name loader_execution_metadata \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum

# View cache efficiency
aws logs insights query \
  --log-group-name /phase-e/incremental-loading \
  --query-string 'fields @message | filter @message like /cache_efficiency/'
```

---

## EventBridge Scheduling

### Deploy
```bash
# Get Phase D state machine ARN
STATE_MACHINE_ARN=$(aws cloudformation describe-stack-resource \
  --stack-name stocks-stepfunctions-phase-d \
  --logical-resource-id DataLoadingStateMachine \
  --query 'StackResourceDetail.PhysicalResourceId' --output text)

# Deploy scheduling
aws cloudformation deploy \
  --stack-name stocks-pipeline-scheduling \
  --template-file template-eventbridge-scheduling.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    StateMachineArn=$STATE_MACHINE_ARN \
    ScheduleTime='cron(0 2 * * ? *)' \
    Environment=prod
```

### Configuration Options

#### Daily Execution (Default)
```
cron(0 2 * * ? *)  → 2 AM UTC every day
```

#### Twice Daily
```
cron(0 2,14 * * ? *)  → 2 AM and 2 PM UTC
```

#### Weekdays Only
```
cron(0 2 ? * MON-FRI *)  → 2 AM UTC Mon-Fri
```

#### Every 6 Hours
```
rate(6 hours)  → Every 6 hours
```

### Manual Trigger
```bash
# Trigger pipeline immediately
aws events put-events \
  --entries '[{
    "Source": "custom.dataLoading",
    "DetailType": "ExecutePipeline",
    "Detail": "{}"
  }]' \
  --region us-east-1
```

---

## Complete End-to-End Test

### Step 1: Verify All Components
```bash
./test-phase-integration.sh
# Should output: ALL TESTS PASSED ✓
```

### Step 2: Deploy All Phases
```bash
# Run all deployment commands above
# Should see: ✓ Stack status: CREATE_COMPLETE or UPDATE_COMPLETE
```

### Step 3: Test Phase C (Lambda)
```bash
# Push a change to trigger the workflow
git commit --allow-empty -m "Test Phase C"
git push

# Watch GitHub Actions
gh run list --limit 1  # Get latest run
gh run view <run-id>   # Watch execution
```

### Step 4: Test Phase D (Step Functions)
```bash
# Manually execute state machine
aws stepfunctions start-execution \
  --state-machine-arn <arn> \
  --input '{"test": true}' \
  --name "test-run-$(date +%s)"

# Wait for completion (should take 10-15 min)
# Check CloudWatch Logs for detailed execution
```

### Step 5: Verify Metrics
```bash
# Phase A: Check S3 COPY in logs
aws logs tail /ecs/ --follow | grep "copy\|COPY"

# Phase C: Check Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=buyselldaily-orchestrator \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Average,Maximum

# Phase D: Check state machine execution time
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionTime \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Average,Maximum

# Phase E: Check cache efficiency
aws dynamodb scan --table-name loader_execution_metadata \
  --projection-expression "loader_name,last_execution_time"
```

---

## Rollback Procedures

### Rollback Phase A (ECS)
```bash
# Disable S3 staging (revert to INSERT)
# Edit template-app-ecs-tasks.yml: set USE_S3_STAGING=false
aws cloudformation update-stack \
  --stack-name stocks-ecs-tasks-stack \
  --template-body file://template-app-ecs-tasks.yml
```

### Rollback Phase C (Lambda)
```bash
# Delete Lambda stack
aws cloudformation delete-stack --stack-name stocks-lambda-phase-c

# Loaders will continue using ECS (slower but functional)
```

### Rollback Phase D (Step Functions)
```bash
# Delete Step Functions stack
aws cloudformation delete-stack --stack-name stocks-stepfunctions-phase-d

# Loaders can be triggered manually or via GitHub Actions
```

### Rollback Phase E (Caching)
```bash
# Delete DynamoDB and caching infrastructure
aws cloudformation delete-stack --stack-name stocks-phase-e-incremental

# Loaders will process all data on every run (no cache benefits)
```

---

## Troubleshooting

### Problem: Phase C Lambda times out (>15 min)
```bash
# Check if all 100 workers are being invoked
aws logs tail /aws/lambda/buyselldaily-orchestrator | grep "Invoked\|invoke"

# Check for errors in worker logs
aws logs tail /aws/lambda/buyselldaily-worker --follow

# Solution: Increase Lambda timeout or reduce batch size
aws lambda update-function-configuration \
  --function-name buyselldaily-orchestrator \
  --timeout 900  # 15 minutes
```

### Problem: Phase D Step Functions fails
```bash
# Get execution history
aws stepfunctions get-execution-history \
  --execution-arn <arn> \
  --query 'events[?type==`ExecutionFailed`]'

# Check specific task failure
aws cloudwatch get-log-events \
  --log-group-name /stepfunctions/data-loading-pipeline

# Solution: Fix the failing task, retry from Step Functions
```

### Problem: Phase E cache not being used
```bash
# Check DynamoDB metadata
aws dynamodb scan --table-name loader_execution_metadata

# Check S3 cache exists
aws s3 ls s3://stocks-app-data/cache/ --recursive

# Solution: Manually update DynamoDB with last execution time
aws dynamodb put-item \
  --table-name loader_execution_metadata \
  --item '{"loader_name":{"S":"pricedaily"},"last_execution_time":{"S":"2026-05-02T21:30:00Z"}}'
```

### Problem: GitHub Actions workflow not triggering
```bash
# Check workflow status
gh workflow list

# Verify trigger paths
grep "paths:" .github/workflows/deploy-app-stocks.yml

# Manually trigger workflow
gh workflow run deploy-app-stocks.yml \
  --ref main \
  --raw-field loaders=pricedaily
```

---

## Performance Targets & SLOs

### Execution Time
| Phase | Target | Tolerance |
|-------|--------|-----------|
| **A** | 3x faster | ±30% |
| **C** | 7 min | ±1 min |
| **D** | 15 min total | ±5 min |
| **E** | -15% (caching) | ±10% |
| **Combined** | 20 min | ±5 min |

### Cost
| Component | Target | Current | Savings |
|-----------|--------|---------|---------|
| **Compute** | -70% | Spot active | ✓ |
| **RDS** | -20% | S3 COPY active | ✓ |
| **API** | -10% | Phase E ready | ✓ |
| **Total** | -88% | Tracking | TBD |

### Reliability
| Metric | Target | Success Criteria |
|--------|--------|------------------|
| **Error Rate** | <0.1% | <1 error per 1000 runs |
| **Retry Success** | >99% | Automatic recovery works |
| **Cache Hit** | >80% | API calls reduced 5x |
| **Uptime** | 99.9% | <43 min downtime/month |

---

## Contact & Support

For issues or questions:

1. Check `STATUS_LIVE.md` for current status
2. Review `PHASE_INTEGRATION.md` for architecture details
3. Check `test-phase-integration.sh` for validation
4. Review CloudWatch Logs for error details
5. Check GitHub Actions workflow runs for deployment issues

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-02 | 1.0 | Initial deployment guide |
| | | All 5 phases (A-E) implemented |
| | | EventBridge scheduling ready |
| | | SLOs and rollback procedures documented |

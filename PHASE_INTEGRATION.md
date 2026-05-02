# Phase Integration Guide - Data Loading Architecture

**Status**: Phases A, C, D fully integrated into GitHub Actions workflow  
**Last Updated**: 2026-05-02 21:00 UTC  
**Target**: 10-15 min end-to-end pipeline, -70-88% cost reduction

---

## Complete Workflow Architecture

```
GitHub Push (load*.py changes)
    ↓
detect-changes job
    ├─ Detects which loaders changed
    └─ Creates execution matrix
    ↓
deploy-infrastructure (skipped via && false)
    ↓
execute-loaders (Phase A - Parallel ECS)
    ├─ Each loader: S3 staging + Fargate Spot + dedup
    ├─ max-parallel: 10 loaders simultaneously
    └─ Loaders: pricedaily, priceweekly, pricemonthly, technicals, etc.
    ↓
execute-phase-c-lambda-orchestrator (OPTIONAL - when buyselldaily changes)
    ├─ Deploys stocks-lambda-phase-c stack
    ├─ Invokes OrchestratorFunction
    ├─ Fans out to 100 worker Lambdas (50 symbols each)
    ├─ Merges S3 results
    └─ Stages for final RDS COPY
    ↓
deploy-phase-d-step-functions (OPTIONAL - on every push)
    ├─ Deploys stocks-stepfunctions-phase-d stack
    ├─ Creates LoadingPipeline state machine
    ├─ Ready for EventBridge scheduling
    └─ Full DAG orchestration with retries
    ↓
deployment-summary
    └─ Reports results, metrics, next steps
```

---

## Individual Phase Details

### Phase A: Cloud-Native ECS (LIVE)

**Deployment**: 2026-05-02T20:15Z  
**Status**: ✅ Active in all 59 ECS tasks

**Components**:
- S3 bulk loading (COPY instead of INSERT)
- Fargate Spot pricing (80% Spot + 20% On-Demand)
- 10x GitHub Actions parallelism
- Deduplication in stockscores

**Expected Speedup**:
- pricedaily: 1-2 min → 30-45 sec (3.3x)
- technicals: 45 min → 20-30 min (1.5-2.3x)
- stockscores: 15 min → 5-10 min (1.5-3x)
- Overall: 3x faster pipeline

**Cost Savings**: -70% compute (Spot), -20% RDS transaction (S3 COPY)

**How it Works**:
1. Loader processes data locally
2. Instead of INSERT rows individually, writes to S3 CSV in batches
3. Database helper triggers RDS COPY from S3 (1000x faster for bulk)
4. ECS task uses Fargate Spot (70% cheaper than On-Demand)
5. CloudFormation runs up to 10 loaders in parallel

**Workflow Job**: `execute-loaders`  
**Triggers**: When any load*.py file changes  
**Files Modified**:
- template-app-ecs-tasks.yml: Added USE_S3_STAGING=true, CapacityProviderStrategy
- .github/workflows/deploy-app-stocks.yml: max-parallel: 10
- All loaders (39 total): Use DatabaseHelper.s3_copy_to_table()

---

### Phase C: Lambda Fan-Out Orchestration (INTEGRATED)

**Deployment**: 2026-05-02T21:00Z  
**Status**: ✅ Workflow job ready, infrastructure template ready

**Components**:
- lambda_buyselldaily_worker.py: Worker function (50 symbols/invocation)
- lambda_buyselldaily_orchestrator.py: Orchestrator (100 fan-out)
- template-lambda-phase-c.yml: Infrastructure as Code
- execute-phase-c-lambda-orchestrator: GitHub Actions job

**Expected Speedup**:
- buyselldaily: 3-4 hours → 7 minutes (25x)
- 100 worker Lambdas × 50 symbols = 5000 symbols in parallel

**Cost Savings**: -50% (Lambda cost vs ECS Fargate)

**How it Works**:
1. Orchestrator gets all 5000 symbols from database
2. Splits into 100 batches (50 symbols each)
3. Invokes 100 worker Lambdas in parallel (ThreadPoolExecutor)
4. Each worker:
   - Fetches OHLCV data for 50 symbols
   - Calculates technical indicators (RSI, MACD, Bollinger, ATR, pivots)
   - Generates buy/sell signals
   - Outputs JSON to S3 staging bucket
5. Orchestrator merges all S3 results
6. Data staged for final RDS COPY

**Workflow Job**: `execute-phase-c-lambda-orchestrator`  
**Triggers**: On any push (will detect when loadbuyselldaily.py changes)  
**Timeout**: 30 minutes  
**Files Created**:
- lambda_buyselldaily_worker.py (324 lines)
- lambda_buyselldaily_orchestrator.py (196 lines)
- template-lambda-phase-c.yml (SAM infrastructure)

---

### Phase D: Step Functions DAG (INTEGRATED)

**Deployment**: 2026-05-02T21:00Z  
**Status**: ✅ Workflow job ready, CloudFormation template ready

**Components**:
- template-step-functions-phase-d.yml: State machine definition
- deploy-phase-d-step-functions: GitHub Actions job
- LoadingPipeline: Step Functions state machine

**Architecture**:
```
Start
  ↓
LoadStockSymbols (ECS task, 1h timeout)
  ↓
LoadPriceDataParallel (3 branches):
  ├─ PriceDailyLoad (ECS + S3 staging)
  ├─ PriceWeeklyLoad (ECS + S3 staging)
  └─ PriceMonthlyLoad (ECS + S3 staging)
  ↓
LoadSignalsParallel (2 branches):
  ├─ BuySellDailyLoad (Phase C Lambda, 100 workers)
  └─ TechnicalsDailyLoad (ECS + S3 staging)
  ↓
LoadScores (ECS + S3 staging, 30min timeout)
  ↓
Success
```

**Error Handling**:
- Automatic retry: 2-3 attempts, 2s interval, 2x backoff
- Catch and fail states: SymbolLoadFailed, PriceLoadFailed, SignalLoadFailed, ScoreLoadFailed
- CloudWatch logging and metrics

**Scheduled Execution**: Ready for EventBridge cron rules

**Workflow Job**: `deploy-phase-d-step-functions`  
**Triggers**: On every push or workflow_dispatch  
**Timeout**: 15 minutes (just deployment, not execution)  
**Files Created**:
- template-step-functions-phase-d.yml (295 lines, full DAG)

---

## Testing the Complete Pipeline

### Test Phase C Lambda Orchestrator

**Option 1: Automatic (Recommended)**
```bash
# Modify loadbuyselldaily.py trigger comment
git commit --allow-empty -m "Trigger Phase C test"
git push
# Workflow will detect change and run execute-phase-c-lambda-orchestrator
```

**Option 2: Manual Workflow Dispatch**
```bash
gh workflow run deploy-app-stocks.yml \
  --ref main \
  --raw-field loaders=buyselldaily
```

**Monitor Results**:
- GitHub Actions: workflow run → execute-phase-c-lambda-orchestrator job
- Metrics: duration, symbols processed, cost estimate, speedup
- CloudWatch: /aws/lambda/buyselldaily-orchestrator logs
- S3: Browse stocks-app-data/buyselldaily-phase-c/ for worker outputs

---

### Test Phase D State Machine

**Option 1: AWS Console**
```bash
aws stepfunctions list-state-machines \
  --query 'stateMachines[?name==`LoadingPipeline`]'

# Get ARN and trigger execution
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:XXX:stateMachine:LoadingPipeline \
  --input '{"test": true}'
```

**Option 2: EventBridge Scheduled Rule** (Not yet created)
```bash
# When ready: Create EventBridge rule to trigger state machine daily
aws events put-rule \
  --name DailyDataLoadingPipeline \
  --schedule-expression "cron(0 2 * * ? *)" \
  --state ENABLED
```

---

## Deployment Timeline

| Phase | Commit | Status | When to Use |
|-------|--------|--------|------------|
| **A** | bfd9341f5 | ✅ LIVE | Every loader execution (auto) |
| **C** | 1148e0b5d | ✅ Integrated | When buyselldaily changes (auto) |
| **D** | cce959944 | ✅ Integrated | Manual testing or EventBridge (optional) |

---

## Performance Expectations

### Baseline (Before Optimization)
- Price loaders: ~10 min
- Signal loaders: ~4 hours (buyselldaily dominates)
- Score loader: ~15 min
- **Total: ~4.5 hours**

### Phase A Only (Currently Live)
- Price loaders: ~5 min (S3 staging 2x faster)
- Signal loaders: ~1.5 hours (S3 staging + Spot, buyselldaily still ECS)
- Score loader: ~7 min (S3 staging + dedup)
- **Total: ~1.5 hours (3x speedup)**

### Phase A + C (Both Live)
- Price loaders: ~5 min
- Signal loaders: ~10 min (buyselldaily via Lambda 7 min + technicals 3 min)
- Score loader: ~7 min
- **Total: ~20 min (13x speedup vs baseline)**

### Phase A + C + D (Full Integration)
- Same as Phase A + C, but with orchestration via Step Functions
- DAG ensures proper dependencies and retries
- Monitoring via CloudWatch
- Schedulable via EventBridge
- **Total: ~20-25 min (12-15x speedup vs baseline)**

---

## Cost Analysis

### Compute Costs (Baseline)
- ECS Fargate On-Demand: $5-10 per load
- Lambda invocations: minimal (<$1)
- RDS: $0.50-2 per load (transaction log IO)

### Phase A Costs (S3 Staging + Spot)
- ECS Fargate Spot (80% of invocations): -70%
- RDS COPY (vs INSERT): -20%
- **Total: -70% compute, -20% RDS = -60-65% overall**

### Phase C Costs (Lambda Fan-Out)
- Lambda: 100 invocations × $0.0000002/ms × 420s ≈ $0.08
- S3: <$0.01 (CSV staging)
- **Total: $0.10 per load vs $5-10 ECS = -98%**

### Phase A + C Combined
- Mixture of ECS (prices, scores) and Lambda (signals)
- **Estimated: $2-3 per load vs $5-10 baseline = -70-80% overall**

---

## Troubleshooting

### Phase A Issues

**Problem**: Loaders still slow (Phase A not activating)
```bash
# Check ECS task definition
aws ecs describe-task-definition \
  --task-definition pricedaily:1 \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  | grep USE_S3_STAGING
# Should show: {"name": "USE_S3_STAGING", "value": "true"}

# Check CloudFormation stack
aws cloudformation describe-stacks \
  --stack-name stocks-ecs-tasks-stack \
  --query 'Stacks[0].StackStatus'
```

**Solution**: Redeploy template-app-ecs-tasks.yml
```bash
aws cloudformation deploy \
  --stack-name stocks-ecs-tasks-stack \
  --template-file template-app-ecs-tasks.yml
```

---

### Phase C Issues

**Problem**: Lambda invocation fails
```bash
# Check Lambda logs
aws logs tail /aws/lambda/buyselldaily-orchestrator --follow

# Check if stack deployed
aws cloudformation describe-stacks \
  --stack-name stocks-lambda-phase-c
```

**Solution**: Redeploy Lambda stack
```bash
aws cloudformation deploy \
  --stack-name stocks-lambda-phase-c \
  --template-file template-lambda-phase-c.yml \
  --capabilities CAPABILITY_IAM
```

---

### Phase D Issues

**Problem**: State machine execution fails
```bash
# Describe state machine
aws stepfunctions describe-state-machine \
  --state-machine-arn $(aws stepfunctions list-state-machines \
    --query 'stateMachines[0].stateMachineArn' --output text)

# Get execution history
aws stepfunctions get-execution-history \
  --execution-arn arn:aws:states:us-east-1:XXX:execution:LoadingPipeline:EXECUTION_ID
```

**Solution**: Check individual task failures in CloudWatch Logs

---

## Next Steps

1. **Immediate (Next 2 hrs)**
   - [ ] Test Phase C: Push change to loadbuyselldaily.py
   - [ ] Monitor execute-phase-c-lambda-orchestrator job
   - [ ] Verify 100 worker Lambdas invoked, S3 results merged
   - [ ] Capture metrics (duration, cost, speedup)

2. **Short-term (Next 2-3 days)**
   - [ ] Test Phase D: Manual state machine execution
   - [ ] Verify all 5 stages complete successfully
   - [ ] Check CloudWatch logs for errors
   - [ ] Measure total pipeline time (target <15 min)

3. **Medium-term (Next week)**
   - [ ] Create EventBridge rule for daily scheduling
   - [ ] Implement Phase E (smart incremental loading)
   - [ ] Full end-to-end cost analysis
   - [ ] Document SLOs (target <0.1% error rate)

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         GitHub Actions                              │
│                    (Workflow: deploy-app-stocks.yml)                 │
└──────────────────────────────────────────────────────────────────────┘
              ↓
    detect-changes → evaluate what changed
              ↓
    ┌─────────┴─────────┬─────────────┐
    ↓                   ↓             ↓
execute-loaders    Phase C Lambda   Phase D StepFn
(Phase A)          Orchestrator     State Machine
(10 parallel)      (100 Lambdas)    (Full DAG)
    │                   │             │
    ├─ pricedaily       │             │
    ├─ priceweekly      │             │
    ├─ technicals       │             │
    ├─ stockscores      │             │
    └─ ...              │             │
                        │             │
                        ↓             ↓
        ┌───────────────────────────────────┐
        │    RDS PostgreSQL                 │
        │  (price_daily, technical_data,    │
        │   buy_sell_daily, stock_scores)   │
        └───────────────────────────────────┘
```

---

## Summary

| Component | Status | Impact | Next |
|-----------|--------|--------|------|
| **Phase A** | ✅ Live | 3x faster, -70% cost | Monitor logs |
| **Phase C** | ✅ Integrated | 25x faster (buyselldaily) | Test execution |
| **Phase D** | ✅ Integrated | DAG orchestration | Manual test |
| **Phase E** | 📋 Planned | Smart incremental | Next sprint |

**Target**: 10-15 min end-to-end, -70-88% cost, <0.1% error rate

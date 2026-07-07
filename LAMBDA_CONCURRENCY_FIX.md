# CRITICAL: Lambda Concurrency Limit Blocking Orchestrator

## Problem
The `algo-algo-dev` Lambda function has **Reserved Concurrent Executions = 5**, which is too low.

## Evidence
```
CloudWatch Metrics (last 1 hour):
- Throttles: 20, 29, 36, 8, 18 occurrences (continuous throttling)
- ConcurrentExecutions: Max 5.0 (reserved concurrency limit)
```

## Impact
- Orchestrator cannot run (gets throttled immediately)
- Dashboard remains empty (no fresh trades/positions generated)
- System appears "broken" even though infrastructure is sound

## Solution
**Increase Lambda Reserved Concurrency from 5 to 100+ (or set to account default)**

```bash
# To fix (requires AWS admin permissions):
aws lambda put-function-concurrency \
  --function-name algo-algo-dev \
  --reserved-concurrent-executions 100 \
  --region us-east-1
```

## Verification
After fixing, run:
```bash
python3 scripts/orchestrator_scheduler.py --once --mode paper
```

Orchestrator should complete successfully and populate:
- ✅ New trades in algo_trades
- ✅ Positions in algo_positions  
- ✅ Portfolio snapshots
- ✅ Growth scores
- ✅ Dashboard data

## Who Can Fix
- AWS Account Owner
- AWS Admin with IAM Lambda permissions
- Anyone with `lambda:PutFunctionConcurrency` IAM action

## Session Impact
- All code fixes complete (credential manager, database schema, linting)
- All infrastructure operational (Lambda, RDS, API Gateway)
- **ONLY BLOCKER**: Reserved concurrency too low (AWS infrastructure limitation, not code issue)

## Why This Happened
Terraform deployment of provisioned concurrency failed (previous session error), and the Lambda reverted to minimal reserved concurrency (5).

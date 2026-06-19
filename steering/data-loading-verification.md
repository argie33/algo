# Data Loading Verification Guide

This guide shows how to verify that production data is loading completely with no gaps.

## Quick Start: Verify Current Production Data

### Option 1: Lambda Function (Fastest)

Invoke the data completeness verifier Lambda:

```bash
aws lambda invoke \
  --function-name algo-data-completeness-verifier \
  --region us-east-1 \
  output.json

# Check result
cat output.json
```

**Expected output for healthy data loading:**
```json
{
  "statusCode": 200,
  "result": "SUCCESS",
  "phase1_passes": true,
  "symbols": 5247,
  "coverage_percent": 98.5,
  "max_date": "2026-06-19"
}
```

**If data loading is broken:**
```json
{
  "statusCode": 200,
  "result": "FAILED",
  "phase1_halted": true,
  "reason": "symbols 3000 < 5000",
  "symbols": 3000,
  "coverage_percent": 56.2,
  "max_date": "2026-06-19"
}
```

### Option 2: Direct SQL Query (If you have RDS access)

```sql
SELECT
  (SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE - 1) as symbols_loaded,
  (SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE - 2) as symbols_prior,
  ROUND(100.0 * (
    (SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE - 1)::NUMERIC / 
    NULLIF((SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = CURRENT_DATE - 2), 0)
  ), 1) as coverage_pct,
  (SELECT MAX(date) FROM price_daily) as latest_date;
```

**Expected results:**
- `symbols_loaded` >= 5000 ✓
- `coverage_pct` >= 75% ✓
- `latest_date` = yesterday (trading day) ✓

### Option 3: ECS Diagnostic Task

Deploy and run the comprehensive diagnostic task:

```bash
# Deploy verification task definition (requires Terraform apply first)
terraform apply -target=module.data_verification

# Run verification task
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-data-completeness-verifier:1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --region us-east-1

# Get task ID from output, then check logs
aws logs tail /ecs/algo-data-completeness-verifier --follow
```

## Verify Loader Execution

### Check ECS Task History

```bash
# See recent task executions
aws ecs list-tasks --cluster algo-cluster --region us-east-1

# Check specific loader task
aws ecs describe-tasks \
  --cluster algo-cluster \
  --tasks arn:aws:ecs:us-east-1:xxx:task/algo-cluster/yyyy \
  --region us-east-1 \
  --query 'tasks[0].{status:lastStatus,exitCode:containers[0].exitCode,stoppedReason:stoppedReason}'
```

### Check CloudWatch Logs

```bash
# Tail loader logs in real-time
aws logs tail /ecs/algo-load_prices-loader --follow --region us-east-1

# Search for errors or specific patterns
aws logs filter-log-events \
  --log-group-name /ecs/algo-load_prices-loader \
  --filter-pattern 'ERROR' \
  --region us-east-1

# Check for successful loader completions
aws logs filter-log-events \
  --log-group-name /ecs/algo-load_prices-loader \
  --filter-pattern 'SUCCESS' \
  --region us-east-1
```

## Verify Phase 1 Passes

Phase 1 is the gatekeeper - if it fails, trading halts automatically.

### Check Phase 1 Execution

```bash
# Query orchestrator logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-algo-dev \
  --filter-pattern 'PHASE 1' \
  --region us-east-1

# Look for these success messages:
# "Phase 1 PASSED - data freshness verified"
# "Price coverage: XXX symbols (YY%)"

# Look for halt messages:
# "PHASE 1 HALTED - insufficient price coverage"
# "Price data stale"
```

## Understand Data Gaps

### Critical Gaps (Data Loading Blocked)
- Price data < 5000 symbols → Phase 1 halts ✓
- Price coverage < 75% vs prior day → Phase 1 halts ✓
- Price data > 1 trading day old → Phase 1 halts ✓

### Handled Gaps (No Trading Impact)
- FRED economic data partially missing → Supported data, doesn't halt
- Technical indicators < 70% → Backfilled after load
- Supporting tables stale → Warn only, doesn't halt

## What If Data Loading Is Broken?

### Symptom: Symbols < 5000

```sql
-- Check what went wrong
SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE - 1;  -- Should be >5000

-- Check if any symbols exist at all
SELECT COUNT(DISTINCT symbol) FROM price_daily;

-- Check for recent price data (look for dates)
SELECT DISTINCT date FROM price_daily ORDER BY date DESC LIMIT 10;
```

**Possible causes:**
1. **Loader never ran** → Check EventBridge rules and ECS task definitions
2. **Loader failed** → Check ECS task logs for errors
3. **yfinance API failures** → Check rate limiting or credentials
4. **RDS connection issues** → Check RDS proxy security groups

### Symptom: Coverage < 75%

This means prices for some symbols are missing for the recent date.

```sql
-- Compare coverage by date
SELECT 
  date, 
  COUNT(DISTINCT symbol) as symbol_count
FROM price_daily
WHERE date >= CURRENT_DATE - INTERVAL '3 days'
GROUP BY date
ORDER BY date DESC;
```

**Possible causes:**
1. **yfinance partial failure** → Some symbols failed, others succeeded
2. **Partial loader retry** → Loader restarted mid-execution
3. **RDS timeout** → Some inserts didn't complete

### Symptom: Data > 1 Day Old

```sql
-- Check when data was last loaded
SELECT MAX(date) FROM price_daily;

-- Check if it's a trading day
-- If it's Monday and max(date) is Friday → normal
-- If it's Thursday and max(date) is Monday → 3 day gap → BAD
```

**Possible causes:**
1. **Loader not scheduled** → Check EventBridge rules are enabled
2. **Orchestrator halted** → Phase 1 may be blocking due to other data gap
3. **Infrastructure down** → ECS cluster, RDS proxy, or Lambda issues

## Recovery Steps

### 1. Check Infrastructure

```bash
# Verify RDS proxy is healthy
aws rds-proxy describe-db-proxies --region us-east-1

# Verify ECS cluster
aws ecs describe-clusters --clusters algo-cluster --region us-east-1

# Check for CloudWatch alarms
aws cloudwatch describe-alarms --region us-east-1 --alarm-names '*algo*'
```

### 2. Manually Trigger Loader

```bash
# Run price loader immediately
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-load_prices-loader:latest \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --region us-east-1
```

### 3. Check Logs for Errors

```bash
# Get the task ARN from previous step output
# Then check logs
aws logs tail /ecs/algo-load_prices-loader --follow --region us-east-1
```

### 4. Verify Data Loaded

```bash
# Wait 5-10 minutes for loader to complete, then verify
aws lambda invoke \
  --function-name algo-data-completeness-verifier \
  --region us-east-1 \
  output.json

cat output.json
```

## CloudWatch Metrics to Monitor

After deployment, monitor these metrics:

```bash
# Price coverage metrics
aws cloudwatch get-metric-statistics \
  --namespace AlgoTrading \
  --metric-name PriceCoverage_Symbols \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --region us-east-1

# Phase 1 pass rate
aws cloudwatch get-metric-statistics \
  --namespace AlgoTrading \
  --metric-name Phase1_Pass \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average \
  --region us-east-1
```

## Verification Checklist

- [ ] Lambda `algo-data-completeness-verifier` returns `SUCCESS`
- [ ] Price symbols >= 5000
- [ ] Price coverage >= 75%
- [ ] Latest date is yesterday (trading day)
- [ ] ECS loader task exit code = 0
- [ ] No ERROR messages in CloudWatch logs
- [ ] Phase 1 logs show "PHASE 1 PASSED"
- [ ] Orchestrator continues past Phase 1 (not halted)

## Automated Verification

Set up daily verification:

```bash
# Deploy verification Lambda with EventBridge trigger
terraform apply -target=module.data_verification

# This will:
# 1. Run daily at 9:15 AM ET (after morning loader)
# 2. Check Phase 1 thresholds
# 3. Publish CloudWatch metrics
# 4. Create alarm if data is incomplete
```

Check alarm status:

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix "algo-data-completeness" \
  --region us-east-1
```

---

**Summary:** If Lambda returns `SUCCESS`, data is loading completely and Phase 1 will pass. Trading can proceed.

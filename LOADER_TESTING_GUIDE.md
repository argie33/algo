# AWS Loader & Orchestrator Testing Guide

## Overview

This guide explains how to fix and test the AWS data loaders and trading orchestrator. The key issues and solutions are:

1. **API Gateway 404 Error** — Fixed by adding explicit `$default` route
2. **Manual Loader Triggering** — Use helper scripts to test loaders in AWS
3. **Test with Friday Data** — Use `--run-date` parameter to simulate running on specific dates
4. **Monitor CloudWatch Logs** — Track execution and debug issues

---

## Quick Start (After Pushing to Main)

### 1. Verify Deployment

After pushing to main, GitHub Actions will deploy the fix automatically:

```bash
# Watch deployment progress
open https://github.com/argie33/algo/actions

# Or check via AWS CLI
aws logs tail /aws/lambda/algo-api-dev --follow
```

### 2. Test API Gateway

Once deployed, verify the API is responding:

```bash
# Get API endpoint
API_ENDPOINT=$(aws apigatewayv2 get-apis \
    --query 'Items[0].ApiEndpoint' \
    --output text)

# Test health endpoint
curl "$API_ENDPOINT/health"

# Expected response: {"status": "healthy"}
```

### 3. Verify Loaders Can Run

```bash
# Check if ECS cluster exists
./test-aws-loaders.sh

# Expected output shows:
# ✅ ECS Cluster: algo-cluster
# ✅ RDS Host: algo-db.*.us-east-1.rds.amazonaws.com
# ✅ API Lambda: algo-api-dev
# ✅ API Endpoint responding with 200
```

---

## Testing Loaders

### Manual Trigger (Any Loader)

```bash
# Trigger a specific loader
./trigger-loader-ecs.sh stock_prices_daily

# Other examples:
./trigger-loader-ecs.sh stock_symbols
./trigger-loader-ecs.sh signals_daily
./trigger-loader-ecs.sh algo_metrics_daily
```

This will:
1. Start the ECS task
2. Stream CloudWatch logs
3. Show execution status

### Monitor CloudWatch Logs

```bash
# Watch all loader logs
aws logs tail /ecs/algo-* --follow

# Watch specific loader
aws logs tail /ecs/algo-stock-prices-daily-loader --follow

# Get logs from last 24 hours
aws logs tail /ecs/algo-signals-daily-loader --since 24h
```

---

## Testing Orchestrator Locally

### Prerequisites

```bash
# Set database credentials (AWS Secrets Manager or env vars)
export DB_HOST=<host>
export DB_PORT=5432
export DB_USER=<user>
export DB_NAME=stocks
export DB_PASSWORD=<password>

# Set API credentials
export APCA_API_KEY_ID=<alpaca_key>
export APCA_API_SECRET_KEY=<alpaca_secret>
```

### Run with Specific Date (Friday Data)

```bash
# Run orchestrator for a specific date
./run-orchestrator-test.sh 2026-05-16

# Run for today (default)
./run-orchestrator-test.sh

# This will:
# 1. Check database connection
# 2. Load available data for that date
# 3. Run all 7 execution phases
# 4. Display results in console
# 5. Write audit log to database
```

### Check Results in Database

```bash
# View today's execution
psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<EOF
SELECT * FROM algo_audit_log
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC
LIMIT 100;
EOF

# View specific date
psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<EOF
SELECT * FROM algo_audit_log
WHERE DATE(created_at) = '2026-05-16'
ORDER BY created_at DESC
LIMIT 100;
EOF
```

### Check if Buys Triggered

```bash
# View trades for a specific date
psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<EOF
SELECT * FROM trades
WHERE DATE(created_at) = '2026-05-16'
ORDER BY created_at DESC;
EOF

# Count buys vs sells
psql -h $DB_HOST -U $DB_USER -d $DB_NAME <<EOF
SELECT 
  action,
  COUNT(*) as count,
  MIN(created_at) as first_trade,
  MAX(created_at) as last_trade
FROM trades
WHERE DATE(created_at) = '2026-05-16'
GROUP BY action;
EOF
```

---

## Full Data Loading Pipeline (AWS)

### Option 1: EventBridge Scheduled Loaders (Automatic)

These run on a schedule via EventBridge. They should start automatically:

- **3:30am ET** — Stock symbols
- **4:00am ET** — Daily price data (stocks + ETFs)
- **10:00am ET** — Financial statements
- **12:00pm ET** — Market & economic data
- **5:00pm ET** — Trading signals
- **Next day 5am UTC** — Bulk refresh + orchestrator

To monitor:

```bash
# Watch for loader invocations
aws logs tail /ecs/algo-stock-prices-daily-loader --follow
```

### Option 2: Manual Full Load (Testing)

```bash
# Load tier by tier, waiting for each to complete
aws ecs run-task \
    --cluster algo-cluster \
    --task-definition algo-stock-symbols-loader:1 \
    --launch-type FARGATE \
    --network-configuration awsvpcConfiguration="{subnets=[subnet-xxx],securityGroups=[sg-xxx]}"

# Then after symbols load:
aws ecs run-task \
    --cluster algo-cluster \
    --task-definition algo-stock-prices-daily-loader:1 \
    ...
```

---

## Troubleshooting

### Issue: "404 Not Found" on /api endpoints

**Fix:** Already applied via `$default` route in Terraform. Deploy with:

```bash
git push origin main
```

### Issue: Loader fails with "database unavailable"

**Check:**
```bash
# Verify RDS is accessible
aws rds describe-db-instances \
    --db-instance-identifier algo-db \
    --query 'DBInstances[0].DBInstanceStatus'

# Should show: "available"

# Test connection from bastion
aws ssm start-session --target <bastion-instance-id>
psql -h algo-db.*.us-east-1.rds.amazonaws.com -U stocks -d stocks
```

### Issue: "Rate limited" on API calls

**This is expected behavior.** The loaders handle rate limiting gracefully:
- They retry with backoff
- They use request queuing
- They parallelism is configured to stay within API limits

**To reduce rate limiting:**
- Reduce `LOADER_PARALLELISM` in ECS task definition
- Stagger loader start times
- Check Alpaca rate limits: `curl https://api.alpaca.markets/v2/account`

### Issue: Loader times out in ECS

**Check task definition timeout:**
```bash
aws ecs describe-task-definition \
    --task-definition algo-stock-prices-daily-loader:1 \
    --query 'taskDefinition.cpu, taskDefinition.memory' \
    --output text
```

**Increase if needed:**
- Edit `terraform/modules/loaders/main.tf`
- Increase `timeout` for the loader (in seconds)
- Redeploy: `git push origin main`

---

## Next Steps

1. **Deploy fixes:** `git push origin main`
2. **Wait for GitHub Actions:** Watch https://github.com/argie33/algo/actions
3. **Verify API:** `./test-aws-loaders.sh`
4. **Trigger test loader:** `./trigger-loader-ecs.sh stock_symbols`
5. **Run orchestrator locally:** `./run-orchestrator-test.sh 2026-05-16`
6. **Check audit logs:** Query `algo_audit_log` table
7. **Monitor CloudWatch:** `aws logs tail /ecs/algo-* --follow`

---

## Key Endpoints & Log Groups

| Component | Endpoint / Log Group | Purpose |
|-----------|---------------------|---------|
| API | `https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/health` | Health check |
| API Logs | `/aws/lambda/algo-api-dev` | API Lambda execution logs |
| Price Loader | `/ecs/algo-stock-prices-daily-loader` | Daily price fetching |
| Signals | `/ecs/algo-signals-daily-loader` | Buy/sell signal generation |
| Orchestrator | `/ecs/algo-algo-orchestrator` | Trading execution logs |
| Step Functions | AWS Console → Step Functions | EOD pipeline coordination |

---

## Manual Command Reference

### View ECS Task Definitions
```bash
aws ecs list-task-definitions --region us-east-1 --query 'taskDefinitionArns' --output text | tr '\t' '\n'
```

### Describe a Loader
```bash
aws ecs describe-task-definition \
    --task-definition algo-stock-prices-daily-loader \
    --query 'taskDefinition.containerDefinitions[0]' \
    --output json | jq '.environment, .secrets'
```

### Trigger Orchestrator in ECS
```bash
aws ecs run-task \
    --cluster algo-cluster \
    --task-definition algo-algo-orchestrator \
    --launch-type FARGATE \
    --network-configuration awsvpcConfiguration="{subnets=[subnet-xxx],securityGroups=[sg-xxx]}"
```

### View Audit Logs (SQL)
```sql
-- Latest orchestrator execution
SELECT * FROM algo_audit_log
ORDER BY created_at DESC LIMIT 1;

-- All executions for a date
SELECT * FROM algo_audit_log
WHERE DATE(created_at) = '2026-05-16'
ORDER BY phase, created_at;

-- Count execution results
SELECT 
  status, 
  COUNT(*) as count 
FROM algo_audit_log 
GROUP BY status;
```

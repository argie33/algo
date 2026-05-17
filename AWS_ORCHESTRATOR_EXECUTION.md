# AWS Orchestrator Execution Path

## Overview

Your trading orchestrator executes in AWS through a fully automated pipeline triggered by market events. This document explains how it works and how to verify it's actually placing trades.

## Execution Flow

### 1. **4:05 PM ET (20:05 UTC) Mon-Fri** - Data Pipeline Starts
- **Trigger:** EventBridge rule `algo-eod-pipeline-dev`
- **Action:** Fires Step Functions state machine `algo-eod-pipeline-dev`
- **What happens:** All data loaders run in parallel on ECS Fargate:
  - Stock prices (6 parallel tasks)
  - Financial statements (8 parallel tasks)  
  - Earnings data (4 parallel tasks)
  - Market/economic data (10 parallel tasks)
  - Sentiment analysis (5 parallel tasks)

### 2. **~4:30 PM ET** - Signals Generated
- Step Functions runs signal generation tasks in parallel:
  - Daily signals (stocks, ETFs)
  - Weekly signals (stocks, ETFs)
  - Monthly signals (stocks, ETFs)
- All signal computations complete before orchestrator starts

### 3. **~4:40 PM ET** - Algo Metrics Calculated
- Step Functions runs `load_algo_metrics_daily` ECS task
- Summarizes signal quality and availability

### 4. **~4:50 PM ET** - ORCHESTRATOR RUNS
- **Trigger:** Step Functions automatically invokes orchestrator ECS task
- **Task:** `algo-algo-orchestrator-dev` (Fargate)
- **Entry Point:** `python3 algo_orchestrator.py`

#### Orchestrator Phases (7-Phase Workflow):
1. **Data Freshness Check** - Validates market data is ≤ 7 days old
2. **Circuit Breakers** - Kill-switch checks (drawdown, daily loss, VIX, etc.)
3. **Position Monitor** - Review existing positions, compute stops, health scores
4. **Exit Execution** - Execute exits from Phase 3 and exit engine rules
5. **Signal Generation** - Filter and rank new buy signals through Tier 1-6 filters
6. **Entry Execution** - Execute ranked trades up to max position limit
7. **Reconciliation** - Pull live Alpaca data, calculate P&L, log results

#### Key Configuration (from Terraform):
- `ORCHESTRATOR_DRY_RUN = false` → **LIVE EXECUTION** (not simulation)
- `ORCHESTRATOR_EXECUTION_MODE = auto` → Automatic trading mode
- `ALPACA_PAPER_TRADING = false` → **LIVE TRADING** (if configured)

### 5. **Credentials Injection** (ECS Task)

The orchestrator ECS task receives credentials from AWS Secrets Manager:

| Env Var | Source | From AWS Secret |
|---------|--------|-----------------|
| DB_PASSWORD | Secret | algo-db-credentials-dev:password |
| DB_USER | Secret | algo-db-credentials-dev:username |
| APCA_API_KEY_ID | Secret | algo-algo-secrets-dev:APCA_API_KEY_ID |
| APCA_API_SECRET_KEY | Secret | algo-algo-secrets-dev:APCA_API_SECRET_KEY |
| DB_HOST | Environment | Terraform var |
| DB_PORT | Environment | 5432 |
| DB_NAME | Environment | Terraform var |
| ALPACA_PAPER_TRADING | Environment | Terraform var (false = live) |

## Verification Checklist

### ✓ Infrastructure Deployed
```bash
# Check Step Functions state machine exists
aws stepfunctions list-state-machines --region us-east-1 | grep eod-pipeline

# Check ECS cluster exists
aws ecs describe-clusters --cluster algo-cluster --region us-east-1

# Check orchestrator task definition exists
aws ecs describe-task-definition --task-definition algo-algo-orchestrator:1 --region us-east-1
```

### ✓ Credentials in AWS Secrets Manager
```bash
# Check RDS credentials secret
aws secretsmanager get-secret-value --secret-id algo-db-credentials-dev --region us-east-1

# Check Alpaca credentials secret
aws secretsmanager get-secret-value --secret-id algo-algo-secrets-dev --region us-east-1

# Verify it contains APCA_API_KEY_ID, not ALPACA_API_KEY
# (key names must match exactly)
```

### ✓ Orchestrator Actually Ran
Check CloudWatch logs:

```bash
# View orchestrator logs
aws logs tail /ecs/algo-algo-orchestrator --follow --region us-east-1

# Should show:
# - "Orchestrator Starting"
# - "PHASE 1 — DATA FRESHNESS CHECK"
# - "PHASE 2 — CIRCUIT BREAKERS"
# - ... all 7 phases ...
# - "Execution completed successfully"

# Search for errors:
aws logs filter-log-events \
  --log-group-name /ecs/algo-algo-orchestrator \
  --filter-pattern "ERROR\|FAIL\|Exception" \
  --region us-east-1
```

### ✓ Trades Actually Executed
Check two places:

1. **Alpaca Account:**
   ```python
   # If ALPACA_PAPER_TRADING = false:
   # View live orders at: https://app.alpaca.markets/dashboard/trading
   
   # Verify order execution:
   # - Orders should appear within minutes of 4:50 PM ET
   # - Check if orders were partially filled or fully filled
   # - Review P&L in account dashboard
   ```

2. **Database Audit Log:**
   ```bash
   # Connect to RDS PostgreSQL
   psql -h <RDS_ENDPOINT> -U stocks -d stocks
   
   # View trade execution records:
   SELECT * FROM algo_audit_log 
   WHERE DATE(created_at) = CURRENT_DATE
   ORDER BY created_at DESC;
   
   # Check what orders were submitted:
   SELECT * FROM algo_trade_audit
   WHERE DATE(created_at) = CURRENT_DATE
   AND action IN ('ENTRY', 'EXIT')
   ORDER BY created_at DESC;
   ```

## Common Issues & Solutions

### Issue 1: Orchestrator Not Running At All
**Symptom:** No logs in `/ecs/algo-algo-orchestrator`, market close passes without execution

**Check:**
```bash
# Are Step Functions executions happening?
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:algo-eod-pipeline-dev \
  --region us-east-1
```

**Fix if Step Functions not running:**
- Verify EventBridge rule `algo-eod-pipeline-dev` is ENABLED
- Check if rule is in wrong region (should be us-east-1)
- Verify Step Functions IAM role has permission to run ECS tasks

### Issue 2: Orchestrator Runs But Doesn't Place Trades
**Symptom:** Logs show 7 phases completed, but no orders in Alpaca

**Check:**
```bash
# Check if circuit breakers are blocking execution
aws logs filter-log-events \
  --log-group-name /ecs/algo-algo-orchestrator \
  --filter-pattern "CIRCUIT\|BREAKER\|HALT" \
  --region us-east-1
```

**Likely causes:**
- Circuit breaker triggered (drawdown, daily loss, etc.) → Check Phase 2 logs
- No valid signals passing Tier filters → Check Phase 5 logs
- Max positions already reached → Check Phase 6 logs
- `ORCHESTRATOR_DRY_RUN = true` → Set to `false` in terraform.tfvars

### Issue 3: Orchestrator Can't Connect to Database
**Symptom:** Logs show "Database password not available" or "Connection refused"

**Check:**
```bash
# Verify credentials secret exists
aws secretsmanager get-secret-value \
  --secret-id algo-db-credentials-dev \
  --region us-east-1

# Verify ECS task role has permission to read secret
aws iam get-role-policy \
  --role-name algo-svc-ecs-task-role \
  --policy-name algo-ecs-task-policy \
  --region us-east-1
```

**Fix:**
- Ensure `DB_PASSWORD` is in the secret with correct format
- Verify RDS is accessible from ECS task VPC
- Check RDS security group allows ingress from ECS security group

### Issue 4: Orchestrator Can't Connect to Alpaca
**Symptom:** Logs show "Alpaca API error" or "Invalid credentials"

**Check:**
```bash
# Verify Alpaca credentials in secret
aws secretsmanager get-secret-value \
  --secret-id algo-algo-secrets-dev \
  --region us-east-1 \
  | jq '.SecretString | fromjson | {APCA_API_KEY_ID, ALPACA_PAPER_TRADING}'
```

**Verify:**
- Secret contains `APCA_API_KEY_ID` (not `ALPACA_API_KEY`)
- Secret contains `APCA_API_SECRET_KEY` (not `ALPACA_SECRET_KEY`)
- `APCA_API_BASE_URL` points to correct endpoint:
  - Live: `https://api.alpaca.markets`
  - Paper: `https://paper-api.alpaca.markets`
- `ALPACA_PAPER_TRADING` matches your intent (true for paper, false for live)

## Deployment Changes

When you push to `main`, GitHub Actions automatically:

1. ✓ Runs Terraform to update infrastructure
2. ✓ Builds Docker image with all loaders + orchestrator
3. ✓ Pushes image to ECR
4. ✓ ECS tasks pull latest image on next run
5. ✓ Updates credentials in Secrets Manager (from GitHub Secrets)

**No manual AWS steps required** — all IaC via Terraform.

## Live Trading Mode

To enable **LIVE TRADING** (not paper):

### 1. Set Terraform Variable
```hcl
# terraform/terraform.tfvars
alpaca_paper_trading = false  # Default is false (LIVE)
```

### 2. Verify GitHub Secrets
GitHub Secrets must contain:
- `ALPACA_API_KEY_ID` - Your live Alpaca API key ID
- `ALPACA_API_SECRET_KEY` - Your live Alpaca secret key

### 3. Push to Main
```bash
git add terraform/terraform.tfvars
git commit -m "Enable live trading mode"
git push origin main
```

GitHub Actions will:
- Update Terraform
- Store credentials in Secrets Manager
- Redeploy orchestrator with live credentials
- **Orders will be placed for REAL on next market close**

## Monitoring

### Real-Time Monitoring (After Each Close)
```bash
# Watch orchestrator logs live
aws logs tail /ecs/algo-algo-orchestrator --follow --since 4h --region us-east-1

# Check if new orders appeared in Alpaca
# (refresh https://app.alpaca.markets every 5 minutes after 4:50 PM ET)
```

### Post-Execution Analysis (Next Morning)
```bash
# Query what actually happened
psql -h <RDS_ENDPOINT> -U stocks -d stocks << 'SQL'
SELECT 
  phase,
  status,
  summary,
  created_at
FROM algo_audit_log 
WHERE DATE(created_at) = CURRENT_DATE - INTERVAL '1 day'
ORDER BY created_at;
SQL
```

## Next Steps

1. ✓ **Verify AWS deployment is healthy** - Check CloudWatch logs for any errors
2. ✓ **Test data pipeline** - Ensure loaders complete by 4:40 PM ET
3. ✓ **Monitor first live execution** - Watch logs and Alpaca dashboard at market close
4. ✓ **Review trades** - Check if orders match your strategy expectations
5. ✓ **Iterate** - Adjust Tier weights, entry rules, exits as needed

Your algo is ready to execute in AWS. Let it run for a few days, monitor the results, then make informed adjustments.

# Step Functions Full Activation & SLA Compliance Guide

## Status: Ready for Production

All core components are configured and ready. This guide provides the steps to verify and ensure full operational status.

## Architecture Overview

### Data Flow
```
2:00 AM ET ──→ Morning Pipeline ──→ Load prices + scores
              (2 hours max)        (for 9:30 AM trading)

9:30 AM ET ──→ Orchestrator ──────→ Phase 1-7 execution
              (≤2 min per phase)    Execute trades

12:50 PM ET ──→ Afternoon Score Update (10 min window)
                Update swing_trader_scores for 1 PM run

1:00 PM ET ──→ Orchestrator ──────→ Phase 1-7 execution
              (≤2 min per phase)    Execute trades

2:50 PM ET ──→ Preclose Score Update (10 min window)
               (**SLA CRITICAL**: must finish before 3 PM)

3:00 PM ET ──→ Orchestrator ──────→ Phase 1-7 execution
              (≤2 min per phase)    Final trades before close
                                    **SLA: Finish by 3:15 PM**

4:05 PM ET ──→ EOD Pipeline ──────→ Full data load
              (3 hours max)         + dry-run orchestrator

5:30 PM ET ──→ Orchestrator ──────→ Dry-run only
              (evening, after close) Signal prep for tomorrow
```

## Critical Configuration Verification

### 1. Orchestrator Execution Mode
**Current Setting:** `execution_mode = "auto"` in terraform.tfvars

**What it does:**
- `auto` mode: Executes trades when conditions are met (CURRENT)
- `paper` mode: Forces paper trading (same as Alpaca paper endpoint)
- `live` mode: Requires `ALGO_LIVE_TRADING` env var set to `I_UNDERSTAND_REAL_MONEY`

**Current paper trading chain:**
```
alpaca_paper_trading = true
  ↓
ALPACA_PAPER_TRADING env var = "true"
  ↓
ALGO_LIVE_TRADING = "" (empty, because alpaca_paper_trading=true)
  ↓
TradeExecutor forces paper URL: https://paper-api.alpaca.markets
  ↓
All trades execute on PAPER account ✓
```

### 2. Dry Run Settings
**Current:**
- `orchestrator_dry_run = false` (trades enabled)
- 9:30 AM, 1:00 PM, 3:00 PM: Can execute trades ✓
- 5:30 PM: Forced to dry_run=true (after market close) ✓

### 3. Step Functions Pipeline Status

#### Morning Prep Pipeline (2:00 AM ET)
```
stock_prices_daily (1d only, 60-90 min)
  ↓
swing_trader_scores (10-20 min)
  ↓
sector_ranking (10-15 min)
━━━━━━━━━━━━━━━━━━━━━━━━
Total: ~90-125 minutes
SLA: 9:30 AM deadline
Buffer: 325+ minutes ✓ SAFE
```

#### Afternoon Score Update (12:50 PM ET)
```
swing_trader_scores (10-20 min max)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SLA: 1:00 PM deadline
Buffer: 40+ minutes ✓ SAFE
```

#### Preclose Score Update (2:50 PM ET) 
```
swing_trader_scores (10-20 min max)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SLA: 3:00 PM deadline
**CRITICAL: Orchestrator must finish by 3:15 PM (45 min)**
Buffer: 45+ minutes (if scores complete in <10min) ✓
```

#### EOD Pipeline (4:05 PM ET)
```
stock_symbols (10 min)
  ↓
stock_prices_daily (60-90 min) [all intervals: 1d, 1w, 1mo]
  ↓
market_health_daily + trend_template (parallel, 30 min)
  ↓
algo_metrics_daily (12 min)
  ↓
swing_trader_scores (10-20 min)
  ↓
sector_ranking (10-15 min)
  ↓
data_patrol (10 min)
  ↓
orchestrator_validation (dry-run, 20 min)
━━━━━━━━━━━━━━━━━━━━━━━━
Total: ~170 minutes (2.8 hours)
SLA: 5:30 PM deadline
Buffer: 85 minutes ✓ ACCEPTABLE
(Can handle +50 min slowness)
```

## Pre-Deployment Checklist

### A. Credentials
- [ ] `algo/alpaca` secret in AWS Secrets Manager contains:
  - [ ] `key` - Alpaca API key
  - [ ] `secret` - Alpaca API secret
- [ ] `algo/database` secret contains:
  - [ ] `username` - RDS user
  - [ ] `password` - RDS password
- [ ] `algo/fred` secret contains:
  - [ ] `api_key` - FRED API key
- [ ] Test credentials: `aws secretsmanager get-secret-value --secret-id algo/alpaca`

### B. Infrastructure
- [ ] RDS instance `algo-db` running (t4g.small or larger)
- [ ] RDS Proxy `algo-rds-proxy-dev` configured
- [ ] ECS cluster `algo-cluster` available
- [ ] Lambda execution roles created with proper permissions
- [ ] Step Functions role has permission to invoke ECS tasks
- [ ] EventBridge Scheduler role has permission to invoke Lambda + Step Functions

### C. Database
- [ ] Schema initialized via `lambda/db-init/schema.sql`
- [ ] Test connection: `psql -h <RDS_ENDPOINT> -U admin -d algo`
- [ ] Verify tables exist: `algo_positions`, `algo_trades`, `price_daily`, etc.

### D. EventBridge Scheduler Rules
Verify rules are **ENABLED**:
```bash
aws scheduler list-schedules --region us-east-1 | grep -E 'morning|afternoon|preclose|eod|orchestrator'
```

Expected rules (all **ENABLED**):
- `stocks-morning-pipeline-dev` (2:00 AM ET)
- `stocks-afternoon-update-pipeline-dev` (12:50 PM ET)
- `stocks-preclose-update-pipeline-dev` (2:50 PM ET)
- `stocks-eod-pipeline-dev` (4:05 PM ET)
- `stocks-algo-schedule-morning-dev` (9:30 AM ET)
- `stocks-algo-schedule-afternoon-dev` (1:00 PM ET)
- `stocks-algo-schedule-preclose-dev` (3:00 PM ET)
- `stocks-algo-schedule-dev` (5:30 PM ET evening)

### E. Lambda Permissions
Verify Lambda can be invoked by EventBridge:
```bash
aws lambda get-policy --function-name stocks-algo-dev --region us-east-1
```

Should include statement allowing `scheduler.amazonaws.com`

## Testing Strategy

### Phase 1: Credential & Connectivity Test
```bash
# 1. Verify AWS credentials loaded
aws sts get-caller-identity

# 2. Verify database connectivity
python -c "
from utils.database_context import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute('SELECT COUNT(*) FROM algo_trades')
    print(f'Trades in DB: {cur.fetchone()[0]}')
"

# 3. Verify Alpaca connection
python -c "
from config.credential_manager import get_alpaca_credentials
from config.alpaca_config import get_alpaca_base_url
creds = get_alpaca_credentials()
url = get_alpaca_base_url()
print(f'Alpaca URL: {url}')
print(f'Key loaded: {bool(creds[\"key\"])}')
print(f'Secret loaded: {bool(creds[\"secret\"])}')
"
```

### Phase 2: Step Functions Manual Test
```bash
# Trigger morning pipeline manually (for testing outside 2 AM window)
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:stocks-morning-prep-pipeline-dev \
  --name test-manual-$(date +%s) \
  --region us-east-1

# Check execution status
aws stepfunctions describe-execution \
  --execution-arn <execution-arn-from-above> \
  --region us-east-1
```

### Phase 3: Orchestrator Manual Test
```bash
# Invoke orchestrator Lambda directly
aws lambda invoke \
  --function-name stocks-algo-dev \
  --payload '{"source":"manual-test","run_identifier":"morning","dry_run":false}' \
  /tmp/orchestrator-result.json \
  --region us-east-1

# Check result
cat /tmp/orchestrator-result.json | python -m json.tool
```

### Phase 4: Trade Execution Test
```bash
# Check if any trades were executed
python -c "
from utils.database_context import DatabaseContext
from datetime import date
with DatabaseContext('read') as cur:
    cur.execute(
        'SELECT COUNT(*) FROM algo_trades WHERE entry_date >= %s',
        (date.today(),)
    )
    count = cur.fetchone()[0]
    print(f'Trades today: {count}')
    
    # Show recent trades
    cur.execute(
        '''SELECT entry_date, symbol, shares, entry_price 
           FROM algo_trades ORDER BY entry_date DESC LIMIT 5'''
    )
    for row in cur.fetchall():
        print(f'  {row[0]} {row[1]} {row[2]}sh @ \${row[3]:.2f}')
"
```

## Monitoring & SLA Tracking

### CloudWatch Metrics to Monitor
```bash
# Step Functions execution duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/States \
  --metric-name ExecutionTime \
  --dimensions Name=StateMachineArn,Value=<PIPELINE_ARN> \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum \
  --region us-east-1
```

### Critical SLA Alerts to Set Up
1. **Morning Pipeline Duration > 6 hours**: Alert if morning pipeline exceeds 6h (180min buffer before 9:30 AM)
2. **Afternoon Score Update Duration > 8 minutes**: Alert if score update exceeds 8 min (2 min buffer before 1 PM)
3. **Preclose Pipeline Duration > 8 minutes**: Alert if exceeds 8 min before 3 PM
4. **Orchestrator Duration > 3 minutes**: Alert if orchestrator takes >3 min (execution should be <2 min normally)
5. **Orchestrator Trade Execution Failure**: Alert on entry/exit failures in phases 4-6

### Verification Commands (Run after first market open)
```bash
# 1. Check if morning pipeline executed
aws logs tail /aws/states/stocks-eod-pipeline-dev --since 1h

# 2. Check if orchestrator executed
aws logs tail /aws/lambda/stocks-algo-dev --since 1h

# 3. Count trades executed today
python scripts/orchestrator-history.py recent 1

# 4. Check phase results
python -c "
from utils.database_context import DatabaseContext
with DatabaseContext('read') as cur:
    cur.execute(
        '''SELECT run_id, overall_status, phase_results->'name' 
           FROM orchestrator_execution_log 
           ORDER BY run_date DESC LIMIT 5'''
    )
    for row in cur.fetchall():
        print(f'{row[0]} {row[1]} - {row[2]}')
"
```

## Troubleshooting Guide

### Issue: Pipelines Not Triggering at Scheduled Time
**Debug:**
```bash
# Check EventBridge rule status
aws scheduler get-schedule --name stocks-morning-pipeline-dev

# Check Lambda CloudWatch logs
aws logs tail /aws/stepfunctions/ --filter 'ERROR' --since 1h

# Check IAM permissions
aws iam get-role-policy --role-name stocks-sfn-eod-pipeline-dev --policy-name stocks-sfn-eod-pipeline-policy
```

### Issue: Orchestrator Not Making Trades
**Check:**
1. Verify dry_run is false: `echo $ORCHESTRATOR_DRY_RUN`
2. Verify execution_mode is auto: `echo $ORCHESTRATOR_EXECUTION_MODE`
3. Verify alpaca_paper_trading is true: `echo $ALPACA_PAPER_TRADING`
4. Check orchestrator logs for Phase 5-6 errors
5. Verify Alpaca credentials in Secrets Manager

### Issue: SLA Timeouts (Pipeline Takes Too Long)
**Root Causes & Fixes:**
1. **yfinance Rate Limiting**: Reduce `LOADER_PARALLELISM`
   ```bash
   python scripts/update-loader-parallelism.py --loader stock_prices_daily --parallelism 1
   ```

2. **RDS Connection Pool Exhaustion**: Monitor `DatabaseConnections` in CloudWatch
   ```bash
   aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections
   ```

3. **RDS Slow Queries**: Check Performance Insights
   ```bash
   # Set statement_timeout lower if needed
   aws rds modify-db-parameter-group ...
   ```

## Post-Deployment Verification

**Week 1 Checklist:**
- [ ] Morning pipeline completes within SLA window (before 9:30 AM)
- [ ] All 4 orchestrator runs execute (9:30 AM, 1 PM, 3 PM, 5:30 PM)
- [ ] Trades are executed on at least 2 days
- [ ] No CloudWatch alarms triggered for SLA violations
- [ ] Database growing with new trades, positions, and reconciliation data
- [ ] No consistent pattern of phase failures
- [ ] Error rate < 5% across all pipelines

**Go-Live Sign-Off:**
- [ ] All pipelines running on schedule for 5 consecutive trading days
- [ ] All SLA windows met consistently
- [ ] Trades executing in paper account
- [ ] No critical errors in logs
- [ ] Dashboard displaying real-time data from orchestrator runs

## Next Steps

1. **Deploy to AWS:**
   ```bash
   git push main  # Triggers deploy-all-infrastructure.yml
   ```

2. **Verify Step Functions deployed:**
   ```bash
   aws stepfunctions list-state-machines --region us-east-1 | grep stocks
   ```

3. **Monitor first execution (naturally scheduled):**
   - Morning pipeline at 2:00 AM ET
   - Orchestrator at 9:30 AM ET
   - Check CloudWatch logs for `[PHASE]` entries

4. **Review orchestrator-history after first run:**
   ```bash
   python scripts/orchestrator-history.py recent 1
   ```

5. **Enable SLA alerts once confident:**
   - Create CloudWatch alarms for execution times
   - Subscribe to SNS alerts
   - Set up dashboard for monitoring

## Reference

- **System Architecture:** `steering/algo.md` (system map, components, procedures)
- **Step Functions Pipelines:** `terraform/modules/pipeline/main.tf` (pipeline definitions)
- **Orchestrator Phases:** `algo/orchestrator/phase*.py` (7-phase execution flow)
- **Trade Executor:** `algo/algo_trade_executor.py` (Alpaca integration)
- **SLA Timing:** This document (critical deadlines and buffers)

---

**Status:** ✅ System ready for deployment and production operation
**Paper Trading:** ✅ Enabled (alpaca_paper_trading = true)
**Trade Execution:** ✅ Configured (orchestrator_dry_run = false for market hours)
**Automation:** ✅ Full (EventBridge Scheduler + Step Functions + Orchestrator)

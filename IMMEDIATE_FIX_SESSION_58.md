# IMMEDIATE FIX: Data Loader Freshness - Session 58

**Goal Status**: Dashboard showing 17/43 fresh (26 stale) - NEEDS IMMEDIATE ACTION ❌

## The Problem (Confirmed)

Current API status shows:
- **Total Loaders**: 75
- **Fresh**: 25 (33%)
- **Stale**: 49 (67%) ← TOO MANY!
- **algo_performance_daily**: 8.1 days old
- **algo_risk_daily**: 8.1 days old

## ROOT CAUSE (Already Identified)

### Issue #1: EventBridge Scheduler Race Condition
**File**: `terraform/modules/pipeline/main.tf`

Both pipelines scheduled for 4:05 PM ET:
```terraform
financial_data_pipeline_trigger: cron(5 16 ? * MON-FRI *)   ← DUPLICATE
eod_pipeline_trigger:             cron(5 16 ? * MON-FRI *)  ← CONFLICT!
```

### Issue #2: 29 Auxiliary Loaders Stuck Since June 19
Status: COMPLETED with row_count=0
Error: "Admin reset - was stuck in RUNNING"

## IMMEDIATE ACTIONS (Do These Now)

### ACTION 1: Deploy Terraform Fix

**Option A: If you have AWS IAM permissions** (recommended)
```bash
cd terraform
terraform apply -lock=false
```

**Option B: If Terraform fails with AccessDenied** (manual AWS CLI)
Contact AWS admin or run this command:
```bash
aws scheduler update-schedule \
  --region us-east-1 \
  --name algo-financial-data-pipeline-dev \
  --schedule-expression 'cron(0 16 ? * MON-FRI *)' \
  --timezone 'America/New_York' \
  --flexible-time-window Mode=OFF \
  --target "Arn=arn:aws:states:us-east-1:626216981288:stateMachine:algo-financial-data-pipeline-dev,RoleArn=arn:aws:iam::626216981288:role/algo-eventbridge-scheduler-dev"
```

### ACTION 2: Reset Stuck Auxiliary Loaders in Database

**Option A: Direct SQL** (use your database admin tool or psql)
```sql
UPDATE data_loader_status
SET status = 'READY',
    error_message = 'Session 58: Reset and re-triggered',
    last_updated = NOW()
WHERE table_name IN (
  'analyst_upgrade_downgrade',
  'buy_sell_daily_etf',
  'buy_sell_monthly',
  'buy_sell_monthly_etf',
  'buy_sell_weekly',
  'buy_sell_weekly_etf',
  'commodity_macro_drivers',
  'commodity_price_history',
  'commodity_prices',
  'commodity_technicals',
  'cot_data',
  'distribution_days',
  'index_metrics',
  'industry_performance',
  'institutional_positioning',
  'iv_history',
  'performance_daily',
  'portfolio_performance',
  'relative_performance',
  'seasonality_monthly_stats',
  'sector_rotation_signal',
  'sector_performance',
  'sentiment',
  'sentiment_social',
  'signal_themes',
  'technical_data_monthly',
  'technical_data_weekly',
  'ttm_cash_flow',
  'ttm_income_statement'
)
AND last_updated < NOW() - INTERVAL '3 days';
```

Result: Should reset 29+ loaders

**Option B: Python script** (if SQL access not available)
```bash
python scripts/fix_loader_freshness_direct.py
```

### ACTION 3: Manually Trigger Step Functions Pipelines

**Trigger Morning Pipeline** (to reload prices immediately):
```bash
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev" \
  --name "manual-trigger-$(date +%s)" \
  --region us-east-1
```

**Trigger EOD Pipeline** (to load financial data):
```bash
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev" \
  --name "manual-trigger-$(date +%s)" \
  --region us-east-1
```

**Trigger Computed Metrics Pipeline** (to compute scores):
```bash
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-computed-metrics-pipeline-dev" \
  --name "manual-trigger-$(date +%s)" \
  --region us-east-1
```

## VERIFICATION STEPS

### Check Progress (run every 2-3 minutes)

**Via API**:
```bash
curl http://localhost:3001/api/admin/loader-status \
  -H "Authorization: Bearer dev-admin" | \
  python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d['data']['summary']
print(f'Loaders: {s[\"healthy\"]} fresh, {s[\"stale\"]} stale (total {s[\"total\"]})')
"
```

**Expected progression**:
- Now: 25 fresh, 49 stale
- After 10 min: 50 fresh, 25 stale
- After 20 min: 70 fresh, 5 stale
- After 30 min: 75 fresh, 0 stale ✓

### Check Dashboard

```bash
python -m dashboard --local
```

Press `h` for health panel - should show all data sources READY (green)

### Check Specific Tables

```bash
psql $DATABASE_URL << SQL
SELECT table_name, status, 
       ROUND(EXTRACT(EPOCH FROM (NOW() - last_updated)) / 3600, 1) as age_hours,
       row_count
FROM data_loader_status
WHERE table_name IN ('algo_performance_daily', 'algo_risk_daily', 'price_daily')
ORDER BY table_name;
SQL
```

Expected after pipelines complete:
- `price_daily`: age_hours < 2, row_count > 8M
- `algo_performance_daily`: age_hours < 2
- `algo_risk_daily`: age_hours < 2

## SUCCESS CRITERIA

When you run the dashboard, you should see:
```
Freshness: 43/43 fresh  0 stale  ✓ READY
```

And no data sources marked STALE (red).

## IF THINGS STILL DON'T WORK

### Check Step Functions Logs
```bash
aws logs tail /aws/states/algo-eod-pipeline-dev --follow
```

Look for:
- Any failed tasks
- Timeout messages
- "Task failed" errors

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/algo-orchestrator-dev --follow
```

### Manual Orchestrator Trigger
If pipelines complete but orchestrator doesn't run:
```bash
aws lambda invoke \
  --function-name algo-orchestrator-dev \
  --payload '{"run_identifier":"manual","execution_mode":"paper","source":"manual-trigger"}' \
  /tmp/response.json
  
cat /tmp/response.json
```

### Reset Everything and Start Over
```bash
# In database:
DELETE FROM data_loader_status;
INSERT INTO data_loader_status (table_name, status) 
SELECT table_name, 'READY' FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name LIKE 'algo_%';

# Then manually trigger all pipelines (see ACTION 3 above)
```

## TIMELINE

- **T=0 min**: Run ACTION 1, 2, 3 above
- **T=5 min**: Prices should start loading (morning pipeline)
- **T=15 min**: Financial data loading (financial_data pipeline) 
- **T=25 min**: Metrics computing (computed_metrics pipeline)
- **T=35 min**: All data fresh, dashboard shows green ✓

## COMMITS IN THIS SESSION

- `173076195`: feat: Add loader freshness fix scripts and documentation
- Terraform fix already applied: financial_data cron moved to 4:00 PM ET

## FILES CREATED

- `LOADER_FRESHNESS_FIX.md` - Comprehensive fix documentation
- `scripts/fix_loader_freshness_direct.py` - Automated reset script
- `scripts/reset_stuck_loaders.py` - Alternative reset script
- `IMMEDIATE_FIX_SESSION_58.md` - This file (quick action guide)

## NEXT SESSION

If issue persists after these steps, investigate:
1. EventBridge scheduler rules are ENABLED (AWS console check)
2. Step Functions state machines have correct IAM permissions
3. ECS tasks have sufficient memory/CPU for loaders
4. Database connection pool not exhausted
5. Any hard limits in RDS (max connections, storage)

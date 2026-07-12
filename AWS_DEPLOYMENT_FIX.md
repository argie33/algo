# AWS Deployment Sync Issue - Session 97

## Problem Identified

**AWS RDS is out of sync with local development database:**

| Metric | Local Database | AWS RDS |
|--------|---|---|
| Open Positions | 3 | 1 |
| Portfolio Value | $99,927.56 | $100,006.00 |
| Last Update | 2026-07-12 current | stale |

**Root Cause:** Orchestrator and data loaders run against local database only. AWS RDS is not being updated.

## Current Architecture Problem

```
LOCAL MODE (--local flag):
  Dashboard → dev_server (localhost:3001) → Local PostgreSQL

AWS MODE (no --local flag):
  Dashboard → API Gateway → Lambda → AWS RDS (STALE DATA)
```

**Issue:** Lambda returns data from RDS, but RDS hasn't been updated by orchestrator since it only runs locally.

## What's Working

- ✅ Lambda API is deployed and responding (200 OK)
- ✅ All endpoints accessible and returning data format correctly
- ✅ Cognito auth configured in Lambda environment
- ✅ Local database and orchestrator working perfectly
- ✅ Dashboard --local mode works flawlessly

## What's Not Working

- ❌ AWS RDS database is stale
- ❌ Orchestrator doesn't run against AWS RDS
- ❌ Data loaders don't push to AWS RDS
- ❌ Users accessing dashboard without --local flag get old data

## Required Fixes (In Priority Order)

### 1. **IMMEDIATE**: Configure Orchestrator to Run in AWS

**Current:** Orchestrator runs locally only  
**Need:** Orchestrator Lambda to execute via EventBridge schedule

**Check Status:**
```bash
# View orchestrator Lambda (if it exists)
aws lambda get-function --function-name algo-orchestrator --region us-east-1

# View EventBridge rules
aws events list-rules --region us-east-1 | grep -i orchestr
```

**Action:** 
- Ensure `algo-orchestrator` Lambda exists and is deployed
- Verify EventBridge schedules are configured (2:15 AM ET & 4:00 PM ET)
- Test: `aws lambda invoke --function-name algo-orchestrator --payload '{...}' response.json`

### 2. **CRITICAL**: Sync AWS RDS with Local Data

**Current:** AWS RDS has 1 position, local has 3  
**Action Required:** Update AWS RDS with current data

**Option A: Quick Sync (Manual)**
```bash
# Dump local database
pg_dump -h localhost -U stocks stocks > /tmp/local_dump.sql

# Restore to AWS RDS (requires credentials)
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com -U stocks stocks < /tmp/local_dump.sql
```

**Option B: Trigger Orchestrator in AWS**
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
# This should invoke algo-orchestrator Lambda which will update AWS RDS
```

### 3. **CRITICAL**: Fix Data Loader Targeting

**Current:** Loaders use local `DATABASE_URL` from environment  
**Need:** Loaders must support both local and AWS targeting

**Configuration needed in:**
- `loaders/runner.py` - default database selection
- `utils/db/context.py` - database context setup
- CI/CD pipeline - specify target database during deployment

**Example Fix:**
```python
# loaders/runner.py should check:
# 1. If LOCAL_MODE=true → use localhost
# 2. If running in Lambda → use AWS RDS (via Secrets Manager)
# 3. Otherwise → use DATABASE_URL env var
```

### 4. **ARCHITECTURE**: Enable Full AWS Pipeline

**Need to implement:**
```
EventBridge Scheduler (2x daily)
    ↓
algo-orchestrator Lambda
    ↓
Invokes Phase 1-8 (parallel + sequential)
    ↓
Loaders update AWS RDS
    ↓
API Lambda reads fresh data from RDS
    ↓
Dashboard displays current data
```

**Currently Missing:**
- Orchestrator not running automatically in AWS
- Loaders not syncing to AWS RDS
- No automatic data pipeline between local and AWS

## Dashboard AWS Mode Testing

### Current Behavior
```bash
# Without --local flag (tries AWS mode)
python3 -m dashboard

# Gets data from Lambda, but data is stale (from AWS RDS)
# Displays old portfolio state
```

### Expected Behavior After Fix
```bash
# Without --local flag (AWS mode)
python3 -m dashboard

# Gets fresh data from Lambda (from updated AWS RDS)
# Displays current portfolio state matching local
```

## Deployment Checklist for Full AWS

- [ ] Verify `algo-orchestrator` Lambda exists and is active
- [ ] Confirm EventBridge schedules are configured
- [ ] Test manual orchestrator trigger: `python3 scripts/trigger_orchestrator.py`
- [ ] Verify AWS RDS gets updated after orchestrator run
- [ ] Sync AWS RDS with current local data
- [ ] Test dashboard in AWS mode (no --local flag)
- [ ] Verify data freshness in Lambda responses
- [ ] Monitor CloudWatch logs for errors

## Files That Need Review/Update

1. **loaders/runner.py** - Database context selection
2. **utils/db/context.py** - Add AWS RDS support
3. **api-pkg/lambda_function.py** - Verify RDS connection
4. **terraform/modules/services/** - EventBridge + Orchestrator config
5. **scripts/trigger_orchestrator.py** - Already correct, just needs EventBridge trigger

## Next Steps for User

1. **Test AWS Orchestrator Manually:**
   ```bash
   python3 scripts/trigger_orchestrator.py --run morning --mode paper
   ```

2. **Monitor Execution:**
   ```bash
   aws logs tail /aws/lambda/algo-orchestrator --follow
   ```

3. **Verify Data Updated:**
   ```bash
   # Check if AWS RDS has new data after orchestrator runs
   psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com -U stocks stocks
   SELECT COUNT(*) FROM algo_positions WHERE status='open';  -- should show 3 (not 1)
   ```

4. **Test Dashboard in AWS Mode:**
   ```bash
   python3 -m dashboard
   # Should display fresh data from Lambda
   ```

## Summary

**System is functionally complete but architecturally split:**
- ✅ Local dev works perfectly
- ✅ AWS Lambda is deployed and responding
- ❌ AWS RDS is not being updated by orchestrator
- ❌ Dashboard AWS mode shows stale data

**Fix Priority:** Get orchestrator running in AWS → sync RDS → verify data pipeline works end-to-end.

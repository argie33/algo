# AWS Data Loading Issue - Session 111 Diagnosis

**Date:** 2026-07-13 11:50 UTC  
**Status:** CRITICAL - Dashboard showing "--" due to incomplete price data load

---

## Root Cause

The AWS price loader (`loadpricedaily`) in Step Functions is **failing after loading only 6 symbols** instead of the expected 10,500+ portfolio symbols.

### Evidence

```
Price Data for Today (2026-07-13):
  - Loaded: 6 symbols (GTERR, HAVAR, HSPTR, KTWOR, MCAHR, MCW)
  - Expected: 10,594 symbols
  - Completeness: 0.06%
  - Status: STALLED
```

### Why Dashboard Shows "--"

1. **Phase 1 Halts** → Insufficient price coverage (6 < 1000 minimum)
2. **Cascading Failure** → All downstream phases skipped
   - Phase 3: Technical indicators (skipped)
   - Phase 7: Signal generation (skipped)
   - Phase 8: Portfolio metrics (skipped)
3. **Dashboard Result** → Queries return empty data → displays "--"

---

## Current Data Status

### 🔴 CRITICAL
- `price_daily`: Only 6 symbols for today (was 10,458 on July 10)
- `technical_data_daily`: No data for July 11-13, last update July 10
- `algo_signals`: 0 signals generated (needs technical data)

### ⚠️ STALE
- `market_exposure_daily`: 6.8h old (missing July 11-13)

### ✅ FRESH
- `stock_scores`: Current as of 91 minutes ago

---

## Why AWS Loaders Incomplete

Possible causes (needs investigation):

1. **yfinance Rate Limit Hit**
   - Loaders hit API rate limits after 6 symbols
   - No retry/resumption logic
   - Fix: Implement batch backoff + state tracking

2. **Lambda Timeout**
   - Step Functions task timeout (default 60-300s)
   - Incomplete data insertion
   - Fix: Increase timeout + monitor CloudWatch logs

3. **VPC Cold-start Timeout**
   - Lambda cold-start takes 15-40s
   - API calls take 2-3s per symbol × 10,500 = 30,000s total
   - Fix: Use provisioned concurrency + parallel loaders

4. **Database Connection Error**
   - Connection to RDS fails mid-load
   - Data partially inserted
   - Fix: Add retry logic + connection pooling

---

## Verification Steps

### Check AWS Lambda Logs

```bash
# Find recent price loader executions
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-data-loader \
  --start-time $(date -d '3 hours ago' +%s)000 \
  --filter-pattern "loadpricedaily" \
  --region us-east-1

# Look for:
# - Rate limit errors (429, 403)
# - Timeout errors
# - Connection failures
# - Partial data indicators
```

### Check Step Functions Status

```bash
# List recent price loader executions
aws stepfunctions list-executions \
  --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-pipeline" \
  --max-items 5 \
  --region us-east-1 \
  --query 'executions[?contains(name, `loadpricedaily`)]'

# Get details of latest execution
aws stepfunctions describe-execution \
  --execution-arn "arn:..." \
  --region us-east-1
```

---

## Recovery Options

### Option 1: Trigger Complete Local Load (Immediate)

```bash
# Clear incomplete today's data
python -c "
import psycopg2
conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()
cur.execute('DELETE FROM price_daily WHERE date = CURRENT_DATE')
conn.commit()
cur.close()
"

# Load prices from cache/backup
python scripts/load_prices_from_backup.py --date 2026-07-13

# Run orchestrator to complete pipeline
python scripts/run_local_orchestrator.py --morning
```

### Option 2: Trigger AWS Step Functions Manually

```bash
# After fixing the step function / increasing timeout
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-pipeline" \
  --name "manual-complete-load-$(date +%s)" \
  --region us-east-1

# Monitor execution
watch -n 5 'aws stepfunctions describe-execution \
  --execution-arn "arn:..." \
  --region us-east-1 \
  --query "{status: status, progress: progress}"'
```

### Option 3: Implement Incremental Loading

Create a fallback loader that:
1. Loads symbols in smaller batches
2. Saves progress to database
3. Resumes from last successful batch on retry
4. Avoids rate limit hits with adaptive backoff

---

## Dashboard Recovery

Once price data is complete:

```bash
# 1. Verify data is fresh
python scripts/monitor_data_staleness.py

# 2. Verify orchestrator completes
python scripts/run_local_orchestrator.py --morning

# 3. Dashboard will auto-show data
python -m dashboard --local
```

Expected timeline:
- Data load: 5-10 minutes
- Orchestrator: 2-3 minutes  
- Dashboard refresh: automatic

---

## Long-term Fixes

1. **Increase Lambda timeout** from 300s → 900s (15 min)
2. **Enable provisioned concurrency** (2-5 units) to eliminate cold starts
3. **Implement batch checkpointing** in price loader
4. **Add adaptive rate limiting** with exponential backoff
5. **Monitor CloudWatch metrics** for failures
6. **Add alerting** when loader covers < 50% of symbols

---

## Questions for User

1. Are there yfinance API errors in CloudWatch logs?
2. Has Step Functions been triggering successfully at 2 AM / 4 PM?
3. Are there recent AWS infrastructure changes (VPC, security groups, IAM)?
4. Should we switch to a different data provider (Alpaca, etc.)?

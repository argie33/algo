# IMMEDIATE NEXT STEPS - Fix BLOCK-006

**Current Time:** 2026-06-14  
**Issue:** Data loaders hanging/failing. Last successful run: June 12 (2 days ago)  
**Impact:** System in degraded mode. Traders receiving stale signals (124+ hours old).

---

## What We Know
1. ✓ Infrastructure deployed correctly (Lambda, ECS, Step Functions, EventBridge)
2. ✓ Schedulers are ENABLED and firing on schedule
3. ✓ Database connection working (23/500 connections, healthy RDS Proxy)
4. ✗ Loaders are hanging or failing silently
5. ✗ No error logs indicating what's wrong (logs show no recent activity)

## What's Happening (Best Hypothesis)
The morning pipeline Step Function:
1. Fires at 2 AM ET (scheduler working)
2. Launches ECS task: `algo-stock_prices_daily-loader`
3. Task starts but **never completes or logs anything**
4. Manual test confirmed: task still running after 60+ seconds with no logs

**Most likely:** ECS task is hanging waiting for external API response

---

## THE FIX (Choose One)

### Option A: Test Hypothesis First (15 minutes)
```bash
# 1. SSH into an EC2 instance in the VPC (or use ECS Exec)
# 2. Run the loader manually with debug logging
aws ecs execute-command \
  --cluster algo-cluster-dev \
  --task algo-<task-id> \
  --container algo-stock_prices_daily-loader \
  --interactive \
  --command "/bin/bash"

# 3. Inside the container:
python3 -c "
import yfinance as yf
import time
print('Downloading AAPL...')
start = time.time()
data = yf.download('AAPL', start='2026-06-12', end='2026-06-14')
print(f'Done in {time.time()-start:.2f}s')
"

# 4. If this hangs, the issue is yfinance/network
# If this works, issue is in the loader code itself
```

### Option B: Enable Debug Logging & Retry (30 minutes)
```bash
# 1. Modify ECS task definition to enable DEBUG logging
# 2. Set LOADER_TIMEOUT environment variable
aws ecs update-task-definition \
  --family algo-stock_prices_daily-loader \
  --container-definitions '[{"name":"algo-stock_prices_daily-loader","environment":[{"name":"LOG_LEVEL","value":"DEBUG"},{"name":"LOADER_TIMEOUT_SEC","value":"600"}]}]'

# 3. Manually trigger loader
aws ecs run-task \
  --cluster algo-cluster-dev \
  --task-definition algo-stock_prices_daily-loader:latest \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-...],securityGroups=[sg-...],assignPublicIp=ENABLED}"

# 4. Wait 10-15 minutes, check logs
aws logs tail /ecs/algo-stock_prices_daily-loader --follow
```

### Option C: Bypass Loaders Temporarily (5 minutes - NOT RECOMMENDED)
**Only do this if you need the system running TODAY while investigating**
```bash
# 1. Fetch latest data from backup/cache
# 2. Insert into database manually
# 3. Update API health check to show "degraded" instead of "stale"
# 4. Fix loaders in parallel (don't leave in this state!)
```

---

## MOST LIKELY ROOT CAUSES (In Priority Order)

### 1. yfinance API Is Slow/Rate Limited (Probability: 60%)
**Signs:** Loader works for first 100 symbols, then hangs  
**Fix:**
```python
# In load_prices.py, modify yfinance initialization
import yfinance as yf

# Add timeout
yf.Ticker._get_timeseries = lambda self, start, end, **kwargs: \
  super(yf.Ticker, self)._get_timeseries(start, end, timeout=30, **kwargs)
  
# Add retry logic
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_batch(symbols):
    return yf.download(symbols, progress=False)
```

### 2. ECS Task Timeout (Probability: 30%)
**Signs:** Task completes partially, then killed by timeout  
**Check:**
```bash
# Get ECS task definition
aws ecs describe-task-definition \
  --task-definition algo-stock_prices_daily-loader \
  | jq '.taskDefinition.containerDefinitions[].stopTimeout'
# Should be >= 600 (10 min) or increase it
```

**Fix:**
```bash
# Update timeout in terraform/modules/loaders/main.tf
# ECS task definition stop_timeout parameter
resource "aws_ecs_task_definition" "stock_prices_daily" {
  stop_timeout = 900  # 15 minutes instead of current
}
```

### 3. RDS Connection Pool Exhaustion (Probability: 10%)
**Signs:** Loader hangs when trying to write data  
**Check:**
```bash
# Get current connections
psql -c "SELECT count(*) FROM pg_stat_activity;"

# If > 450, connections exhausted
# Get idle connections
psql -c "SELECT * FROM pg_stat_activity WHERE state='idle' AND query_start < NOW() - INTERVAL '5 minutes';"

# Kill idle connections
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle';"
```

**Fix:**
```bash
# Update terraform/modules/loaders/main.tf
# Increase RDS Proxy max_connections
max_connections = 100  # From 30-40 to 100
```

### 4. Missing Environment Variables (Probability: 5%)
**Fix:**
```bash
# Check ECS task has required env vars
aws ecs describe-task-definition \
  --task-definition algo-stock_prices_daily-loader \
  | jq '.taskDefinition.containerDefinitions[0].environment'

# Should include:
# LOADER_PARALLELISM=2
# LOADER_TIMEOUT_SEC=600
# DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
# FRED_API_KEY
# APCA_API_KEY_ID, APCA_API_SECRET_KEY
```

---

## Step-by-Step Fix Process

### Phase 1: Diagnose (Today - 1 hour)
1. Run Option A above (test yfinance directly)
2. Check if yfinance responds (should be <10 seconds)
3. If yfinance works → issue is in loader code
4. If yfinance hangs → issue is API/network
5. Document finding in `LOADER_DIAGNOSIS.md`

### Phase 2: Fix Root Cause (Today - 2-4 hours)
1. If yfinance hangs:
   - Add timeout to yfinance calls (30 second hard timeout)
   - Add retry logic with backoff
   - Add circuit breaker for persistent failures
   
2. If loader code hangs:
   - Enable DEBUG logging
   - Add timing/profiling info to identify where it hangs
   - Fix specific bottleneck
   
3. If RDS hangs:
   - Kill idle connections
   - Increase pool size
   - Add connection timeout

### Phase 3: Test Fix (Today - 30 minutes)
1. Manually trigger stock_prices_daily loader
2. Wait for completion (should be <5 minutes)
3. Verify data inserted: `SELECT MAX(date) FROM price_daily;`
4. Trigger full morning pipeline
5. Verify all loaders complete
6. Check API health: should show `"status": "healthy"`

### Phase 4: Re-Enable Automation (Today - 15 minutes)
1. Verify schedulers are still ENABLED
2. Wait for next scheduled run (2 AM ET next day)
3. Verify data updated
4. Set up CloudWatch alarm for stale data

---

## How to Monitor Fix Progress

```bash
# Check current data age (should be <24h)
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health | jq '.data.freshness.signal_age_hours'

# Check Step Function status in real-time
aws stepfunctions describe-execution \
  --execution-arn arn:aws:states:us-east-1:626216981288:execution:algo-morning-prep-pipeline-dev:TEST-$(date +%s) \
  | jq '{status:.status, startDate:.startDate}'

# Check ECS task logs
aws logs tail /ecs/algo-stock_prices_daily-loader --follow

# Check database
psql -c "SELECT MAX(date), COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;"
```

---

## Success Criteria
- [ ] Morning pipeline completes without hanging
- [ ] ECS task finishes in < 5 minutes
- [ ] Logs show successful data load
- [ ] Database has data from today (2026-06-14)
- [ ] API health returns "healthy" status
- [ ] Signal age < 24 hours
- [ ] Circuit breaker status updated today

---

## Files to Modify
- `loaders/load_prices.py` - Add timeout/retry logic
- `terraform/modules/loaders/main.tf` - Increase timeouts/pool size
- `utils/optimal_loader.py` - Add better error logging
- ECS task definitions - Enable debug logging

---

## Rollback Plan (If Fix Breaks Things)
```bash
# 1. Revert terraform changes
terraform revert

# 2. Restart services
aws ecs update-service --cluster algo-cluster-dev --service ... --force-new-deployment

# 3. Fall back to previous state
# Last known good state: June 12 morning pipeline run
```

---

## Questions to Answer Before Proceeding
1. Is yfinance API responding? (curl yfinance API directly)
2. Are ECS tasks actually starting? (check CloudWatch ECS metrics)
3. Are any loaders completing, or all hanging? (check database watermarks)
4. What's the error message in ECS logs? (not available now, but enable logging)

---

## DO NOT
- ❌ Manually insert fake data (traders will act on it)
- ❌ Disable data freshness checks (defeats purpose of monitoring)
- ❌ Keep system running in degraded mode long-term (risk to trading)
- ❌ Modify scheduling without testing first
- ❌ Leave debug logging enabled in production

## DO
- ✓ Document what you find (helps next time)
- ✓ Add monitoring/alerting for this issue
- ✓ Test fix before enabling for real runs
- ✓ Keep logs for post-mortem analysis

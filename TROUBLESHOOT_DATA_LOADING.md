# Data Loading Pipeline Troubleshooting

**Status:** EOD Pipeline FAILED (May 19, 2026 01:19:30 UTC)  
**Execution:** `arn:aws:states:us-east-1:626216981288:execution:algo-eod-pipeline-dev:auto-populate-1779152959`  
**Duration:** ~10 minutes  
**Error:** "One or more pipeline steps failed"

---

## How to Diagnose

### Step 1: Check Step Functions Execution History

Go to: https://console.aws.amazon.com/states/home?region=us-east-1

Find execution: `auto-populate-1779152959`

Look for:
- Which STEP failed (Tier 0? Tier 1? Tier 2?)
- What was the error message?
- Did it timeout, crash, or get throttled?

### Step 2: Check CloudWatch Logs

Go to: https://console.aws.amazon.com/cloudwatch/

Search for log groups matching:
- `/aws/lambda/` — Lambda function logs
- `/aws/ecs/algo-eod-pipeline/` — ECS Fargate task logs
- `algo-loaders` — Loader-specific logs

Look for:
```
ERROR
FAIL
Exception
TimeoutError
Connection refused
```

### Step 3: Identify the Failing Loader

Check `run-all-loaders.py` execution logs. Most likely failures:

| Loader | Common Failure | Fix |
|--------|---|---|
| `loadpricedaily.py` | yfinance timeout (VPC) | Increase timeout or use Alpaca API |
| `loadstockscores.py` | Database slow query | Add indexes to swing_trader_scores |
| `loadearningsrevisions.py` | yfinance missing data | Skip stocks with no earnings data |
| `load_technical_data_daily.py` | Missing price data | Ensure price_daily is populated first |
| `load_signal_quality_scores.py` | Tier dependency | Check buy_sell_daily exists |

---

## Common Failures & Solutions

### 1. **yfinance Timeout (Most Likely)**

**Symptom:**
```
TimeoutError: Function call exceeded 60s timeout
```

**Cause:** yfinance calls from AWS EC2/Lambda to Yahoo Finance are slow/unreliable in VPC

**Fix:**
```python
# In utils/data_source_router.py, line 191:
# Change:
hist = _call_with_timeout(do_download, timeout_sec=60)

# To:
hist = _call_with_timeout(do_download, timeout_sec=120)
```

Or use Alpaca API instead (if you have subscription):
```python
# In loaders/loadpricedaily.py, use Alpaca:
from utils.alpaca_service import AlpacaDataService
service = AlpacaDataService()
```

### 2. **Database Connection Error**

**Symptom:**
```
psycopg2.OperationalError: FATAL: remaining connection slots reserved for non-replication superuser connections
```

**Cause:** Too many connections, database limit reached

**Fix:**
- Check RDS security group allows traffic from Fargate
- Verify DB password correct in Secrets Manager
- Check Fargate task can reach RDS endpoint
- Reduce parallelism in `run-all-loaders.py`

```python
# In run-all-loaders.py, reduce workers:
('Tier 1: Price data (parallel)', tier_1_prices, 1),  # Was: 2
('Tier 2: Reference data (parallel)', tier_2_reference, 1),  # Was: 2
```

### 3. **Missing Table or Schema**

**Symptom:**
```
psycopg2.ProgrammingError: relation "price_daily" does not exist
```

**Cause:** Database schema not initialized

**Fix:**
```bash
# Run init_database.py in RDS:
python3 init_database.py \
  --db-host your-rds-endpoint.rds.amazonaws.com \
  --db-user stocks \
  --db-password $DB_PASSWORD
```

### 4. **Rate Limit (yfinance)**

**Symptom:**
```
HTTPError 429 Too Many Requests
```

**Cause:** Too many yfinance requests too fast

**Fix:**
```python
# In utils/algo_retry.py, add delay:
YFINANCE_LIMITER.max_calls = 5  # Reduce from 10
YFINANCE_LIMITER.time_period = 1  # Per second
```

### 5. **Out of Memory**

**Symptom:**
```
Process exited with code: 137
```

**Cause:** Fargate task doesn't have enough memory

**Fix:**
```bash
# In Terraform, increase Fargate memory:
memory = 2048  # Was: 1024
cpu = 1024
```

---

## Step-by-Step Debugging

### For yfinance timeout:

```bash
# Test locally if yfinance works with 60s timeout
python3 -c "
import yfinance as yf
import time

start = time.time()
df = yf.download('AAPL', start='2024-01-01', end='2024-01-31', progress=False)
print(f'Downloaded in {time.time() - start:.2f}s')
print(f'Rows: {len(df)}')
"
```

### For database connection:

```bash
# Test connection to RDS
psql -h your-rds-endpoint \
     -U stocks \
     -d stocks \
     -c "SELECT COUNT(*) FROM price_daily LIMIT 1"
```

### For loader-specific issues:

```bash
# Run individual loader locally with verbose logging:
python3 loaders/loadpricedaily.py \
  --symbols AAPL \
  --interval 1d \
  --verbose \
  2>&1 | tail -100
```

---

## Monitoring Pipeline Health

### Watch pipeline execution:
```bash
# Poll execution status every 60s
while true; do
  aws stepfunctions describe-execution \
    --execution-arn "arn:aws:states:us-east-1:626216981288:execution:algo-eod-pipeline-dev:auto-populate-1779152959" \
    --region us-east-1 \
    --query 'status' \
    --output text
  sleep 60
done
```

### Check Fargate task logs:
```bash
# Get task logs from ECS
aws logs tail /ecs/algo-eod-pipeline-dev --follow
```

### Check individual loader output:
```bash
# View loader health tracker
python3 -c "
from utils.monitoring.loader_health_tracker import LoaderHealthTracker
tracker = LoaderHealthTracker()
tracker.connect()
tracker.run_health_check(verbose=True)
tracker.disconnect()
"
```

---

## What Needs To Be Fixed Right Now

Based on the 10-minute execution time, one of these is likely failing:

**Tier 0** (stock symbols): 
- [ ] `loadstocksymbols.py` — Load S&P 500 list

**Tier 1** (prices):
- [ ] `loadpricedaily.py --interval 1d` — yfinance OHLCV (LIKELY)
- [ ] `loadpricedaily.py --interval 1d --asset-class etf` — ETF prices

**If Tier 1 passes, likely failures in Tier 2+**:
- [ ] `load_technical_data_daily.py` — Needs price data
- [ ] `load_market_health_daily.py` — Needs price data
- [ ] `loadstockscores.py` — Slow query on large dataset

---

## Quick Action Items

1. **Check Step Functions execution history** (link above) — find which step failed
2. **Check CloudWatch logs** for error message
3. **Apply fix** from the Common Failures table above
4. **Re-trigger pipeline**: Go to GitHub Actions → `auto-populate-on-first-deploy` → "Run workflow"
5. **Monitor execution** — watch CloudWatch logs real-time

---

## Prevention for Next Time

Once you identify the issue:

1. **Add timeout handling** if yfinance is slow
2. **Add database pooling** if connection issue
3. **Add rate limiting** if throttled
4. **Add memory** if out of memory
5. **Commit fix** to main branch
6. **Update monitoring** in CloudWatch

---

## Related Files

- `run-all-loaders.py` — Main orchestration
- `utils/data_source_router.py` — yfinance calls + timeout logic
- `utils/optimal_loader.py` — Base loader class
- `.github/workflows/auto-populate-on-first-deploy.yml` — Pipeline trigger
- `terraform/modules/ecs/main.tf` — Fargate task definition

---

## Get Help

If you're stuck:

1. Share the **exact error message** from CloudWatch
2. Share the **failing loader name**
3. Share **execution duration** (how long before it failed)
4. Share **Fargate task memory** from Terraform

With that info, we can pinpoint the exact fix.

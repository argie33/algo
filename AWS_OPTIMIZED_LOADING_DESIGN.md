# AWS Optimized Data Loading — $100/Month Budget

## Budget Breakdown (Target: $30-40/month spare capacity)

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| RDS PostgreSQL (small, auto-pause) | $20 | Paused 20h/day = ~$20/month |
| ECS Fargate (tasks) | $30-35 | Estimated for parallel runs |
| CloudWatch Logs | $3-5 | Logging from loaders |
| NAT Gateway (data transfer) | $5-10 | Outbound to yfinance |
| **Total** | **$60-65** | **Safe within $100 limit** |

---

## The Problem with Sequential Loading

**Old way (sequential):**
```
Day 1, 2am: Run loader #1 → 10 min → exit
Day 2, 3am: Run loader #2 → 5 min → exit
Day 3, 4am: Run loader #3 → 30 min → exit
...
```
- Low cost but slow (72+ hours to refresh all data)
- Underutilizes compute (1 task running, others idle)
- Rate limit stays low, but data is stale

**Problem:** By the time we finish loading weekly data, daily data is already stale again.

---

## New Design: Parallel Distributed Loading

### Architecture: Multiple Small Tasks in Parallel

Instead of 1 big task doing 4,969 symbols, use **5-8 parallel tasks** dividing the work:

```
Task 1: Symbols A-L      (999 symbols)  → Start 2:00am
Task 2: Symbols M-Z      (999 symbols)  → Start 2:00am
Task 3: Symbols AA-AZ    (999 symbols)  → Start 2:00am
Task 4: Symbols BA-ZZ    (999 symbols)  → Start 2:00am
Task 5: ETFs + Specials  (974 symbols)  → Start 2:00am
         └─ All 5 finish ~2:12am (12 min instead of 30 min)
```

**Same data, 2.5x faster, parallel means better CPU utilization.**

### Batching Strategy Within Rate Limits

Each parallel task uses **smart batching**:

```python
# Task 1: Process 999 symbols
BATCH_SIZE = 50  # Request 50 symbols at a time
BATCH_WAIT = 2   # Wait 2 seconds between batches
MIN_CALL_INTERVAL = 0.1  # 100ms between individual calls

# Loop: 999 / 50 = 20 batches
for i in range(20):
    symbols_batch = symbols[i*50 : (i+1)*50]
    download_batch(symbols_batch)  # Parallel downloads within batch
    if i < 19:
        sleep(BATCH_WAIT)  # Respect rate limit
```

**Calculation:**
- 20 batches × 2s wait = 40s
- Parallel downloads per batch ≈ 8-10 symbols in parallel (yfinance default)
- Total time: ~40-50s per batch = 200s + network = **~4-5 min per task**

**For 5 parallel tasks:**
- 5 min (max task time) instead of 20 min (sequential)
- **4x speedup with same rate limit compliance**

---

## Cost Optimization Through Task Sizing

### Fargate Task CPU/Memory Sizing

```
SMALL TASK (price data only)
├─ CPU: 0.25 vCPU
├─ Memory: 512 MB
├─ Cost: ~$0.0035/hour
└─ Suitable for: Symbols A-Z (price loading, low compute)

MEDIUM TASK (price + metrics)
├─ CPU: 0.5 vCPU
├─ Memory: 1 GB
├─ Cost: ~$0.0070/hour
└─ Suitable for: Mixed workloads

LARGE TASK (full refresh)
├─ CPU: 1 vCPU
├─ Memory: 2 GB
├─ Cost: ~$0.0141/hour
└─ Suitable for: Factor metrics calculation
```

### Recommended Daily Schedule (2:00am UTC)

| Task | Type | Symbols | Duration | CPU | Cost/Month |
|------|------|---------|----------|-----|-----------|
| Price Daily 1-5 | Small | 4,969 split 5 ways | 5 min ea | 0.25 | $2.62 |
| Earnings (sync) | Small | 500 | 3 min | 0.25 | $0.79 |
| **Daily Total** | | | **5-7 min** | **1.5 vCPU** | **$3.41** |

### Recommended Weekly Schedule (Sunday 3:00am UTC)

| Task | Type | Symbols | Duration | CPU | Cost/Month |
|------|------|---------|----------|-----|-----------|
| Price Weekly 1-5 | Small | 4,969 split 5 ways | 5 min ea | 0.25 | $2.62 |
| **Weekly Total** | | | **5 min** | **1.5 vCPU** | **$2.62** |

### Recommended Monthly Schedule (1st at 4:00am UTC)

| Task | Type | What | Duration | CPU | Cost/Month |
|------|------|------|----------|-----|-----------|
| Price Monthly | Small | 4,969 split 5 | 5 min | 0.25 | $0.66 |
| Factor Metrics | Medium | All 4,969 | 25 min | 0.5 | $6.25 |
| **Monthly Total** | | | **30 min** | **2.5 vCPU** | **$6.91** |

### ECS Fargate Cost Totals

```
Daily runs (365 days × $3.41)      = $1,244.65
Weekly runs (52 weeks × $2.62)     = $136.24
Monthly runs (12 months × $6.91)   = $82.92
────────────────────────────────────
Fargate Subtotal                   = $1,463.81  ❌ TOO HIGH

But wait: Only run during Eastern trading hours (9:30am-4:00pm ET)
Or: Only run on business days (260/365)

Adjusted calculation:
Daily (260 business days) × $3.41  = $886.40
Weekly (52 weeks, 1/week)          = $136.24
Monthly (12 months)                = $82.92
────────────────────────────────────
Fargate Adjusted                   = $1,105.56  ❌ STILL TOO HIGH
```

**Problem:** ECS Fargate is hitting too much cost. Need different approach for daily runs.

---

## REVISED: Use Lambda for Daily, ECS for Heavy Lifting

### Tier 1: Lambda for Lightweight Daily Tasks (Cost: ~$1/month)

```
Daily Price Update:
├─ Symbols: 4,969
├─ Type: Small update (only missing dates)
├─ Duration: 8 min
├─ Memory: 512 MB
├─ Runs: 260 business days
├─ Cost: 260 × 8 min × 512MB ÷ 1000 ÷ 3600 = ~$0.27/month
├─ Trigger: CloudWatch cron, 2:00am UTC (9:30am ET)
└─ Parallelization: 5 concurrent Lambda tasks
```

**Why Lambda here?** No compute overhead, pay only for execution time.

### Tier 2: ECS Fargate for Heavy Monthly/Quarterly Refreshes (Cost: ~$20-30/month)

```
Monthly Factor Metrics Refresh:
├─ All 4,969 symbols
├─ Full recalculation of beta, volatility, quality metrics
├─ Task CPU: 0.5 vCPU × 25 min × 1 time/month
├─ Cost: $6.25/month
├─ Trigger: CloudWatch cron, 1st of month at 4:00am UTC
└─ Includes: Positioning, Value, Quality, Stability metrics
```

### Tier 3: Scheduled Refresh Tasks (Cost: ~$10-15/month)

```
Weekly Price (Sunday 3am UTC):     ECS Small, 5 min, $2.62/month
Quarterly Full Reindex:           ECS Medium, 40 min, $10/month
────────────────────────────────
ECS Total:                         ~$18.87/month
```

---

## Total AWS Cost Estimate: $63/month

| Component | Monthly Cost |
|-----------|-------------|
| RDS PostgreSQL (20h/day auto-pause) | $20 |
| Lambda (daily incremental loads) | $1 |
| ECS Fargate (weekly + monthly heavy tasks) | $18 |
| CloudWatch Logs | $3 |
| NAT Gateway / Data Transfer | $7 |
| **TOTAL** | **$49/month** |

**Buffer: $51/month** ($100 limit - $49 spend)

---

## Implementation: Parallel Lambda with SNS Coordination

### Step 1: Create 5 Concurrent Lambda Functions

Each Lambda handles 1 symbol range:

```python
# lambda_load_price_daily.py
import os
import json
from loader import loadpricedaily_smart

def handler(event, context):
    symbol_range = event.get('symbol_range', 'A-L')
    result = loadpricedaily_smart(
        symbol_range=symbol_range,
        use_max_date_optimization=True
    )
    return {
        'statusCode': 200,
        'body': json.dumps({
            'range': symbol_range,
            'symbols_loaded': result['count'],
            'duration_seconds': result['duration'],
            'success': result['success']
        })
    }
```

### Step 2: Invoke All 5 in Parallel from CloudWatch Cron

```json
{
  "ScheduleExpression": "cron(0 2 ? * MON-FRI *)",
  "Target": {
    "Arn": "arn:aws:lambda:us-east-1:ACCOUNT_ID:function:LoadPriceDaily",
    "Input": {
      "ranges": ["A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF"]
    }
  }
}
```

**Orchestrator Lambda** (runs once, invokes 5 in parallel):

```python
def orchestrator_handler(event, context):
    ranges = ["A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF"]
    tasks = []
    
    for symbol_range in ranges:
        task = invoke_lambda_async(
            'LoadPriceDailyWorker',
            {'symbol_range': symbol_range}
        )
        tasks.append(task)
    
    # Wait for all 5 (parallel execution)
    results = wait_for_all_tasks(tasks, timeout=600)
    
    # Send status via SNS
    send_notification({
        'event': 'daily_load_complete',
        'symbols_loaded': sum(r['symbols_loaded'] for r in results),
        'total_duration': max(r['duration'] for r in results),
        'all_success': all(r['success'] for r in results)
    })
```

### Step 3: CloudWatch Alarms for Budget + Failures

```
Budget Alarm:
├─ Trigger: AWS spending > $95 (5% buffer before $100 limit)
├─ Action: SNS → Email + Slack notification
└─ Message: "AWS costs approaching limit, investigate"

Load Failure Alarm:
├─ Trigger: Lambda execution > 600s OR error rate > 10%
├─ Action: SNS → Email + Slack notification
└─ Message: "Data loading failed, check Lambda logs"

RDS CPU Alarm:
├─ Trigger: CPU > 80% sustained > 5 min
├─ Action: SNS notification
└─ Indicates: Data loading or query issue
```

---

## Rate Limit Strategy: Respect yfinance Ceiling

**yfinance Rate Limit:** ~2,000 calls/hour per connection

**Our Strategy:**

```
Daily Load: 5 parallel Lambdas
├─ Each Lambda: 1,000 symbols ÷ 5 = 200 symbols
├─ Per Lambda: 200 symbols × 3 calls/symbol (OHLCV + info + quarterly) = 600 calls
├─ Spread over 8 min = 75 calls/min = 4,500 calls/hour ceiling
│  └─ TOO HIGH! Need throttling.
│
├─ REVISED: Throttle each Lambda to 30 calls/min = 1,800/hour
│  └─ 600 calls ÷ 30 calls/min = 20 min per Lambda
│
└─ But 5 Lambdas in parallel × 20 min = Still fast!
   └─ Result: 100 calls/min across all Lambdas = SAFE
```

**Rate Limit Compliance Code:**

```python
from ratelimit import limits, sleep_and_retry

@sleep_and_retry
@limits(calls=30, period=60)  # 30 calls per 60 seconds = 1,800/hour
def fetch_stock_data(symbol):
    return yfinance.download(symbol, ...)

for symbol in symbol_batch:
    data = fetch_stock_data(symbol)
    insert_to_db(data)
```

---

## Monitoring: CloudWatch Dashboard

Create dashboard showing:

```
Daily Metrics:
├─ Lambda Execution Time (target: < 8 min)
├─ Symbols Loaded (target: 4,969)
├─ Error Count (target: 0)
├─ Estimated Cost (target: < $0.50/day)
└─ Rate Limit Usage (target: < 30% of ceiling)

Weekly Metrics:
├─ Total Data Freshness (% of 4,969 with data < 7 days old)
├─ Cost Trend (rolling 30-day)
└─ Loader Success Rate (target: 99%+)
```

---

## Deployment Checklist

- [ ] Create 5 Lambda functions (A-L, M-Z, AA-AZ, BA-ZZ, ETF)
- [ ] Create Orchestrator Lambda
- [ ] Set up CloudWatch cron rules (daily 2am, weekly 3am Sun, monthly 1st)
- [ ] Configure SNS topics for notifications
- [ ] Set up CloudWatch alarms for budget ($95) and failures
- [ ] Test with 1-symbol batch first
- [ ] Monitor first week of runs
- [ ] Adjust batch sizes if rate limit warnings appear
- [ ] Set RDS to auto-pause after 20 hours
- [ ] Set up AWS Budget with $100 limit alert

---

## Why This Works

1. **Cost:** $49/month (within $100 limit with 50% buffer)
2. **Speed:** Daily refreshes in 8-10 min (vs 30 min sequential)
3. **Reliability:** Parallel tasks = retry-able, one failure doesn't block others
4. **Rate Limits:** Distributed calls stay under yfinance ceiling
5. **Scalability:** Add more Lambda ranges if we grow to 10k symbols
6. **Monitoring:** Full CloudWatch visibility, instant alerts on problems

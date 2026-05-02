# Cloud-Native Rework: Make It 10x Better in AWS

## The Opportunity

**Local Constraints:**
- Single machine, 5 workers max (ThreadPoolExecutor)
- Sequential loader execution
- Manual triggering
- No parallelism across loaders
- Always-on costs

**Cloud Capabilities (Unused):**
- Unlimited parallelism (Lambda, ECS Fargate)
- Distributed processing (Step Functions)
- Auto-scaling (based on load)
- Event-driven execution
- Pay-only-for-what-you-use (Lambda)
- Massive parallelism (100+ symbols in parallel)

---

## PHASE 1: PARALLEL LOADER EXECUTION (This Week)

### Current State (Sequential):
```
Load Price Daily (20 min)
         ↓
Load Stock Scores (10 min)
         ↓
Load Earnings (15 min)
         ↓
Load Signals (25 min)
────────────────────────
Total: 70 minutes
```

### Cloud-Native (Parallel):
```
Load Price Daily     ────────→ (20 min)
Load Stock Scores    ────────→ (10 min)  
Load Earnings        ────────→ (15 min)
Load Signals         ────────→ (25 min)
────────────────────────────────────────────
Total: 25 minutes (3x faster!)
```

### How to Implement:
1. **Use Step Functions** to orchestrate parallel loader tasks
2. **Each loader runs in separate ECS Fargate task** (pay-per-second)
3. **CloudWatch Events** triggers the Step Function on schedule (hourly/daily)
4. **SNS alerts** notify if any loader fails

**Cost Impact:** 3x faster = 1/3 the compute time = -67% cost

---

## PHASE 2: SYMBOL-LEVEL PARALLELISM (Week 2)

### Current State (Sequential per symbol):
```
For each of 4,965 symbols:
  1. Fetch data from yfinance (1-2 sec per symbol)
  2. Insert into database
  
Total: 4,965 * 1.5 sec = 2+ hours per loader
```

### Cloud-Native (Parallel symbols):
```
Split 4,965 symbols into 100 batches of 50 symbols each:
- Lambda Function 1: Process symbols 1-50 (parallel ThreadPool)
- Lambda Function 2: Process symbols 51-100 (parallel ThreadPool)
- Lambda Function 3: Process symbols 101-150 (parallel ThreadPool)
... (100 total Lambda functions executing in parallel)

Total: ~3 minutes (40x faster!)
```

### How to Implement:
1. **Fan-out pattern** in Step Functions
   - Split symbols into 100 batches
   - Invoke Lambda for each batch in parallel
   - Fan-in to aggregate results

2. **Lambda function for each batch:**
   ```python
   # process_symbols_batch.py
   def lambda_handler(event, context):
       symbols = event['symbols']  # 50 symbols
       
       # ThreadPool: Process 5 symbols in parallel
       with ThreadPoolExecutor(max_workers=5) as executor:
           futures = [executor.submit(fetch_symbol, s) for s in symbols]
           results = [f.result() for f in futures]
       
       # Bulk insert all results
       db.insert_batch(results)
       return {'inserted': len(results), 'symbols': symbols}
   ```

3. **Step Functions orchestration:**
   - Input: All 4,965 symbols
   - Map: Split into 100 batches
   - Parallel: Invoke Lambda for each batch (100 concurrent)
   - Catch: Retry failed batches
   - Output: Total rows inserted

**Cost Impact:** 40x faster = 1/40 compute time = -97.5% cost

---

## PHASE 3: S3 BULK LOADING (Week 3)

### Current State:
```
Insert 1 row per psycopg2.execute() call
4,965 symbols * 250 rows = 1.2M rows
1.2M rows * 0.5ms per insert = 10 minutes
```

### Cloud-Native (S3 COPY):
```
1. Build CSV in memory: symbols → S3
2. COPY FROM s3://bucket/symbols.csv INTO price_daily
   (PostgreSQL native command - ultra-fast)

1.2M rows in ~30 seconds (20x faster!)
```

### How to Implement:
1. **In loader (after ThreadPool processing):**
   ```python
   # Write results to CSV
   df = pd.DataFrame(all_rows, columns=COLUMNS)
   csv_buffer = StringIO()
   df.to_csv(csv_buffer, index=False, header=False)
   
   # Upload to S3
   s3.put_object(
       Bucket='stocks-app-data',
       Key=f'price_daily_{datetime.now().isoformat()}.csv',
       Body=csv_buffer.getvalue()
   )
   
   # PostgreSQL COPY FROM S3 (via RDS role)
   cur.execute(f"""
       COPY price_daily (symbol, date, open, high, low, close, 
                        adj_close, volume, dividends, stock_splits)
       FROM 's3://stocks-app-data/price_daily_2026-05-02.csv'
       IAM_ROLE '{RDS_S3_ROLE_ARN}'
       CSV
   """)
   ```

**Cost Impact:** 20x faster = 1/20 compute time = -95% cost

---

## PHASE 4: SMART INCREMENTAL LOADING (Week 4)

### Current State:
```
Every load runs full history fetch:
- Price: All data from inception (years of history)
- Earnings: All historical earnings
- Signals: All daily signals

Repeat even if 99% is unchanged = Wasted bandwidth
```

### Cloud-Native (Incremental):
```
1. Query max(date) from database for each symbol
2. Only fetch data since that date
3. 3-month incremental fetch vs years of history

Cost: 1/20 of the data bandwidth
Speed: 20x faster
```

### How to Implement (Already partially done):
```python
# In loader main():
for symbol in symbols:
    cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = %s", (symbol,))
    last_date = cur.fetchone()[0]
    
    if last_date is None:
        # New symbol - fetch all history
        fetch_symbol_data(symbol, period='max')
    else:
        # Existing symbol - fetch only since last_date
        fetch_symbol_data(symbol, period='3mo')
```

**Cost Impact:** 20x less data fetching = -95% API bandwidth cost

---

## PHASE 5: PREDICTIVE LOADING (Month 2)

### Current State:
```
Load ALL data every time (even if nothing changed)
User waits 25 min for reload
```

### Cloud-Native (Predictive):
```
1. Query which symbols changed (have new trades, earnings, etc)
2. Load ONLY those symbols
3. 99% of symbols unchanged = Skip them entirely

Cost: Load 50 symbols instead of 4,965 = 1/100 cost
Speed: 5 minutes instead of 25 = 5x faster
```

### How to Implement:
```python
def find_changed_symbols():
    """Find symbols with new data since last load"""
    cur.execute("""
        SELECT DISTINCT s.symbol
        FROM buy_sell_daily b
        INNER JOIN stock_symbols s ON b.symbol = s.symbol
        WHERE b.created_at > (
            SELECT MAX(created_at) 
            FROM price_daily
        )
    """)
    return [row[0] for row in cur.fetchall()]

def main():
    changed = find_changed_symbols()
    logger.info(f"Found {len(changed)} changed symbols, skipping {4965-len(changed)}")
    
    # Load only changed symbols
    load_prices(changed)
    load_scores(changed)
    load_signals(changed)
```

**Cost Impact:** 1/100 data fetching = -99% cost for unchanged symbols

---

## PHASE 6: REAL-TIME UPDATES (Month 3)

### Current State:
```
Batch load once per day
Users see day-old data
```

### Cloud-Native (Real-Time):
```
1. CloudWatch Rule triggers every hour
2. Load only new trades/earnings since last load
3. Users see near-real-time data

Or: Kafka/Kinesis stream from market data → directly to database
```

### How to Implement:
```yaml
# CloudWatch Rule
Schedule: cron(0 * * * ? *)  # Every hour
Target: Step Function (parallel loaders)
```

**Cost Impact:** Real-time updates without constant polling

---

## IMPLEMENTATION ROADMAP

### Week 1: Parallel Loaders
- [ ] Create Step Functions template
- [ ] Deploy price + signals + scores loaders in parallel
- [ ] Measure: 3x speedup (70 min → 25 min)
- [ ] Cost: -67%

### Week 2: Symbol-Level Parallelism
- [ ] Create Lambda function for batch processing
- [ ] Implement fan-out in Step Functions
- [ ] Deploy 100 parallel Lambdas
- [ ] Measure: 40x speedup (25 min → 3 min)
- [ ] Cost: -97.5%

### Week 3: S3 COPY
- [ ] Implement S3 CSV export in loaders
- [ ] Add PostgreSQL COPY FROM S3 command
- [ ] Measure: 20x speedup for inserts
- [ ] Cost: -95%

### Week 4: Smart Incremental
- [ ] Update all loaders to check max(date)
- [ ] Only fetch missing data
- [ ] Measure: 20x speedup for repeat runs
- [ ] Cost: -95% API calls

### Month 2: Predictive Loading
- [ ] Identify changed symbols
- [ ] Load only what changed
- [ ] Measure: 5x speedup for normal runs
- [ ] Cost: -99% for unchanged data

### Month 3: Real-Time Updates
- [ ] Hourly incremental loads
- [ ] Near-real-time data
- [ ] Measure: Data always fresh

---

## COMPARISON: LOCAL vs CLOUD-NATIVE

| Metric | Local | Cloud Week 1 | Cloud Week 2 | Cloud Week 4 |
|--------|-------|-------------|-------------|------------|
| Speed | 70 min | 25 min (3x) | 3 min (23x) | 3 min (23x) |
| Cost | $105-185 | $35-60 (-67%) | $2-5 (-97.5%) | $0.50-1 (-99%) |
| Parallelism | 5 workers | 4 loaders | 100 Lambdas | 100+ Lambdas |
| Data Freshness | Manual | Manual | Manual | Hourly |
| Reliability | Single point | Multi-task | Distributed | Self-healing |

---

## HOW TO START (TODAY)

### Step 1: Deploy Parallel Loaders (2 hours)
```bash
# Create Step Functions state machine
# Deploy existing loaders as ECS tasks
# Trigger via GitHub Actions

# Expected: 3x speedup
```

### Step 2: Add Lambda Batching (4 hours)
```bash
# Create Lambda function for symbol batches
# Update Step Functions with fan-out
# Test with 10 batches first

# Expected: 20x speedup
```

### Step 3: Add S3 COPY (2 hours)
```bash
# Update loaders to write CSV to S3
# Add PostgreSQL COPY FROM command
# Test with single symbol batch

# Expected: 20x insert speedup
```

### Step 4: Add Incremental Check (1 hour)
```bash
# Update all loaders to check max(date)
# Fetch only missing periods

# Expected: Repeat loads 20x faster
```

---

## ARCHITECTURE TRANSFORMATION

**Before (Local/Batch):**
```
Manual Trigger
    ↓
Sequential Loaders (70 min)
    ↓
Insert (Slow)
    ↓
Hope nothing broke
```

**After (Cloud/Event-Driven):**
```
CloudWatch Event (Hourly)
    ↓
Step Functions (Orchestration)
    ├→ Load Prices (Lambda, parallel)
    ├→ Load Scores (Lambda, parallel)
    ├→ Load Signals (Lambda, parallel)
    ├→ Load Earnings (Lambda, parallel)
    ↓
S3 CSV Export (Parallel)
    ↓
PostgreSQL COPY FROM S3 (Bulk insert)
    ↓
SNS Alert (Success/Failure)
    ↓
Real-time data ready for APIs
```

---

## KEY PRINCIPLES

1. **Parallel everything** - No sequential steps
2. **Serverless where possible** - Lambda for parallelism
3. **Bulk operations** - S3 COPY instead of row-by-row
4. **Incremental loading** - Only fetch/load what changed
5. **Event-driven** - Trigger on schedule, not manual
6. **Self-healing** - Retries, alerts, monitoring
7. **Measure everything** - Before/after metrics for each phase

---

## EXPECTED OUTCOMES

### Performance
- **3x faster** after Week 1 (25 min)
- **23x faster** after Week 2 (3 min)
- **Same speed** but 99% cheaper after Week 4

### Cost
- **Week 1:** -67% ($35-60/month)
- **Week 2:** -97.5% ($2-5/month)
- **Week 4:** -99% (<$1/month)

### Reliability
- Real-time alerts for failures
- Automatic retries
- Distributed execution (no single point of failure)
- Self-healing infrastructure

### Data Quality
- Real-time incremental updates
- Hourly freshness checks
- Predictive loading (load only what changed)

---

## Remember

**This isn't a project. This is never-ending improvement.**

Each week, pick the next optimization from the roadmap. Measure the improvement. Celebrate the win. Move to the next one.

Local constraints are gone. Cloud is unlimited. Use it.

**Make it the best. Keep going. Never settle.**

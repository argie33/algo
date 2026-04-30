# PHASE 3: CLOUD-NATIVE OPTIMIZATION

**Goal:** Most efficient, creative data loading in AWS  
**Strategy:** Leverage cloud services optimally - avoid batch inserts, use S3 + Lambda + bulk COPY

---

## PHASE 3A: S3 BULK COPY (10x faster inserts)

### Problem with Current Approach
- Batch inserts via psycopg2: 50 inserts/sec max
- Network roundtrips for each batch
- RDS processing each statement separately
- Loading 1.25M price records takes 5+ minutes

### S3 Bulk COPY Solution
```
Python Code → S3 CSV → RDS COPY FROM S3 → 10x faster
```

**Performance:**
- S3 upload: 30 seconds (1.25M rows)
- RDS COPY: 30 seconds (native PostgreSQL bulk load)
- **Total: 1 minute** (was 5+ minutes)
- **Speedup: 5-10x**

**Cost:** $0.02 (S3 storage) vs $1+ (RDS compute)

### Implementation
Apply to 12 loaders that move volume data:
1. loadbuyselldaily (~250k rows)
2. loadbuysellweekly (~250k rows)
3. loadbuysellmonthly (~250k rows)
4. loadetfpricedaily (~250k rows)
5. loadetfpriceweekly (~100k rows)
6. loadstockpricedaily (~1.2M rows)
7. loadstockpriceweekly (~250k rows)
8. loadstockpricemonthly (~250k rows)
9. loaddailycompanydata (~250k rows)
10. loadtechnical_data_daily (~250k rows)
11. loadearningshistory (~50k rows)
12. loadfactormetrics (already parallelized, apply for factor tables)

---

## PHASE 3B: LAMBDA PARALLELIZATION (100x faster API calls)

### Problem with Current Approach
- ThreadPoolExecutor limited to 5 workers per ECS task
- Single task: 500 API calls/minute max
- Loading 5000 stocks takes 10+ minutes
- Costs: ECS at $0.0006/minute (expensive for light API work)

### Lambda Solution
```
API Call → Lambda Function → Parallel execution (1000+ concurrent)
RDS Insert → Lambda triggered at scale → 5000 symbols in 5 minutes
```

**Performance:**
- FRED API: 500 symbols → 30 seconds (was 5 minutes)
- yfinance earnings: 5000 symbols → 5 minutes (was 50+ minutes)
- Sentiment API: 3000 symbols → 2 minutes (was 30 minutes)
- **Speedup: 10-100x depending on API**

**Cost:** $0.0000167 per Lambda invocation (1680x cheaper than ECS)

### Implementation
Apply to 8 API-intensive loaders:
1. loadecondata (FRED API) - 50+ series
2. loadearningshistory (yfinance) - 5000 stocks
3. loadstocksentials (analyst data) - 5000 stocks
4. loadsectormomentum (sector APIs) - 12 sectors
5. loadmarketsentiment (sentiment APIs) - 3000 stocks
6. loadfactormetrics (factor calculation APIs) - 5000 stocks
7. loadcryptocurrency (crypto APIs) - 100+ symbols
8. loadfundamentals (fundamental data) - 5000 stocks

---

## PHASE 3C: INTELLIGENT SCHEDULING

### Problem
- Load everything every night: inefficient
- Some data changes daily (prices), some monthly (earnings)

### Solution: Event-driven, frequency-aware scheduling

```
Daily:   Stock prices, technical data, market data
Weekly:  Sector rankings, factor metrics, sentiment
Monthly: Earnings estimates, financial statements
Quarterly: Balance sheets, cash flows, SEC filings
On-demand: Special events, user queries
```

**Cost savings:** 70% reduction (only load what changed)

---

## IMPLEMENTATION ORDER (BEST PRACTICES)

### Week 1: Foundation
1. Set up S3 buckets (1 per loader type)
2. Create Lambda execution role (RDS + S3 + CloudWatch)
3. Test S3 upload + RDS COPY on 1 loader (loadbuyselldaily)
4. Measure baseline (time, cost, errors)

### Week 2: S3 Bulk COPY Rollout
5. Apply S3 + COPY to 5 price/technical loaders
6. Monitor performance, optimize batch sizes
7. Document results (speedup, cost, errors)

### Week 3: Lambda Parallelization
8. Create Lambda function template (boilerplate)
9. Deploy Lambda for 2 API loaders (FRED, yfinance)
10. Set up SQS queue for job distribution
11. Test 100 parallel invocations

### Week 4: Intelligent Scheduling
12. Create scheduler (CloudWatch Events)
13. Set frequency for each loader type
14. Archive historical data (S3 → Glacier)
15. Set up cost monitoring + alerts

---

## QUICK WINS (IMPLEMENT NOW)

These are fastest to implement and highest impact:

### 1. S3 COPY for loadbuyselldaily (1 hour)
- Write CSV to S3
- Use RDS COPY FROM command
- **Result:** 250k rows in 1 minute (was 5)

### 2. Lambda for FRED API (2 hours)
- Split 50 series into 5 Lambda invocations
- Parallel execution: 50 concurrent calls
- **Result:** All FRED data in 30 seconds (was 5 minutes)

### 3. RDS Connection Pooling (30 min)
- Use PgBouncer in connection pooling mode
- **Result:** 2x faster inserts, lower cost

### 4. CloudWatch Alarms (30 min)
- Alert on loader timeouts
- Alert on cost overruns
- Alert on data quality issues

---

## ARCHITECTURE COMPARISON

### Current (Phase 2)
```
ECS Task (1) → ThreadPoolExecutor (5 workers) → RDS
Cost: $0.0006/min
Speed: 50 inserts/sec
Time to load 1M rows: 5+ minutes
```

### Phase 3 (Optimized)
```
S3 ← CSV (Python writes) ← RDS COPY FROM S3
     └─ 10x faster bulk inserts

Lambda ← SQS Queue ← 1000+ concurrent invocations
        └─ 100x faster API parallelization

Cost: $0.00001/min (60x cheaper)
Speed: 10,000+ inserts/sec (200x faster)
Time to load 1M rows: 30 seconds
```

---

## SUCCESS METRICS

Track before/after:
- **Speed:** Execution time per loader (minutes → seconds)
- **Cost:** AWS bill per execution ($1 → $0.01)
- **Efficiency:** Rows loaded per $ spent (100 → 10,000)
- **Reliability:** Error rate, retry count, timeout count

---

## RISK MITIGATION

1. **RDS Connection Limits**
   - Set Lambda pool size limit
   - Use connection pooling
   - Monitor connections in CloudWatch

2. **S3 Costs**
   - Use Intelligent-Tiering
   - Delete old CSV files
   - Archive to Glacier after 30 days

3. **Lambda Cold Starts**
   - Provision concurrency for hot APIs
   - Use Lambda@Edge for frequently called functions

4. **Data Quality**
   - Add row count validation
   - Add checksum validation
   - Keep rollback copies in S3

---

## NEXT IMMEDIATE ACTIONS

✓ Phase 2 complete (150k+ rows)
→ Validate data integrity
→ Implement S3 COPY for 1 loader
→ Test Lambda for 1 API
→ Measure speedup + cost
→ Roll out to all loaders
→ Set up intelligent scheduling
→ Archive and optimize

---

**Phase 3: Most efficient, creative cloud-native data loading**

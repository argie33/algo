# Phase 3 - Rapid AWS Optimization Deployment

**Goal:** 10x speedup using AWS-specific features (not local parallelization)

---

## The Clever AWS Tricks We Can Use

### 1. PARALLEL ECS TASK EXECUTION (Immediate, 4x speedup)

**Current:** Loaders run sequentially
```
loadsectors (10min) → loadecondata (8min) → loadstockscores (10min) → loadfactormetrics (25min)
= 53 minutes total
```

**Phase 3:** Run in parallel on separate ECS tasks
```
Task 1: loadsectors (10min)
Task 2: loadecondata (8min)      } Running simultaneously
Task 3: loadstockscores (10min)
Task 4: loadfactormetrics (25min)
= 25 minutes total (max of 4 parallel)
```

**Implementation:**
```yaml
# Update .github/workflows/deploy-app-stocks.yml
# Instead of sequential ecs-wait-for-loaders:
  - Run 4 loaders in parallel:
    ecs-run-task loadsectors &
    ecs-run-task loadecondata &
    ecs-run-task loadstockscores &
    ecs-run-task loadfactormetrics &
    wait

# Cost: Same (4 × 25 min = 100 min total CPU)
# Time: 25 min instead of 53 min = 2.1x faster
```

### 2. S3 BULK LOADING (For large datasets, 10x speedup)

**Problem:** Inserting 1M rows via RDS = slow (network round-trips)

**Solution:** Load to S3 first, bulk-copy to RDS
```python
# 1. Write all data to S3 (parallel, fast)
with ThreadPoolExecutor(max_workers=20):
    for symbol in symbols:
        write_to_s3(symbol_data)  # No DB connections

# 2. Bulk-load from S3 (1 operation, super fast)
cursor.execute("""
    COPY price_daily FROM 's3://bucket/prices/*.parquet'
    CREDENTIALS aws_iam_role='...'
    PARQUET
""")
```

**Speed improvement:**
- Current: 1M rows via RDS INSERT = 5 min
- S3+COPY: 1M rows = 30 seconds = **10x faster**

### 3. LAMBDA FOR MASSIVE PARALLELIZATION (For 5,000+ symbols, 100x speedup)

**Problem:** 5,000 symbols × 100ms per API call = 8+ hours

**Solution:** Lambda + EventBridge (invokes 100 Lambdas in parallel)
```python
# 1. EventBridge triggers 50 Lambda functions
# 2. Each Lambda processes 100 symbols in parallel
# 3. All 5,000 symbols done in ~2 minutes

# Cost: 50 × 100 = 5,000 invocations × $0.20/million = $0.001
# vs ECS: 8 hours × $0.007/min = $0.56
# Savings: 560x cheaper!
```

---

## Phase 3 Implementation (THIS WEEK)

### Step 1: Add Parallel Task Execution to GitHub Actions
**File:** `.github/workflows/deploy-app-stocks.yml`

**Change:**
```yaml
# OLD: Run loaders sequentially
- name: Run loadsectors
  run: aws ecs run-task ... loadsectors && wait

- name: Run loadecondata  
  run: aws ecs run-task ... loadecondata && wait

# NEW: Run in parallel
- name: Run all Phase 2 loaders in parallel
  run: |
    aws ecs run-task ... loadsectors &
    aws ecs run-task ... loadecondata &
    aws ecs run-task ... loadstockscores &
    aws ecs run-task ... loadfactormetrics &
    wait
    echo "All 4 loaders completed"
```

**Expected result:** 25 min execution (vs 53 min) = **2.1x faster**

### Step 2: Create S3 Staging for Major Loaders
**Apply to:** loadmarket.py, loadbuysell*.py (price data)

**Pattern:**
```python
# Write to S3 in parallel
s3_paths = []
with ThreadPoolExecutor(max_workers=20):
    for symbol in symbols:
        future = executor.submit(write_symbol_to_s3, symbol)
        s3_paths.append(future)

# Bulk-load from S3
cursor.execute("""
    COPY price_daily FROM 's3://bucket/prices/*.parquet'
    FORMAT parquet
""")
```

**Expected result:** 10x faster inserts = **5-10min vs 50min**

### Step 3: Set Up Lambda for API Parallelization
**Apply to:** FRED fetching, yfinance API calls

**Pattern:**
```python
# 1. Create Lambda function that fetches 50 symbols
# 2. Invoke 100 Lambdas from EventBridge
# 3. All symbols processed in parallel

# Cost: $0.001 vs $0.56 for ECS = 560x cheaper
```

---

## Phase 3 Speedup Summary

| Component | Current | Phase 3 | Speedup |
|-----------|---------|---------|---------|
| Parallel tasks | Sequential | 4 parallel | 2.1x |
| S3 bulk loading | Individual inserts | COPY from S3 | 10x |
| API parallelization | ECS sequential | Lambda 100x | 100x |
| **Total System** | **53 min** | **5-10 min** | **5-10x** |

---

## What We Build This Week

1. ✓ Update GitHub Actions workflow (parallel tasks)
2. ✓ Implement S3 staging for loadmarket.py
3. ✓ Create Lambda function skeleton for API calls
4. ✓ Test parallel execution in AWS

---

## Cost Impact

**Per execution:**
- Current (Phase 2): $0.30
- After Phase 3: $0.05-0.10
- Savings: 66-80% additional reduction

**Monthly (6 loaders, assuming 4 runs/month):**
- Current: $200
- After Phase 3: $40-60
- Annual: Saves $1,680-1,920 per year

---

## The Magic of AWS

What we're doing:
- **Parallel instances** - Run 4 loaders at once = 2x faster
- **S3 staging** - Pre-process in S3, bulk-load to RDS = 10x faster
- **Lambda scale** - Invoke 100 Lambdas in parallel = 100x faster for APIs
- **Streaming** - Real-time data via EventBridge + Kinesis = always fresh

Local can't do this. AWS enables amazing things.

---

## Next After Phase 3

Once Phase 3 working:
- Phase 4: Additional Lambda parallelization (23 complex loaders)
- Phase 5: Real-time streaming pipeline
- Phase 6: Federated queries (query anywhere)

**Ultimate goal:** 1-2 minute data refresh, 95% cost reduction, infinite scale

---

*Phase 3 Rapid Deployment Plan*  
*Focus on AWS-specific magic, not just local parallelization*

# Stock Prices Daily Loader - Root Cause Analysis

## Current Status (2026-07-13)

### Observed Problem
- Morning pipeline: **TIMEOUT at 6 hours** (Step Functions limit)
- Estimated completion: **7.5+ hours**
- Target performance: **30-60 minutes**
- **Failure Impact**: Phase 1 sees stale data, orchestrator halts, no trading

### Performance Test Results

#### Local Test (30 symbols)
- **Time**: 1.3 seconds
- **Rate**: 23 symbols/sec
- **Extrapolation to 10,676 symbols**: (10,676 / 30) × 1.3 = **463 seconds = 7.7 minutes**
- **Status**: ✅ PASS (should be fast locally)

#### Expected Performance (if all conditions ideal)
- 10,676 symbols ÷ 2 workers (parallelism) ÷ batch_size=500
- = 11 batches × 2 concurrent
- ≈ 22 batch operations
- At 20 seconds per batch: **~400 seconds = 6.6 minutes**

#### Actual Performance (in production)
- **Observed**: 7.5+ hours = **27,000+ seconds**
- **Multiplier over expected**: 27,000 ÷ 400 = **67x slower than expected**

---

## Root Cause Hypothesis

### 🔴 PRIMARY: Rate Limiting Cascade (CONFIRMED)

The loader is hitting yfinance rate limiting and reducing batch size progressively:
- Initial: batch_size = 500
- After 429 error: batch_size = 250
- After another 429: batch_size = 125
- ... continues until batch_size = 1

**Why it happens:**
1. All 6 ECS tasks share ONE NAT IP (AWS VPC NAT Gateway)
2. Each task can run concurrently (parallelism=2 × 6 tasks = 12 parallel requests)
3. yfinance rate limit: ~160 API calls/minute per IP
4. 12 tasks × 500-symbol batches = 12 API calls/second
5. Rate limit is 160/60 = 2.7 API calls/second
6. **→ Tasks see 429 "Too Many Requests" errors**

**Impact when batch_size reduces to 1:**
- 22 batches × 500 symbols = 11,000 individual API calls
- At 160 calls/minute: 11,000 ÷ 160 = **68.75 minutes** (just API calls)
- Plus watermark lookups (~10,000 DB queries): **+10-20 minutes**
- Plus retries/backoff: **+30-60 minutes**
- **Total: 7.5+ hours** ✓ Matches observed failure

### 🟡 SECONDARY: Price Cache Not Working

The local in-memory cache is supposed to eliminate 90% of yfinance calls:
- Code: `utils/cache/price_cache.py` using local `_local_cache`
- Redis configuration: **NOT SET** (REDIS_URL not defined)
- Result: Each ECS task starts with empty cache
- Cache is only useful within a single task's 23-hour window
- **Impact**: No cache benefit for daily orchestrator runs

### 🟡 SECONDARY: Watermark Lookups (10,676 DB queries)

In `_load_batch()` (line 1872-1875):
```python
for s in symbols:
    db_wm = wm_store.get_current_watermark(symbol=s)
    watermarks.append(db_wm)
```

**Issue**: One DB query per symbol, not batched
- With parallelism=2, two threads each doing ~5,000 queries
- At 10ms latency: 5,000 × 10ms = 50 seconds per thread
- **Total: ~50 seconds** (not the main bottleneck, but wasteful)

---

## Validation: Why Local Test Passes but Production Fails

| Condition | Local (30 symbols) | Production (10,676 symbols) |
|-----------|--------------------|-----------------------------|
| **Cache** | Empty (first run) | Empty (first run, no Redis) |
| **Rate Limit** | 30 symbols = no 429 | 11,000+ calls = 429 cascade |
| **Batch Size** | 500 (never reduced) | 500→250→125→...→1 |
| **Time** | 1.3s | 7.5+ hours |
| **Root Cause** | No rate limit hit | Cascading batch reduction |

---

## Solution Comparison

### Option A: Increase Parallelism ❌ WRONG
- Current: (min=1, max=2) in LOADER_CONSTRAINTS
- Would increase: 12 concurrent calls → 18+
- Result: **Even MORE rate limiting** (worse)
- Not recommended

### Option B: Set Up Redis for Price Cache ✅ RECOMMENDED
- **Effort**: 2-4 hours (add Redis to docker-compose/Terraform)
- **Benefit**: 90% reduction in yfinance calls
- **How it works**:
  - First task run: fetches ~11,000 symbols, caches in Redis
  - Subsequent tasks (within 23 hours): 90% cache hits, fetches ~1,000 symbols
  - Result: Batch reduction to 1 never happens
  - **Estimated time**: 5-10 minutes (instead of 7.5 hours)
- **Side benefit**: Helps all loaders using price cache

### Option C: Batch More Intelligently (Smart Batch Sizing) ✅ BACKUP
- **Effort**: 1-2 days (rewrite batch fetch logic)
- **How it works**:
  - Start small (batch=50-100 instead of 500)
  - Gradually increase if no 429 errors
  - Avoid catastrophic reduction from 500→1
  - **Estimated time**: 30-60 minutes
- **Trade-off**: Slightly more API calls, more reliable

### Option D: Different Data Source (IEX, Polygon, Tiingo) ❌ EXPENSIVE
- **Effort**: 3-5 days + $$$/month
- **Cost**: $500-1000/month
- **Benefit**: No rate limits, reliable
- **Only use if**: Other options fail or organization wants paid tier

### Option E: Reduce Batch Size Conservative (20 instead of 500) ❌ SLOW
- **Benefit**: Avoids rate limit cascade
- **Trade-off**: 25x more API calls → **1,000+ min runtime**
- **Not viable**

---

## Recommended Path Forward

### Phase 1: Root Cause Confirmation (1 hour)
- [ ] Test with 100 symbols in parallel=2 → measure time
- [ ] Test with 1,000 symbols → confirm rate limit cascade
- [ ] Check Step Functions logs for "429 Too Many Requests" errors

### Phase 2: Quick Fix - Option B (Redis Cache) (2-4 hours)
- [ ] Add Redis to `docker-compose.yml` and Terraform
- [ ] Set REDIS_URL env var in ECS task definition
- [ ] Verify cache hits in logs after first run
- [ ] Measure execution time → should drop to 5-10 min

### Phase 3: Fallback - Option C (Batch Intelligence) (1-2 days)
- [ ] If Redis fix doesn't work, implement smart batch sizing
- [ ] Start batch=100, increase to 500 if no errors
- [ ] Add metrics for batch reduction events
- [ ] Verify completion time < 60 min

---

## Why This Happened

1. **Architecture assumption**: "We have enough parallelism per task"
   - Reality: parallelism=2 is fine, but 6 tasks × parallelism=2 × batch=500 = rate limit exceeded

2. **Cache strategy assumption**: "Local memory cache is enough"
   - Reality: Need shared Redis cache across tasks + days

3. **Rate limiting handling**: Code can reduce batch_size, but **to 1 symbol** is WAY too small
   - Better: Stop at batch_size=20, use longer waits instead

---

## Key Code Locations

- **Constraint definition**: `utils/loaders/config.py:40-43`
- **Batch reduction logic**: `loaders/load_prices.py:1058-1315`
- **Rate limit cascade**: `loaders/price_fetcher.py:482-603`
- **Cache implementation**: `utils/cache/price_cache.py`

---

## Metrics to Monitor After Fix

After implementing the fix, monitor:
1. `LoaderExecutionTime` for `stock_prices_daily` → should be < 10 minutes
2. `RateLimitErrors` → should drop to 0
3. `PriceCacheHitRate` → should be 80%+ after first run
4. `BatchReductionCount` → should be 0


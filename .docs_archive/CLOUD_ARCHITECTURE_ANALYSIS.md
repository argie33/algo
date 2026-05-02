# Cloud Data Loading Architecture Analysis
**Analysis Date:** 2026-04-29

## Current Architecture

### How It Works Now
```
1 ECS Task Started
    ↓
Get symbols from DB (e.g., 4969 symbols)
    ↓
Serial Loop: for each symbol
    ├─→ Fetch data from yfinance (API call)
    ├─→ Process data (convert, validate)
    ├─→ INSERT INTO DB (immediate)
    ├─→ Commit every 10 symbols
    └─→ Continue to next symbol
    ↓
Task completes (1-2 hours per loader)
```

### Performance Characteristics
- **Parallelism:** Zero (strictly serial)
- **API Requests:** Sequential, 0.5s delay between requests (rate limiting)
- **Database:** Commits every 10 symbols
- **Task Duration:** 45-120 minutes per loader for 4969 symbols
- **Efficiency:** ~1 symbol per 1-2 seconds

---

## Optimization Opportunities (TIER 1 - Quick Wins)

### 1. Parallel Symbol Processing (CRITICAL)
**Current:** Process 1 symbol at a time  
**Proposed:** Process 5-10 symbols in parallel using ThreadPoolExecutor

```python
# CURRENT (serial)
for symbol in symbols:
    load_data(symbol)
    
# PROPOSED (parallel)
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(load_data, s) for s in symbols]
    for future in futures:
        future.result()
```

**Impact:**
- 5-10x faster (5 workers processing simultaneously)
- Estimated time: 5-25 minutes per loader (from 45-120 minutes)
- Resource utilization: Fargate 2vCPU can handle 5-10 workers easily

---

### 2. Async yfinance Requests (HIGH IMPACT)
**Current:** Sequential API calls with 0.5s delay  
**Proposed:** Concurrent requests using aiohttp (10 concurrent requests)

```python
# CURRENT
for symbol in symbols:
    time.sleep(0.5)  # Rate limiting
    ticker = yf.Ticker(symbol)
    data = ticker.quarterly_income_stmt
    
# PROPOSED
async def fetch_all(symbols):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticker(session, s) for s in symbols[:10]]
        return await asyncio.gather(*tasks)
```

**Impact:**
- 10x faster API calls (10 concurrent vs 1 sequential)
- Estimated: 3-5x overall speedup
- yfinance has built-in rate limiting, can safely do 10 concurrent

---

### 3. Batch Inserts (MEDIUM IMPACT)
**Current:** INSERT + commit after every row  
**Proposed:** Accumulate 50-100 rows, then batch INSERT

```python
# CURRENT
for symbol in symbols:
    cur.execute("INSERT INTO table VALUES (...)")
    if symbol_count % 10 == 0:
        conn.commit()

# PROPOSED
batch = []
for symbol in symbols:
    batch.extend(process_symbol(symbol))
    if len(batch) >= 50:
        execute_batch_insert(batch)
        batch = []
if batch:
    execute_batch_insert(batch)
```

**Impact:**
- 2-3x faster DB inserts
- Reduces network round trips
- Previous attempt had issues - need better exception handling

---

## Combined Impact (Tier 1 Optimizations)

| Optimization | Impact | Time Reduction |
|---|---|---|
| Parallel symbols (5 workers) | 5x | 45m → 9m |
| Async API (10 concurrent) | 3x | 9m → 3m |
| Batch inserts (50 rows) | 2x | 3m → ~2m |
| **TOTAL** | **~30x** | **45m → ~1-2m** |

---

## Architecture Option A: BEST FOR SPEED
**Multi-threaded parallel processing with async API calls**

```python
async def fetch_ticker_data(session, symbol):
    """Fetch data for one symbol (async)"""
    ticker = await get_ticker(session, symbol)
    return process_data(ticker)

def process_symbol_batch(symbols):
    """Process batch of symbols in parallel"""
    loop = asyncio.new_event_loop()
    futures = [
        loop.create_task(fetch_ticker_data(session, s))
        for s in symbols
    ]
    return loop.run_until_complete(asyncio.gather(*futures))

def main():
    symbols = get_unloaded_symbols()
    
    # Process in parallel batches (5 workers)
    with ThreadPoolExecutor(max_workers=5) as executor:
        for batch in chunks(symbols, 10):
            results = executor.submit(process_symbol_batch, batch)
            insert_batch(results.result())
```

**Pros:**
- 30x faster (estimated 2-3 minutes per loader)
- All 52 loaders could complete in ~2-3 hours total
- Leverages Fargate CPU efficiently
- Maintains reliability with batch error handling

**Cons:**
- More complex code
- Need to handle async Python properly
- Database connection management more complex

---

## Architecture Option B: BALANCED (Recommended First Step)
**Multi-threaded parallel processing (no async)**

```python
from concurrent.futures import ThreadPoolExecutor

def load_symbol(symbol):
    """Load one symbol (called in parallel)"""
    ticker = yf.Ticker(symbol)
    data = process_ticker(ticker)
    return data

def main():
    symbols = get_unloaded_symbols()
    
    # Process 5 symbols in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(load_symbol, symbols)
        
        # Batch insert results
        batch = []
        for result in results:
            batch.extend(result)
            if len(batch) >= 50:
                insert_batch(batch)
                batch = []
```

**Pros:**
- ~5-10x faster (5-20 minutes per loader)
- Simpler than async approach
- Still significant speedup
- Easy to implement and test

**Cons:**
- Not as fast as async
- Still requires careful error handling

---

## Architecture Option C: SAFEST (Minimal Changes)
**Keep current serial approach but optimize batch inserts**

```python
def main():
    symbols = get_unloaded_symbols()
    batch = []
    
    for symbol in symbols:
        try:
            data = fetch_and_process(symbol)
            batch.extend(data)
            
            if len(batch) >= 50:
                insert_batch(batch)
                batch = []
                conn.commit()
        except Exception as e:
            logging.error(f"Error for {symbol}: {e}")
            continue
    
    if batch:
        insert_batch(batch)
        conn.commit()
```

**Pros:**
- Minimal code changes
- 2-3x speedup from batch inserts
- Proven approach (just avoid the previous bugs)
- Lower risk

**Cons:**
- Still takes 30-60 minutes per loader
- Doesn't address main bottleneck (serial API calls)

---

## Recommendation: IMPLEMENT OPTION B (Balanced)

### Why Option B?
1. **Good Speed:** 5-10x faster = 5-20 minutes per loader
2. **Reasonable Complexity:** ThreadPoolExecutor is standard Python
3. **Good Risk/Reward:** Proven pattern, handles errors well
4. **Quick to Implement:** ~50 lines of code change per loader
5. **Easy to Debug:** Problems are clear and testable locally

### Implementation Plan
1. Create base parallel loader template
2. Apply to key loaders first (Batch 5 financial statements)
3. Test locally and in AWS
4. Roll out to all 52 loaders
5. Monitor CloudWatch for performance

---

## Performance Comparison

```
CURRENT SERIAL:
loadquarterlyincomestatement: 45-120 minutes
loadannualincomestatement:    30-90 minutes
loadquarterlybalancesheet:    40-100 minutes
+ 49 more loaders...
TOTAL: ~300+ hours (12+ days)

OPTION B (5 parallel workers):
loadquarterlyincomestatement: 10-25 minutes
loadannualincomestatement:    7-18 minutes
loadquarterlybalancesheet:    8-20 minutes
+ 49 more loaders (mix of 2-20 min each)
TOTAL: ~50-100 hours (~3-5 days with GitHub Actions parallel matrix)

WITH GITHUB ACTIONS PARALLEL (max 3 loaders at once):
All 52 loaders: ~25-40 hours (1-2 days total)
```

---

## Why Previous Batch Insert Optimization Failed

**Root Cause:** Exception handling in batch insert

```python
# BUGGY (lost rows on exception)
batch = []
for symbol in symbols:
    data = fetch(symbol)
    batch.append(data)
    
    if len(batch) >= 50:
        try:
            insert_batch(batch)
        except Exception as e:
            logging.error(e)
            # PROBLEM: batch not cleared, rows get duplicated/lost
        batch = []  # ← Should be OUTSIDE try/except or handled differently
```

**Fix:** Proper exception handling

```python
# CORRECT
batch = []
for symbol in symbols:
    try:
        data = fetch(symbol)
        batch.append(data)
        
        if len(batch) >= 50:
            insert_batch(batch)
            batch = []  # ← Only clear if insert succeeded
    except Exception as e:
        logging.error(f"Symbol {symbol}: {e}")
        # Continue processing, batch stays intact for retry
        continue
```

---

## Implementation Checklist

- [ ] Create parallel loader template with ThreadPoolExecutor
- [ ] Test with loadquarterlyincomestatement locally
- [ ] Verify 5x speedup
- [ ] Apply to other Batch 5 loaders
- [ ] Test in AWS ECS
- [ ] Monitor CloudWatch performance
- [ ] Roll out to remaining 47 loaders
- [ ] Update GitHub Actions workflow for faster execution
- [ ] Document for future reference

---

## Conclusion

**Best approach: Implement Option B (Parallel Processing)**

This gives us:
- ✓ 5-10x speed improvement
- ✓ 52 loaders complete in 1-2 days (vs 12+ days current)
- ✓ Manageable complexity
- ✓ Easy to test and debug
- ✓ Low risk of failure

Next step: Implement parallel loader template and test.

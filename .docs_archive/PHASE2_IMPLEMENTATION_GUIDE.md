# Phase 2 Implementation Guide - Parallel Processing Pattern

**Status:** Ready to implement  
**Target:** 6 financial loaders parallelized with 5x speedup each  
**Timeline:** 2-3 days

---

## The Pattern (Copy-Paste Template)

### Step 1: Add Imports
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
```

### Step 2: Create Worker Function
```python
def process_item_parallel(item_name, config):
    """
    Process a single item (sector, metric, etc) - runs in parallel thread
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # YOUR EXISTING PROCESSING CODE HERE
        # (the code currently in the for loop for single item)
        
        cursor.close()
        conn.close()
        return {"item": item_name, "status": "success"}
    except Exception as e:
        return {"item": item_name, "status": "error", "error": str(e)}
```

### Step 3: Replace Sequential Loop With Parallel
```python
# BEFORE (sequential):
for item in items:
    process_item(item)

# AFTER (parallel):
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(process_item_parallel, item, config): item 
               for item in items}
    
    completed = 0
    for future in as_completed(futures):
        result = future.result()
        completed += 1
        if completed % 10 == 0:  # Log progress every 10 items
            logger.info(f"Processed {completed}/{len(items)} items")
```

---

## Phase 2 Loaders - Implementation Checklist

### 1. loadsectors.py (887 lines)
**What to parallelize:** Sector processing loop (line 700)

```
Current: for sector in sectors:
Target:  ThreadPoolExecutor with 5 workers processing sectors in parallel
Impact:  45 min → 10 min (4.5x speedup)
```

**Changes needed:**
- [ ] Add imports
- [ ] Create `process_sector_parallel()` function
- [ ] Replace loop at line 700 with ThreadPoolExecutor
- [ ] Add progress logging every 5 sectors

---

### 2. loadecondata.py (677 lines)
**What to parallelize:** Economic data fetching loop

```
Current: Fetches ~100 economic indicators sequentially
Target:  5 workers fetch 5 indicators in parallel
Impact:  35 min → 8 min (4.4x speedup)
```

**Changes needed:**
- [ ] Add imports
- [ ] Create `fetch_econ_indicator_parallel()` function
- [ ] Replace main fetch loop with ThreadPoolExecutor
- [ ] Handle rate limiting per worker (1-2 req/sec each)

---

### 3. loadfactormetrics.py (3,794 lines - COMPLEX)
**What to parallelize:** Symbol processing loop

```
Current: for symbol in symbols: calculate_factors()
Target:  5 workers each process different symbols
Impact:  90 min → 20 min (4.5x speedup)
```

**Changes needed:**
- [ ] Add imports
- [ ] Create `calculate_factors_for_symbol_parallel()` function
- [ ] Find main symbol loop (likely around line 1500-2000)
- [ ] Replace with ThreadPoolExecutor
- [ ] Be careful with numpy operations (thread-safe)

---

### 4. loadmarket.py (869 lines)
**Status:** Partially parallelized - COMPLETE IT

```
Current: Some parallel, some serial
Target:  Full parallelization of all market data fetching
Impact:  Already good, optimize remaining parts
```

**Changes needed:**
- [ ] Review current implementation
- [ ] Apply same pattern to any remaining sequential sections
- [ ] Add batch insert optimization

---

### 5. loadstockscores.py (587 lines)
**What to parallelize:** Stock scoring calculation loop

```
Current: for stock in all_stocks: calculate_score()
Target:  5 workers each score different stocks
Impact:  40 min → 10 min (4x speedup)
```

**Changes needed:**
- [ ] Add imports
- [ ] Create `calculate_score_parallel()` function
- [ ] Replace scoring loop with ThreadPoolExecutor
- [ ] Batch insert results (50-stock batches)

---

### 6. loadecondata.py ALTERNATIVE (if needed)
**Status:** May use different loader if exists

```
Current: Unknown
Target:  Apply same parallel pattern
Impact:  Similar 4-5x improvement
```

---

## Batch Insert Optimization (ALL 6)

### Before (individual inserts):
```python
for row in data:
    cursor.execute("INSERT INTO table VALUES (...)", row_data)
    conn.commit()  # 1 commit per row!
```
**Cost:** 5,000 rows = 5,000 commits = SLOW

### After (batch inserts):
```python
batch = []
for row in data:
    batch.append(row_data)
    if len(batch) >= 50:  # Insert 50 at a time
        cursor.executemany("INSERT INTO table VALUES (...)", batch)
        conn.commit()  # 1 commit per 50 rows
        batch = []

if batch:  # Insert remaining
    cursor.executemany("INSERT INTO table VALUES (...)", batch)
    conn.commit()
```
**Cost:** 5,000 rows = 100 commits = 50x FASTER

### Implementation (add to each worker):
```python
def batch_insert(cursor, table, data, batch_size=50):
    """Insert data in batches"""
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        placeholders = ','.join(['%s'] * len(batch[0]))
        sql = f"INSERT INTO {table} VALUES " + ','.join([f'({placeholders})'] * len(batch))
        
        flat_data = [val for row in batch for val in row]
        cursor.execute(sql, flat_data)
```

---

## Error Handling Pattern

```python
def process_with_retry(item, max_retries=3):
    """Process with automatic retry on failure"""
    for attempt in range(max_retries):
        try:
            return process_item_parallel(item)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
                logger.warning(f"Retry {attempt+1}/{max_retries} for {item} in {wait:.1f}s")
                time.sleep(wait)
            else:
                logger.error(f"Failed after {max_retries} attempts: {item}")
                raise
```

---

## Performance Measurement

### Add to each loader:
```python
import time

start_time = time.time()
logger.info(f"Starting loader with {num_items} items, 5 workers...")

# ... parallel processing ...

elapsed = time.time() - start_time
rate = num_items / elapsed if elapsed > 0 else 0

logger.info(f"[OK] Completed: {num_items} items in {elapsed:.1f}s ({rate:.1f} items/sec)")
```

---

## Execution Order (Sequential Days)

### Day 1: loadsectors.py + loadecondata.py
- Simplest to parallelize
- Most straightforward loops
- Good examples for team learning

### Day 2: loadstockscores.py
- Similar pattern to Day 1
- Good validation of approach

### Day 3: loadfactormetrics.py
- Complex file (3,794 lines)
- Most impactful (90→20 min)
- Last because most complex

### Day 4: Complete loadmarket.py + Testing
- Finish implementation
- Test all 5 loaders together
- Measure combined speedup

---

## Success Criteria per Loader

| Loader | Before | After | Target | Status |
|--------|--------|-------|--------|--------|
| loadsectors | 45m | 10m | 4-5x | ⏳ Pending |
| loadecondata | 35m | 8m | 4-5x | ⏳ Pending |
| loadstockscores | 40m | 10m | 4x | ⏳ Pending |
| loadfactormetrics | 90m | 20m | 4-5x | ⏳ Pending |
| loadmarket | 50m | 12m | 4x | ⏳ Pending |

**Total Phase 2:** 260m → 60m = **4.3x system speedup**

---

## Testing Protocol

### For each loader after implementation:
1. Run locally with test data (10% of symbols)
2. Verify row counts match expected
3. Check CloudWatch logs for no errors
4. Measure actual execution time
5. Compare with baseline

### Integration test (all 5 together):
1. Commit all 5 optimized loaders
2. Trigger GitHub Actions
3. Monitor ECS task execution
4. Verify all 5 run in parallel (max ~15 min for slowest)
5. Confirm 4-5x speedup achieved

---

## Common Pitfalls to Avoid

❌ **Don't:**
- Share database connections across threads (not thread-safe)
- Modify shared data structures without locks
- Forget to close connections in worker threads
- Use `conn.commit()` too frequently in threads

✓ **Do:**
- Create new connection per worker thread
- Use thread-safe operations (Queue, etc. if sharing state)
- Close connections in finally block
- Batch commits (50-row batches)

---

## Quick Reference Commands

```bash
# Test locally
python3 loadsectors.py

# Monitor CloudWatch logs after deployment
aws logs tail /ecs/algo-loadsectors --follow

# Check execution time
grep "Completed:" /ecs/algo-loadsectors

# Compare performance (before vs after)
# Before: "Completed: 11 sectors in 2400.5s"
# After:  "Completed: 11 sectors in 480.2s"  ← 5x faster!
```

---

## Questions?

Refer back to `OPTIMIZATION_STRATEGY.md` for detailed explanation  
Refer to `AWS_SERVICES_OPTIMIZATION.md` for rate limit handling  
Refer to `PHASE2_READINESS.md` for overall plan  

---

*Phase 2 Implementation Guide v1.0*  
*Ready to execute - start with loadsectors.py*  

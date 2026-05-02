# Parallel Loader Optimization Guide
**Implementation Status:** Template + Example Created  
**Next Steps:** Apply to all 52 loaders

## Quick Summary

Converting loaders from serial to parallel processing is simple:

**Before (Serial - 45+ minutes):**
```python
for symbol in symbols:
    rows = load_data(symbol)
    insert_data(rows)
```

**After (Parallel - 5-25 minutes):**
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(load_data, s): s for s in symbols}
    for future in as_completed(futures):
        rows = future.result()
        insert_data(rows)
```

---

## Implementation Status

### ✅ COMPLETED
- `loadquarterlyincomestatement.py` - Fully parallel (ThreadPoolExecutor)
- `parallel_loader_template.py` - Reusable base class
- Architecture analysis document created
- Performance projections: 5-25x speedup

### 🔄 IN PROGRESS
- Need to apply to remaining 51 loaders

### ⏳ TODO
- Test in AWS ECS
- Verify performance improvement
- Roll out to all loaders

---

## How to Convert a Loader to Parallel

### Method 1: Quick Update (5 minutes)

**Step 1:** Add imports at the top
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

**Step 2:** Find the main loop (usually in `main()` function)
```python
# BEFORE
for i, symbol in enumerate(symbols):
    rows = load_for_symbol(cur, symbol)
    total_rows += rows
    if (i + 1) % 10 == 0:
        conn.commit()
```

**Step 3:** Replace with parallel version
```python
# AFTER
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(load_for_symbol_data, symbol): symbol
        for symbol in symbols
    }
    
    for i, future in enumerate(as_completed(futures)):
        symbol = futures[future]
        try:
            rows = future.result()
            total_rows += rows
            if (i + 1) % 10 == 0:
                conn.commit()
        except Exception as e:
            logging.error(f"Error with {symbol}: {e}")
            continue
```

**Step 4:** Reduce request delay (since parallel)
```python
REQUEST_DELAY = 0.1  # Change from 0.5 to 0.1
```

---

## Why ThreadPoolExecutor?

### Advantages
✓ Simple to implement  
✓ Built-in Python library  
✓ Handles resource management automatically  
✓ Easy error handling  
✓ Works well with I/O bound tasks  

### How It Works
1. Submit 5 tasks at once (5 workers)
2. Tasks run in parallel
3. Main thread processes results as they complete
4. When a worker finishes, it gets the next task

### Visual
```
Time →
Worker 1: [Symbol 1    Symbol 6    Symbol 11   ...]
Worker 2: [Symbol 2    Symbol 7    Symbol 12   ...]
Worker 3: [Symbol 3    Symbol 8    Symbol 13   ...]
Worker 4: [Symbol 4    Symbol 9    Symbol 14   ...]
Worker 5: [Symbol 5    Symbol 10   Symbol 15   ...]

4969 symbols / 5 workers = ~994 per worker
At 1 symbol/second = ~17 minutes (vs 80 minutes serial)
```

---

## Common Patterns by Loader Type

### Pattern 1: Database Loaders (14 loaders)
Fetch from yfinance, insert into DB

**Key Changes:**
- Use ThreadPoolExecutor for symbol processing
- Implement batch inserts (50 rows at a time)
- Reduce REQUEST_DELAY from 0.5 to 0.1

**Affected:**
- loadquarterlyincomestatement.py ✓ (DONE)
- loadannualincomestatement.py (TODO)
- loadquarterlybalancesheet.py (TODO)
- loadannualbalancesheet.py (TODO)
- loadquarterlycashflow.py (TODO)
- loadannualcashflow.py (TODO)
- loaddailycompanydata.py (TODO)
- loadbuyselldaily.py (TODO)
- loadbuysellweekly.py (TODO)
- loadbuysellmonthly.py (TODO)
- loadetfpricedaily.py (TODO)
- loadetfpriceweekly.py (TODO)
- loadearningshistory.py (TODO)
- loadstockscores.py (TODO)

### Pattern 2: Simple Price Loaders (multiple)
Fetch OHLCV data for each symbol

**Key Changes:**
Same as Pattern 1, just different data extraction

### Pattern 3: Complex Loaders (factor metrics, sectors, etc.)
More complex business logic

**Key Changes:**
May need custom handling, but ThreadPoolExecutor still applies

---

## Before/After Performance

### Expected Times (4969 symbols)

| Loader | Serial | Parallel | Speedup |
|--------|--------|----------|---------|
| Quarterly Income | 60m | 12m | 5x |
| Annual Income | 45m | 9m | 5x |
| Quarterly Balance | 50m | 10m | 5x |
| Annual Balance | 55m | 11m | 5x |
| Quarterly Cash Flow | 40m | 8m | 5x |
| Annual Cash Flow | 35m | 7m | 5x |
| Daily Company Data | 90m | 18m | 5x |
| Buy/Sell Daily | 70m | 14m | 5x |
| Buy/Sell Weekly | 65m | 13m | 5x |
| Buy/Sell Monthly | 60m | 12m | 5x |
| ETF Price Daily | 30m | 6m | 5x |
| ETF Price Weekly | 25m | 5m | 5x |
| Earnings History | 35m | 7m | 5x |
| Stock Scores | 45m | 9m | 5x |
| **Batch 5 Total** | **710 min** | **142 min** | **5x** |
| **All 52 Loaders** | **~1200 min** | **~240 min** | **5x** |
| **With GitHub Actions Parallel** | **~300 min** | **~60 min** | **5x** |

---

## Testing Checklist

Before applying to all loaders:

```
[ ] Test locally (with test database)
    python3 loadquarterlyincomestatement.py
    
[ ] Verify:
    - Completes in ~5-25 minutes
    - All rows inserted
    - No data corruption
    - Handles errors gracefully
    
[ ] Test in AWS:
    - Create ECS task with parallel version
    - Verify CloudWatch logs show parallel execution
    - Check DB for correct data
    - Monitor CPU/memory usage
    
[ ] Performance benchmarks:
    - Measure actual time taken
    - Verify 5-10x speedup
    - Compare serial vs parallel
    - Check error rates
```

---

## Common Pitfalls & Fixes

### Pitfall 1: Database Connection in Threads
**Problem:** Multiple threads sharing one DB connection  
**Solution:** Each thread opens its own connection
```python
# WRONG
for symbol in as_completed(futures):
    cur.execute(...)  # ← Shared connection, thread-unsafe

# RIGHT
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(load_symbol, s) for s in symbols]
    # Each load_symbol() opens its own connection inside
```

### Pitfall 2: Losing Data on Error
**Problem:** Exception in one thread loses accumulated batch  
**Solution:** Use try/except properly
```python
# WRONG
batch.extend(future.result())  # If this throws, batch is lost

# RIGHT
try:
    rows = future.result()
    batch.extend(rows)
except Exception as e:
    logging.error(f"Error: {e}")
    continue  # Skip this symbol, continue with batch
```

### Pitfall 3: Rate Limiting
**Problem:** 5 parallel requests hit rate limits  
**Solution:** Reduce delay or use queue-based approach
```python
REQUEST_DELAY = 0.1  # Reduced from 0.5
# 5 workers × 1 request/second = 5 req/sec (acceptable)
```

### Pitfall 4: Batch Insert Bugs
**Problem:** Previous attempts had exception handling issues  
**Solution:** Use execute_values() for batch operations
```python
from psycopg2.extras import execute_values

execute_values(cur, """
    INSERT INTO table (col1, col2) VALUES %s
    ON CONFLICT (col1) DO UPDATE SET col2 = EXCLUDED.col2
""", data)  # ← Handles batch atomically
```

---

## Quick Migration Script

To help speed up conversion, here's a template to use:

```bash
#!/bin/bash
# For each loader, replace the main loop pattern

for loader in loadannualincomestatement loadquarterlybalancesheet \
               loadannualbalancesheet loadquarterlycashflow \
               loadannualcashflow loaddailycompanydata; do
               
    echo "Updating $loader.py..."
    
    # 1. Add import (if not present)
    sed -i '1a from concurrent.futures import ThreadPoolExecutor, as_completed' "$loader.py"
    
    # 2. Update REQUEST_DELAY
    sed -i 's/REQUEST_DELAY = 0.5/REQUEST_DELAY = 0.1/' "$loader.py"
    
    # 3. Manual update of main loop needed (too complex for sed)
    echo "  ⚠ Manual update of main() function required"
    
done
```

---

## Deploy Strategy

### Phase 1: Key Loaders (Batch 5)
Priority: Financial statements (6 loaders)
- loadquarterlyincomestatement ✓
- loadannualincomestatement
- loadquarterlybalancesheet
- loadannualbalancesheet
- loadquarterlycashflow
- loadannualcashflow

### Phase 2: Secondary Loaders (8 loaders)
- Daily company data
- Buy/sell signals (daily, weekly, monthly)
- ETF prices (daily, weekly)

### Phase 3: Remaining Loaders (38 loaders)
- Earnings history
- Stock scores
- Sectors
- Factor metrics
- All others

---

## Success Metrics

After applying parallel optimization:

✅ All 52 loaders process 5-10x faster  
✅ Batch 5 completes in ~2 hours (vs 12 hours)  
✅ All 52 complete in ~3-4 hours (vs 300 hours)  
✅ No data loss or corruption  
✅ Proper error handling and logging  
✅ CPU utilization stays within ECS limits  
✅ Database connections managed properly  

---

## Next Steps

1. ✅ Create parallel template and architecture analysis
2. ✅ Implement for loadquarterlyincomestatement
3. → Apply to remaining Batch 5 loaders
4. → Test in AWS ECS
5. → Roll out to all 52 loaders
6. → Update GitHub Actions workflow
7. → Monitor and validate performance

---

## Reference Implementation

See `loadquarterlyincomestatement.py` for complete parallel implementation.
See `parallel_loader_template.py` for reusable base class.

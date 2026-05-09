# Parallelism & Batch Tuning Guide

Comprehensive guide to tuning parallelism and batch settings for optimal performance.

## Quick Reference

| Setting | Default | Recommended | When to Increase |
|---------|---------|-------------|-----------------|
| `--parallelism` | 8 | 8 | CPU cores available |
| `batch_size` | 500 | 500-1000 | <200ms per insert |
| `commit_every_n_symbols` | 50 | 50-100 | High error rate |
| Max DB connections | 100 | 150-200 | Hitting limit at parallelism=8 |

## Understanding Parallelism

### What It Is

Parallelism = number of concurrent worker threads fetching and loading data

```
parallelism=1 (serial):
- 1 thread fetches symbol 1
- Wait for DB insert
- 1 thread fetches symbol 2
- Wait for DB insert
- ...
- Total time: ~1 min per 100 symbols

parallelism=8 (parallel):
- 8 threads fetch symbols 1-8 in parallel
- Insert rows from each thread concurrently
- 8 threads fetch symbols 9-16 while first batch inserts
- ...
- Total time: ~8 min per 800 symbols (vs 80 min serial)
```

### How It Works

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=parallelism) as executor:
    # Submit 8 symbols in parallel
    for symbol in symbols:
        future = executor.submit(fetch_and_load, symbol)

    # Threads run concurrently:
    # - Thread 1: fetch(AAPL), load(AAPL)
    # - Thread 2: fetch(GOOGL), load(GOOGL)
    # - ... up to 8 threads
    # - Thread 1: fetch(next symbol) while Thread 2 still loading
```

## Tuning Strategy

### Step 1: Determine Optimal Parallelism

Goal: Balance between speed and resource constraints

```bash
# Test different parallelism levels (1000 symbols each)
for p in 1 2 4 8 12 16; do
    echo "Testing parallelism=$p"
    time python3 loadpricedaily.py --parallelism $p --symbols 1000
done

# Results will look like:
# parallelism=1:  real  50m30s    # Baseline
# parallelism=2:  real  27m15s    # 50% faster (2x speedup)
# parallelism=4:  real  15m20s    # 70% faster (3.3x speedup)
# parallelism=8:  real  8m45s     # 82% faster (5.8x speedup)
# parallelism=12: real  8m30s     # 83% faster (6.0x speedup) - diminishing returns
# parallelism=16: real  10m20s    # Worse - too many connections competing
```

**Optimal parallelism**: Point where adding more threads provides <10% improvement

#### Formula: Optimal Parallelism

```
optimal_parallelism = min(
    CPU_CORES,                    # Don't exceed available CPUs
    (MAX_DB_CONNECTIONS * 0.8) / AVG_CONNECTIONS_PER_WORKER,  # DB limit
    RAM_GB * 100 / AVG_MB_PER_WORKER  # Memory limit
)

Example:
- CPU cores: 4
- Max DB connections: 100
- Connections per worker: 1
- Memory: 8GB, 50MB per worker

optimal = min(
    4,                    # CPU bound
    (100 * 0.8) / 1,      # 80 (DB bound)
    8 * 100 / 50          # 16 (Memory bound)
)
= 4  # CPU is the limiting factor
```

### Step 2: Determine Optimal Batch Size

Goal: Balance between memory usage and database roundtrips

```bash
# Test different batch sizes (parallelism=8, 1000 symbols)
for b in 100 250 500 750 1000; do
    echo "Testing batch_size=$b"
    time python3 -c "
        loader = MyLoader(batch_size=$b)
        loader.load_symbols(1000)
    "
done

# Results:
# batch_size=100:   5m15s   (many small INSERT roundtrips)
# batch_size=250:   4m20s   (fewer roundtrips)
# batch_size=500:   3m45s   (good balance) ← Recommended
# batch_size=750:   3m42s   (minimal improvement)
# batch_size=1000:  3m40s   (<1% improvement, uses more memory)
```

**Optimal batch_size**: Where adding 250 more rows gives <5% improvement

#### Formula: Optimal Batch Size

```
optimal_batch_size = min(
    1000,                         # PostgreSQL INSERT limit
    AVAILABLE_RAM_MB / (DATA_PER_ROW_KB * PARALLELISM),
    (DATABASE_INSERT_TIME_MS / 100)  # Target <100ms per insert
)

Example (daily prices):
- Available RAM: 8GB
- Data per row: 0.1KB (5 columns × ~20 bytes)
- Parallelism: 8
- Target insert time: <100ms

= min(
    1000,
    8000 / (0.1 * 8),     # 10,000 (plenty)
    100                   # Target insert rate
)
= 100  # But testing shows 500 is better for this data

Note: Actual optimal depends on INSERT query complexity
```

### Step 3: Determine Commit Interval

Goal: Balance between failure recovery and transaction overhead

```bash
# Test different commit intervals (parallelism=8, batch_size=500, 1000 symbols)
for c in 10 25 50 100 250; do
    echo "Testing commit_every_n_symbols=$c"
    time python3 -c "
        loader = MyLoader(batch_size=500, commit_every_n_symbols=$c)
        loader.load_symbols(1000)
    "
done

# Results:
# commit_every_n=10:   4m30s   (many small transactions)
# commit_every_n=25:   4m05s   (fewer commits)
# commit_every_n=50:   3m45s   (good balance) ← Recommended
# commit_every_n=100:  3m42s   (<1% improvement)
# commit_every_n=250:  3m41s   (same, but recovery slower)
```

**Optimal commit_interval**: Where doubling commit size gives <5% improvement

#### Formula: Optimal Commit Interval

```
optimal_commit_interval = max(
    1,                                # Must commit at least sometimes
    BATCH_SIZE * ACCEPTABLE_LOSS_ROWS / TOTAL_SYMBOLS,
    ACCEPTABLE_COMMIT_TIME_SECONDS
)

Example (1000 symbols, 500 batch size):
- Acceptable row loss on failure: 5000 rows (5%)
- Total symbols: 1000
- Acceptable commit time: 1 second

= max(
    1,
    500 * (1000 * 0.05) / 1000,  # 25 symbols
    1  # 1 second
)
= 25  # But empirically, 50 is better

Note: Longer intervals batch more inserts = better throughput
      But more rows to retry on failure
```

## Configuration Examples

### Development (Local, Small Dataset)

```python
# Optimize for speed (since DB is local)
loader = OptimizedLoader(
    batch_size=1000,              # Largest batches
    commit_every_n_symbols=100,   # Fewer commits
)

# Run with high parallelism (local DB can handle it)
python3 loadpricedaily.py --parallelism 12 --symbols 100
```

### Production - Stable (Large Dataset, Limited Resources)

```python
# Conservative settings for reliability
loader = OptimizedLoader(
    batch_size=500,               # Standard
    commit_every_n_symbols=50,    # Frequent checkpoints
)

# Moderate parallelism (respect connection limits)
python3 loadpricedaily.py --parallelism 8 --symbols 7000
```

### Production - High Performance (Large Dataset, Plenty of Resources)

```python
# Aggressive settings for throughput
loader = OptimizedLoader(
    batch_size=1000,              # Larger batches
    commit_every_n_symbols=100,   # Fewer commits
)

# High parallelism if DB allows
python3 loadpricedaily.py --parallelism 12 --symbols 7000
# Requires: max_connections >= 150 in PostgreSQL
```

### AWS Lambda (Constrained Resources)

```python
# Minimal resources: 128MB memory, 1 CPU equivalent
loader = OptimizedLoader(
    batch_size=250,               # Smaller batches (less memory)
    commit_every_n_symbols=25,    # More frequent commits
)

# Low parallelism (Lambda memory is limited)
python3 loadpricedaily.py --parallelism 2 --symbols 100
```

## Performance Monitoring

### Metrics to Track

During a load, monitor:

```python
import time
import psycopg2

start_time = time.time()

# Track every symbol
for i, symbol in enumerate(symbols):
    fetch_start = time.time()
    
    data = fetch_from_api(symbol)
    fetch_time_ms = (time.time() - fetch_start) * 1000
    
    insert_start = time.time()
    insert_rows(data)
    insert_time_ms = (time.time() - insert_start) * 1000
    
    # Log every 100 symbols
    if (i+1) % 100 == 0:
        elapsed = time.time() - start_time
        rate = (i+1) / elapsed  # symbols per second
        remaining = (len(symbols) - i-1) / rate  # seconds remaining
        
        print(f"Progress: {i+1}/{len(symbols)} ({rate:.1f}/sec, ETA {remaining/60:.1f}min)")
        print(f"  Fetch: {fetch_time_ms:.0f}ms, Insert: {insert_time_ms:.0f}ms")
        print(f"  Active connections: {count_db_connections()}")
```

### CloudWatch Metrics

After load, check metrics:

```bash
aws cloudwatch get-metric-statistics \
  --namespace "algo/ConnectionPool/daily_prices" \
  --metric-name AvgWaitTime \
  --start-time 2026-05-09T12:00:00Z \
  --end-time 2026-05-09T13:00:00Z \
  --period 60 \
  --statistics Average,Maximum
```

Expected: Avg <100ms, Max <500ms

## Troubleshooting

### "too many connections" Error

**Cause**: Parallelism × connections_per_worker > database max_connections

**Solution**: Reduce parallelism or increase max_connections

```bash
# Check current max_connections
psql -U postgres -c "SHOW max_connections;"

# Increase max_connections (requires restart)
aws rds modify-db-instance \
  --db-instance-identifier algo-db \
  --db-parameter-group-name algo-pg14-params-new \
  --apply-immediately
```

### High Memory Usage

**Cause**: Batch size too large or too many parallel threads

**Solution**: Reduce batch_size or parallelism

```python
# Before (peak 1GB)
loader = OptimizedLoader(batch_size=2000, commit_every_n_symbols=100)

# After (peak 300MB)
loader = OptimizedLoader(batch_size=500, commit_every_n_symbols=50)
```

### Slow Performance (No Speedup from Parallelism)

**Cause**: API call time dominates (not DB insert time)

**Solution**: Implement request batching or caching

```python
# Bad: 8 threads, but API calls are serialized
with ThreadPoolExecutor(max_workers=8) as executor:
    for symbol in symbols:
        executor.submit(fetch_one_symbol, symbol)  # 1 call each

# Better: Batch API calls
symbols_batch = list(chunked(symbols, 100))  # Groups of 100
with ThreadPoolExecutor(max_workers=8) as executor:
    for batch in symbols_batch:
        executor.submit(fetch_symbols_batch, batch)  # 1 call per batch
```

### Diminishing Returns from More Parallelism

**Cause**: Database becoming bottleneck

**Solution**: Check DB resource usage

```bash
# Check if CPU-bound
mpstat 1 5 | grep CPU

# Check if I/O-bound
iostat -x 1 5 | grep sda

# Check if connection-limited
psql -c "SELECT count(*) FROM pg_stat_activity;"

# If all low, may be API-limited instead
# (Alpaca: 50 req/sec, IEX: varies by plan)
```

## Scaling Considerations

### Horizontal Scaling (Multiple Loaders)

Run multiple loaders in parallel for different symbol subsets:

```bash
# Loader 1: Symbols A-D
python3 loadpricedaily.py --parallelism 8 --symbols-prefix A-D &

# Loader 2: Symbols E-H
python3 loadpricedaily.py --parallelism 8 --symbols-prefix E-H &

# Loader 3: Symbols I-L
python3 loadpricedaily.py --parallelism 8 --symbols-prefix I-L &

wait  # Wait for all to finish
```

Total connections: 3 loaders × 8 parallelism = 24 connections ✓

### Vertical Scaling (More Powerful Database)

When single loader hits limits, upgrade database:

```bash
# db.t3.micro (100 conn max) → db.t3.small (200 conn max)
aws rds modify-db-instance \
  --db-instance-identifier algo-db \
  --db-instance-class db.t3.small \
  --apply-immediately

# Now can run with higher parallelism
python3 loadpricedaily.py --parallelism 16
```

## Adaptive Tuning

Automatically adjust parallelism based on system metrics:

```python
import psutil

def get_optimal_parallelism():
    # CPU available
    cpu_cores = psutil.cpu_count()
    
    # Memory available
    mem_percent = psutil.virtual_memory().percent
    mem_available_mb = psutil.virtual_memory().available / 1024 / 1024
    
    # Database connections available
    db_available = get_db_available_connections()
    
    # Estimate based on constraints
    optimal = min(
        cpu_cores,
        int(mem_available_mb / 150),  # ~150MB per worker
        db_available // 2  # Use half available to leave margin
    )
    
    # Ensure at least 1, at most 16
    return max(1, min(optimal, 16))

# Use
parallelism = get_optimal_parallelism()
print(f"Adaptive parallelism: {parallelism}")
```

## References

- Code: `loader_base_optimized.py`, `loadpricedaily.py`
- Testing: `LOADER_TESTING_GUIDE.md`
- Monitoring: `CONNECTION_POOL_MONITORING.md`
- PostgreSQL docs: https://www.postgresql.org/docs/14/sql-syntax.html#SQL-SYNTAX-LEXICAL-STRUCTURE-OPERATORS

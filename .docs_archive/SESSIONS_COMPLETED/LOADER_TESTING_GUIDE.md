# Loader Testing & Performance Validation

This guide walks through testing the optimized loaders with parallelism=8 to validate performance improvements.

## Quick Start: Test Price Loader

```bash
# 1. Start local PostgreSQL (if not running)
docker-compose -f docker-compose.postgres.yml up -d

# 2. Set up environment
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=stocks
export DB_NAME=stocks
export WATERMARK_DIR=./.watermarks
export LOG_LEVEL=INFO

# 3. Run with parallelism=8 (optimized)
time python3 loadpricedaily.py --parallelism 8 --symbols 100

# 4. Monitor in separate terminal
# Watch connection count
watch -n 1 'psql -h localhost -U stocks -d stocks -c "SELECT count(*) as connections FROM pg_stat_activity WHERE datname='"'"'stocks'"'"';"'

# Watch memory
watch -n 1 'ps aux | grep loadpricedaily'

# Watch performance metrics
tail -f ./.watermarks/daily_prices.json
```

## Performance Baseline Tests

### Test 1: Small Load (100 symbols)

Goal: Validate basic functionality, measure baseline

```bash
# Run with parallelism=8
time python3 loadpricedaily.py --parallelism 8 --symbols 100

# Expected results:
# - Time: 1-2 minutes
# - Memory peak: 200-300 MB
# - Connections peak: 8
# - Success: true
```

### Test 2: Medium Load (1000 symbols)

Goal: Validate scaling, measure throughput

```bash
time python3 loadpricedaily.py --parallelism 8 --symbols 1000

# Expected results:
# - Time: 10-15 minutes
# - Memory peak: 300-500 MB
# - Connections peak: 8-10
# - Success: true
# - Throughput: ~100 symbols/min
```

### Test 3: Full Load (7000+ symbols)

Goal: Full production-like test

```bash
time python3 loadpricedaily.py --parallelism 8

# Expected results:
# - Time: 70-120 minutes (depending on API rate limits)
# - Memory peak: 400-600 MB
# - Connections peak: 8-12
# - API calls: ~70-80% fewer than serial load
# - Success: true
```

### Test 4: Parallelism Comparison

Compare parallelism=4 vs parallelism=8 vs serial (parallelism=1)

```bash
# Baseline: Serial loading
echo "=== Testing parallelism=1 (serial) ==="
time python3 loadpricedaily.py --parallelism 1 --symbols 500 2>&1 | tee results_parallel_1.log

# Current: Parallelism 4
echo "=== Testing parallelism=4 ==="
time python3 loadpricedaily.py --parallelism 4 --symbols 500 2>&1 | tee results_parallel_4.log

# Optimized: Parallelism 8
echo "=== Testing parallelism=8 ==="
time python3 loadpricedaily.py --parallelism 8 --symbols 500 2>&1 | tee results_parallel_8.log

# Compare results
echo "=== COMPARISON ==="
echo "Parallel=1 (serial):" && grep "real" results_parallel_1.log
echo "Parallel=4:" && grep "real" results_parallel_4.log
echo "Parallel=8:" && grep "real" results_parallel_8.log
```

**Expected**: Parallelism=8 should be ~50-100% faster than serial

## Monitoring During Load

### Terminal 1: Run Loader

```bash
python3 loadpricedaily.py --parallelism 8 --symbols 1000
```

### Terminal 2: Watch Connections

```bash
watch -n 2 'psql -h localhost -U stocks -d stocks -c \
  "SELECT count(*) as connections, max(extract(epoch from (now() - query_start))) as oldest_query_sec FROM pg_stat_activity WHERE datname='"'"'stocks'"'"' AND state != '"'"'idle'"'"';"'
```

Expected output evolution:
- Start: 1 connection (initial)
- During load: 5-8 active connections
- End: 1 connection (cleanup)

### Terminal 3: Watch Memory

```bash
# macOS
while true; do ps aux | grep loadpricedaily | grep -v grep | awk '{print "Memory:", $6/1024 "MB"}'; sleep 5; done

# Linux
while true; do ps aux | grep loadpricedaily | grep -v grep | awk '{print "Memory:", $6 "KB", "=", $6/1024 "MB"}'; sleep 5; done
```

### Terminal 4: Watch Database Size

```bash
watch -n 5 'psql -h localhost -U stocks -d stocks -c \
  "SELECT 
    (SELECT count(*) FROM price_daily) as price_records,
    (SELECT count(*) FROM stock_symbols) as symbols,
    pg_size_pretty(pg_database_size('"'"'stocks'"'"')) as total_size;"'
```

## Advanced Testing

### Test API Rate Limiting

Loaders should respect API rate limits (Alpaca: 50 req/sec)

```bash
# Monitor API calls
# Create a filter in loadpricedaily.py to log API calls:

import time
api_call_times = []

def fetch_bars(symbol):
    api_call_times.append(time.time())
    # Remove calls older than 1 second
    api_call_times = [t for t in api_call_times if time.time() - t < 1]
    
    if len(api_call_times) > 50:
        # Rate limited - wait
        time.sleep(0.1)
    
    # ... actual API call ...
```

### Test Connection Pool Monitoring

Verify connection pool metrics are publishing:

```bash
# Check metrics after load completes
aws cloudwatch get-metric-statistics \
  --namespace "algo/ConnectionPool/daily_prices" \
  --metric-name UtilizationPercent \
  --start-time 2026-05-09T12:00:00Z \
  --end-time 2026-05-09T13:00:00Z \
  --period 60 \
  --statistics Maximum,Average

# Expected: Max ~80%, Average ~50-60%
```

### Test Watermark Functionality

Verify watermarks prevent re-loading:

```bash
# First run
python3 loadpricedaily.py --parallelism 8 --symbols 100
# Should load ~100 symbols

# Check watermark
cat .watermarks/daily_prices.json
# Should show: "last_timestamp": "2026-05-09T...", "status": "success"

# Second run (same day)
python3 loadpricedaily.py --parallelism 8 --symbols 100
# Should skip most data (loaded more recently)
# Should load only new/updated data

# Reset watermark (full reload)
rm .watermarks/daily_prices.json

# Third run
python3 loadpricedaily.py --parallelism 8 --symbols 100
# Should load full historical data again
```

### Test Error Recovery

Simulate failures and verify recovery:

```bash
# 1. Kill database mid-load
# In terminal 2, while load is running:
# killall postgres  (or similar)

# Loader should:
# - Catch connection error
# - Mark watermark as "failed"
# - Exit gracefully
# - On retry, resume from same watermark

# 2. Test rate limit recovery
# Modify loadpricedaily.py to simulate API rate limit:
if symbol == "AAPL":  # Simulate rate limit on 100th symbol
    raise Exception("429 - Rate Limited")

# Loader should:
# - Catch exception
# - Retry with backoff
# - Mark as failed if too many retries
# - On retry, resume from last successful symbol
```

## Performance Metrics to Track

| Metric | Baseline (Para=1) | Target (Para=8) | Success Criteria |
|--------|-------------------|-----------------|-----------------|
| Time (1K symbols) | 40-50 min | 8-12 min | 75% faster |
| Memory peak | 300 MB | 300-400 MB | Similar or lower |
| Connections peak | 1-2 | 8-10 | Matches parallelism |
| API calls (1K symbols) | ~1000 | ~100-150 | 85% reduction |
| Database writes | ~1000 inserts | ~20 batch inserts | Fewer roundtrips |
| Success rate | 100% | 100% | No failures |
| Watermark updates | Every 1 symbol | Every 50 symbols | Reduced commits |

## Troubleshooting Tests

### "Connection Refused"

Database not running or accessible

```bash
# Check database
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# If fails, start database
docker-compose -f docker-compose.postgres.yml up -d

# Verify
docker ps | grep postgres
```

### "Too Many Connections"

Connection limit reached (default: 100)

```bash
# Check active connections
psql -h localhost -U stocks -d stocks -c \
  "SELECT count(*) FROM pg_stat_activity;"

# Kill idle connections
psql -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
   WHERE datname='stocks' AND state='idle';"
```

### "Rate Limited" (429 Error)

Exceeding API rate limits

```python
# Add backoff to loadpricedaily.py
import time
import random

def fetch_with_backoff(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return fetch_data(symbol)
        except Exception as e:
            if "429" in str(e):
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limited, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### "Out of Memory"

Process exceeds available memory

```bash
# Monitor memory during load
while true; do
    free -h
    sleep 5
done

# If OOM: reduce parallelism or batch_size
python3 loadpricedaily.py --parallelism 4 --batch-size 250
```

## Documenting Results

Create a test report:

```markdown
# Load Test Results - [Date]

## Test Configuration
- Loader: loadpricedaily.py
- Parallelism: 8
- Symbols: 1000
- Batch Size: 500
- Commit Interval: 50 symbols

## Baseline Metrics
- **Time**: 12 minutes 45 seconds
- **Memory Peak**: 380 MB
- **Connection Peak**: 9
- **API Calls**: 150 (vs 1000 with serial)
- **Success**: ✓

## Performance Improvement
- **vs Serial (Para=1)**: 75% faster (48 min → 12 min)
- **vs Previous (Para=4)**: 40% faster (18 min → 12 min)
- **API Efficiency**: 85% reduction in API calls
- **Database Efficiency**: 50x fewer INSERT roundtrips

## Issues Found
- (none)

## Recommendations
- Ready for production deployment
- Monitor connection pool in first week
- Consider parallelism=12 for future if connections remain <80%

## Next Steps
- [ ] Deploy to staging environment
- [ ] Run 24-hour load test
- [ ] Monitor CloudWatch alarms
- [ ] Deploy to production
```

## CI/CD Testing

Integrate into automated testing:

```bash
#!/bin/bash
# test-loader.sh

set -e

echo "Running loader tests..."

# Test 1: Serial (baseline)
echo "Test 1: Serial loading"
timeout 300 python3 loadpricedaily.py --parallelism 1 --symbols 100 || true

# Test 2: Optimized
echo "Test 2: Parallel loading (optimized)"
timeout 300 python3 loadpricedaily.py --parallelism 8 --symbols 100 || true

# Test 3: Watermark functionality
echo "Test 3: Watermark test"
rm -f .watermarks/daily_prices.json
python3 loadpricedaily.py --parallelism 8 --symbols 10
python3 loadpricedaily.py --parallelism 8 --symbols 10  # Should skip some data

echo "All tests passed!"
```

## References

- Code: `loadpricedaily.py`, `loader_base_optimized.py`
- Monitoring: `connection_pool_monitor.py`
- Watermarks: `watermark_manager.py`
- Docker setup: `docker-compose.postgres.yml`

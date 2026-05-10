# Data Integrity Phase 1 - Integration Guide

## Overview

You now have three foundational components for production data quality:

1. **data_tick_validator.py** - Validates every tick before database insert
2. **data_provenance_tracker.py** - Complete audit trail for replay and debugging
3. **data_watermark_manager.py** - Atomic "load only once" guarantee

## Why This Matters

**The Problem:** Silent data corruption. Your algo could be trading on:
- Deleted ticks (API failure, fallback to stale data)
- Corrupted OHLC (volume = 0, prices negative)
- Doubled rows (loader crashed mid-run, retry loaded same data twice)
- Misaligned data (price from 2 days ago but date says today)

**The Solution:** Every tick is validated, tracked, and linked to a loader run ID. You can replay any day's trades with the exact data that was used.

## Integration Pattern

### For Existing Loaders

Here's how to integrate into an existing loader like `loadpricedaily.py`:

```python
#!/usr/bin/env python3
import psycopg2
from data_tick_validator import TickValidator, validate_price_tick
from data_provenance_tracker import DataProvenanceTracker
from data_watermark_manager import WatermarkManager

# Setup
db_conn = psycopg2.connect(...)
tracker = DataProvenanceTracker('loadpricedaily', 'price_daily', db_conn)
watermark_mgr = WatermarkManager('loadpricedaily', 'price_daily', db_conn, granularity='symbol')

# Start a new loader run
run_id = tracker.start_run(source_api='yfinance', parameters={'symbols': ['AAPL', 'MSFT']})

# For each symbol
for symbol in symbols:
    # Get current watermark (last successfully loaded date)
    watermark = watermark_mgr.get_current_watermark(symbol=symbol)
    start_date = watermark + timedelta(days=1) if watermark else old_start_date
    
    # Fetch data
    rows = fetch_data(symbol, start_date, today)
    
    # Validate and insert
    validated_rows = []
    prior_close = None
    
    for row in rows:
        # Validate each tick
        is_valid, errors = validate_price_tick(
            symbol=symbol,
            open_price=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            volume=row['volume'],
            prior_close=prior_close,
        )
        
        if not is_valid:
            # Log validation error
            tracker.record_error(
                symbol=symbol,
                error_type='DATA_INVALID',
                error_message=', '.join(errors),
                resolution='skipped',
            )
            continue
        
        # Track this tick's provenance
        provenance_id = tracker.record_tick(
            symbol=symbol,
            tick_date=row['date'],
            data=row,  # The full OHLCV data
            source_api='yfinance',
        )
        
        validated_rows.append(row)
        prior_close = row['close']
    
    # Insert all validated rows
    insert_into_price_daily(validated_rows)
    
    # ATOMICALLY update watermark (only if insert succeeded)
    success = watermark_mgr.advance_watermark(
        symbol=symbol,
        new_watermark=today,
        rows_loaded=len(validated_rows),
    )
    
    if not success:
        tracker.record_error(
            symbol=symbol,
            error_type='WATERMARK_UPDATE_FAILED',
            error_message='Failed to update watermark - will retry next run',
            resolution='retry',
        )

# Finish the run
tracker.end_run(success=True, summary={
    'symbols_processed': len(symbols),
    'total_ticks_loaded': sum of all ticks,
})
```

## Usage Scenarios

### Scenario 1: Replay a Date's Data

You want to know exactly what data was used on 2026-05-09:

```python
from data_provenance_tracker import DataProvenanceTracker

tracker = DataProvenanceTracker('loadpricedaily', 'price_daily', db_conn)

# Get the run that happened on May 9
# SELECT * FROM data_loader_runs WHERE loader_name = 'loadpricedaily' 
#                                    AND start_at::DATE = '2026-05-09'
run_id = '...'

# Get all ticks from that run
replay_data = tracker.get_run_replay_data(run_id)

# Now you have:
# - All ticks that were loaded
# - Their exact timestamps (source_timestamp vs load_timestamp)
# - Their checksums (to verify integrity)
# - Any errors that occurred

print(f"Run {run_id} loaded {len(replay_data['ticks'])} ticks")
for tick in replay_data['ticks']:
    print(f"  {tick['symbol']} {tick['tick_date']}: {tick['data_checksum']}")
```

### Scenario 2: Detect Data Corruption

You want to find if any ticks were corrupted:

```python
# In algo_data_patrol.py, add this check:
with conn.cursor() as cur:
    cur.execute("""
    SELECT symbol, tick_date, data_hash
    FROM data_provenance_log
    WHERE symbol = %s AND tick_date = %s
    """, (symbol, date))
    
    original_hash = cur.fetchone()[2]
    
    # Now fetch the tick from price_daily
    cur.execute("""
    SELECT open, high, low, close, volume
    FROM price_daily
    WHERE symbol = %s AND date = %s
    """, (symbol, date))
    
    current_data = cur.fetchone()
    current_hash = compute_hash(current_data)
    
    if current_hash != original_hash:
        logger.critical(f"DATA CORRUPTION DETECTED: {symbol} {date}")
        # Alert immediately - this is a critical issue
```

### Scenario 3: Watermark Recovery

Loader crashed mid-run on 2026-05-09. What happens on next run?

```python
# May 9 run:
watermark_mgr = WatermarkManager('loadpricedaily', 'price_daily', db_conn)

# Previous watermark was 2026-05-08
watermark = watermark_mgr.get_current_watermark(symbol='AAPL')  # Returns 2026-05-08

# Fetch data from 2026-05-09 (watermark + 1 day)
rows = fetch_data('AAPL', '2026-05-09', '2026-05-09')
insert_into_db(rows)

# Crash happens HERE before watermark update!
watermark_mgr.advance_watermark(symbol='AAPL', new_watermark='2026-05-09')  # Never runs

# May 10 run (next day):
watermark = watermark_mgr.get_current_watermark(symbol='AAPL')  # Still returns 2026-05-08!

# Fetch data from 2026-05-09 again (watermark + 1)
rows = fetch_data('AAPL', '2026-05-09', '2026-05-10')
# May 9 data is refetched. If it's the same, no problem.
# If API changed, we get new data. Either way, deterministic.

watermark_mgr.advance_watermark(symbol='AAPL', new_watermark='2026-05-10')  # Now succeeds
```

## Implementation Checklist

For each loader (loadpricedaily, loadpricweekly, loadstockscores, etc.):

- [ ] Import the three modules
- [ ] Create DataProvenanceTracker and WatermarkManager instances
- [ ] Call `tracker.start_run()` at start
- [ ] For each data fetch:
  - [ ] Get watermark via `watermark_mgr.get_current_watermark()`
  - [ ] Fetch data from watermark + 1
  - [ ] Validate each tick with `validate_price_tick()`
  - [ ] Call `tracker.record_tick()` for each valid tick
  - [ ] Insert to database
  - [ ] Call `watermark_mgr.advance_watermark()` (atomic with insert)
  - [ ] On error: `tracker.record_error()` and `watermark_mgr.record_failure()`
- [ ] Call `tracker.end_run()` at end

## Testing

### Unit Test: Tick Validator

```python
from data_tick_validator import validate_price_tick

# Test: Price bounds
is_valid, errors = validate_price_tick(
    symbol='AAPL',
    open_price=150,
    high=151,
    low=149,
    close=150.5,
    volume=5_000_000,
)
assert is_valid == True
assert errors == []

# Test: Volume sanity (too low)
is_valid, errors = validate_price_tick(
    symbol='AAPL',
    open_price=150,
    high=151,
    low=149,
    close=150.5,
    volume=0,  # Invalid!
)
assert is_valid == False
assert 'volume is zero' in errors[0]

# Test: OHLC logic (high < low)
is_valid, errors = validate_price_tick(
    symbol='AAPL',
    open_price=150,
    high=149,
    low=151,  # Invalid!
    close=150.5,
    volume=5_000_000,
)
assert is_valid == False
assert 'high < low' in errors[0]
```

### Integration Test: Full Loader

```python
def test_loadpricedaily_with_integrity():
    # Setup
    tracker = DataProvenanceTracker('loadpricedaily', 'price_daily', db_conn, in_memory=True)
    wm = WatermarkManager('loadpricedaily', 'price_daily', db_conn, granularity='symbol')
    
    # Start
    run_id = tracker.start_run(source_api='yfinance')
    
    # Load AAPL
    rows = [
        {'symbol': 'AAPL', 'date': date(2026, 5, 9), 'open': 150, 'high': 151, 'low': 149, 'close': 150.5, 'volume': 5000000},
    ]
    
    for row in rows:
        is_valid, errors = validate_price_tick(**row)
        assert is_valid
        tracker.record_tick(symbol=row['symbol'], tick_date=row['date'], data=row, source_api='yfinance')
    
    # End
    tracker.end_run(success=True)
    
    # Verify
    assert len(tracker.ticks_recorded) == 1
    assert tracker.ticks_recorded[0]['symbol'] == 'AAPL'
    print("✅ All ticks valid and tracked")
```

## Monitoring

### Dashboard Queries

```sql
-- Loaders that need attention (high error rate)
SELECT 
    loader_name,
    COUNT(*) as total_runs,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 1) as success_rate_pct
FROM data_loader_runs
WHERE start_at >= NOW() - INTERVAL '7 days'
GROUP BY loader_name
HAVING SUM(CASE WHEN success THEN 1 ELSE 0 END)::FLOAT / COUNT(*) < 0.95
ORDER BY success_rate_pct ASC;

-- Which APIs are failing?
SELECT error_type, COUNT(*) as count, MAX(recorded_at)
FROM data_provenance_errors
WHERE recorded_at >= NOW() - INTERVAL '24 hours'
GROUP BY error_type
ORDER BY count DESC;

-- Data freshness by symbol
SELECT 
    symbol,
    MAX(tick_date) as latest_data_date,
    CURRENT_DATE - MAX(tick_date) as days_stale
FROM data_provenance_log
GROUP BY symbol
HAVING MAX(tick_date) < CURRENT_DATE - INTERVAL '3 days'
ORDER BY days_stale DESC;
```

## Performance Implications

- **Validation overhead**: ~1-2ms per tick (negligible for 10k ticks)
- **Database inserts**: Same speed, now with validation + provenance
- **Storage overhead**: ~1KB per provenance record (for 1M ticks = 1GB/month)
- **Query performance**: Indexed properly, should be <100ms

## Next Steps

1. Update `loadpricedaily.py` to use these components (1-2 hours)
2. Update other loaders (1 hour each)
3. Add monitoring queries to dashboard (30 min)
4. Run 1 week of validation to catch issues (automatic)
5. Add replay capability to backtester (2-3 hours)

---

**Why do this first?** Because garbage data in = garbage trades out. Once you have clean, validated, auditable data, everything downstream becomes much more reliable.

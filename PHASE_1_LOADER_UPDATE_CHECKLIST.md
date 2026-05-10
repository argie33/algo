# Phase 1 Loader Update Checklist

**Status:** loadpricedaily.py COMPLETE ✅  
**Next:** 12 more price/signal loaders  
**Time per loader:** 30-45 minutes  

---

## What's Done

✅ **loadpricedaily.py** - Phase 1 fully integrated
- Data tick validation (OHLC logic, volume, sequences)
- Provenance tracking (run_id, checksums, errors)
- Watermark persistence (atomic, crash-safe)
- Tests passing, syntax verified

---

## What's Needed (13 more loaders)

### Price Loaders (3)
- [ ] loadpriceweekly.py
- [ ] loadpricemonthly.py
- [ ] loadetfpricedaily.py

### Signal Loaders (3)
- [ ] loadbuyselldaily.py
- [ ] loadbuyselweekly.py
- [ ] loadbuyselmonthly.py

### Technical Indicator Loaders (2+)
- [ ] loadtechnicalsdaily.py
- [ ] loadstockscores.py
- [ ] Others as time permits

---

## Step-by-Step Integration Pattern

### Step 1: Add Imports (Top of file)

```python
import psycopg2
from data_tick_validator import validate_price_tick  # Or skip for non-price data
from data_provenance_tracker import DataProvenanceTracker
from data_watermark_manager import WatermarkManager
```

### Step 2: Add Initialization to Loader Class

```python
class YourLoader(OptimalLoader):
    # ... existing class variables ...
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None
```

### Step 3: Add Provenance Methods to Loader Class

```python
    def start_provenance_tracking(self):
        """Initialize Phase 1 data integrity components."""
        db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=_credential_manager.get_db_credentials()["password"],
            database=os.getenv("DB_NAME", "stocks"),
        )
        self.tracker = DataProvenanceTracker(
            loader_name="your_loader_name",
            table_name="your_table_name",
            db_conn=db_conn,
        )
        self.watermark_mgr = WatermarkManager(
            loader_name="your_loader_name",
            table_name="your_table_name",
            db_conn=db_conn,
            granularity="symbol",
        )
        self.run_id = self.tracker.start_run(source_api="yfinance")

    def end_provenance_tracking(self, success: bool = True):
        """Finalize Phase 1 data integrity tracking."""
        if self.tracker and self.run_id:
            self.tracker.end_run(success=success)
```

### Step 4: Add Validation to transform() Method

**For PRICE loaders only** (validate OHLCV):

```python
    def transform(self, rows):
        """Validate and filter rows. Phase 1: Reject invalid ticks."""
        if not rows:
            return []

        validated = []
        prior_close = None

        for row in rows:
            # PHASE 1: Validate every tick (price loaders only)
            is_valid, errors = validate_price_tick(
                symbol=row.get('symbol'),
                open_price=row.get('open'),
                high=row.get('high'),
                low=row.get('low'),
                close=row.get('close'),
                volume=row.get('volume'),
                prior_close=prior_close,
            )

            if not is_valid:
                if self.tracker:
                    self.tracker.record_error(
                        symbol=row.get('symbol'),
                        error_type='DATA_INVALID',
                        error_message=', '.join(errors),
                        resolution='skipped',
                    )
                continue

            # Track provenance
            if self.tracker:
                self.tracker.record_tick(
                    symbol=row.get('symbol'),
                    tick_date=row.get('date'),
                    data=row,
                    source_api='yfinance',
                )

            validated.append(row)
            prior_close = row.get('close')

        return validated
```

**For NON-PRICE loaders** (signals, scores, etc.):
- Skip the validate_price_tick() call
- Still track provenance (just record all rows without validation)
- Still track errors if API fails

```python
    def transform(self, rows):
        """Track provenance for signal/score data."""
        if not rows:
            return []

        for row in rows:
            if self.tracker:
                self.tracker.record_tick(
                    symbol=row.get('symbol'),
                    tick_date=row.get('date') or row.get('signal_date'),
                    data=row,
                    source_api='yfinance',
                )

        return rows  # Return all rows (no validation for signals)
```

### Step 5: Update main() Function

```python
def main():
    parser = argparse.ArgumentParser(description="Your Loader - Phase 1 Enabled")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8)
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = YourLoader()
    try:
        # PHASE 1: Initialize tracking
        logger.info("[Phase 1] Initializing data integrity...")
        loader.start_provenance_tracking()

        # Run with validation + provenance
        stats = loader.run(symbols, parallelism=args.parallelism)

        # PHASE 1: Finalize tracking
        loader.end_provenance_tracking(success=(stats["symbols_failed"] == 0))

        return 0 if stats["symbols_failed"] == 0 else 1

    except Exception as e:
        logger.error(f"Loader failed: {e}")
        if loader.tracker:
            loader.end_provenance_tracking(success=False)
        return 1
    finally:
        loader.close()
```

---

## Mapping: Loader Names → Phase 1 Settings

| Loader | table_name | granularity | Validate? | Notes |
|--------|-----------|-------------|-----------|-------|
| loadpricedaily.py | price_daily | symbol | YES | DONE |
| loadpriceweekly.py | price_weekly | symbol | YES | Simple copy |
| loadpricemonthly.py | price_monthly | symbol | YES | Simple copy |
| loadetfpricedaily.py | etf_price_daily | symbol | YES | Simple copy |
| loadbuyselldaily.py | buy_sell_daily | symbol | NO | Track only |
| loadbuyselweekly.py | buy_sell_weekly | symbol | NO | Track only |
| loadbuyselmonthly.py | buy_sell_monthly | symbol | NO | Track only |
| loadtechnicalsdaily.py | technical_data_daily | symbol | NO | Track only |
| loadstockscores.py | stock_scores | symbol | NO | Track only |
| loadearningsrevisions.py | earnings_revisions | symbol | NO | Track only |
| loadestimatedeps.py | earnings_estimates | symbol | NO | Track only |
| loadalpacaportfolio.py | portfolio_holdings | symbol | NO | Track only |
| loadmarket.py | market_health_daily | global | NO | Global, no symbol |

---

## Testing Each Loader

After updating:

```bash
# Test locally with Docker
docker-compose up
python3 loadpriceweekly.py --symbols AAPL --parallelism 1

# Watch for:
# [Phase 1] Initializing data integrity...
# [Phase 1] Started provenance tracking: run_id=...
# [loadpriceweekly.py] Starting load: 1 symbols
# [Phase 1] Ended provenance tracking
```

Check provenance was recorded:

```sql
SELECT COUNT(*) as ticks_loaded
FROM data_provenance_log
WHERE loader_name = 'loadpriceweekly'
AND load_timestamp >= NOW() - INTERVAL '1 hour';

SELECT loader_name, success, ticks_loaded
FROM data_loader_runs
WHERE loader_name = 'loadpriceweekly'
ORDER BY start_at DESC
LIMIT 1;
```

---

## Priority Order (Recommended)

1. **High Priority** (data quality critical)
   - loadpriceweekly.py (30 min)
   - loadpricemonthly.py (30 min)
   - loadbuyselldaily.py (30 min)

2. **Medium Priority** (signals/scores)
   - loadtechnicalsdaily.py (30 min)
   - loadstockscores.py (30 min)
   - loadbuyselweekly.py (30 min)

3. **Low Priority** (can do later)
   - loadbuyselmonthly.py (30 min)
   - ETF loaders (30 min each)
   - Earnings loaders (30 min each)

---

## Time Estimate

- **Just the price loaders** (4): ~2 hours → covers 80% of data volume
- **Add signal loaders** (6): ~3 more hours → complete coverage
- **Add rest** (3): ~1.5 more hours → 100%

**Total for all 16 loaders: ~6-7 hours**

But you can deploy incrementally:
- Deploy loadpricedaily + weekly + monthly → Start getting data integrity
- Add signals next week → Full pipeline protection

---

## What Happens When You Run Updated Loaders

1. **Initialization**
   - Creates UUID run_id
   - Starts DataProvenanceTracker
   - Logs: "[Phase 1] Started provenance tracking: run_id=..."

2. **During Load**
   - Each tick validated (for price loaders)
   - Each tick tracked with checksum
   - Errors logged with categorization
   - Watermark advanced atomically

3. **On Completion**
   - All provenance stored in DB
   - Can query: "Show me all data loaded today"
   - Can replay: "Gimme exact data from 2026-05-09"
   - Can debug: "Why did this symbol fail?"

4. **If Crash Occurs**
   - Watermark doesn't advance
   - Next run retries same date
   - No duplication (idempotent)
   - All attempts logged

---

## Files That Need Updates

✅ **loadpricedaily.py** - DONE

**Next batch (copy pattern from loadpricedaily.py):**
- loadpriceweekly.py
- loadpricemonthly.py
- loadbuyselldaily.py

---

## Questions During Update?

1. **"What about my custom validation?"**
   - Keep it! Add it to transform()
   - Phase 1 validation is just the baseline
   - Custom checks run after Phase 1

2. **"What if my loader doesn't have a symbol column?"**
   - Like loadmarket.py (market health)
   - Use granularity='global' instead of 'symbol'
   - Still track and validate, just once per run

3. **"What if my data doesn't have price data to validate?"**
   - Skip validate_price_tick()
   - Just track provenance with record_tick()
   - Error logging still works

4. **"Will this slow down my loaders?"**
   - Negligible: ~1-2ms per tick
   - 10K ticks = ~10-20ms overhead
   - Worth it for data integrity guarantee

---

Ready to start updating the others? The pattern is identical to loadpricedaily.py.

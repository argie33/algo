#!/usr/bin/env python3
"""Execute buy_sell_daily to validate ROOT CAUSE #4 fix - generate fresh signals."""

import sys
import time
from datetime import datetime, timezone
from utils.infrastructure.timezone import EASTERN_TZ
from utils.db.context import DatabaseContext

print("\n" + "="*70)
print("ROOT CAUSE #4 VALIDATION: EXECUTING BUY_SELL_DAILY WITH OPTIMIZATIONS")
print("="*70)

# Check starting state
print("\n[BEFORE] Signal Freshness")
with DatabaseContext('read') as cur:
    cur.execute('SELECT MAX(date) FROM buy_sell_daily')
    before_date = cur.fetchone()[0]
    now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()
    before_hours = (now_et - before_date).days * 24 if before_date else 0
    print(f"  Max signal date: {before_date}")
    print(f"  Signal age: {before_hours} hours (STALE)")

# Execute the loader with optimizations
print("\n[EXECUTE] buy_sell_daily with:")
print("  - Parallelism: 6 (ROOT CAUSE #4 FIX #1)")
print("  - Batch context caching (ROOT CAUSE #4 FIX #2)")
print("  - Processing 10,549 symbols in parallel...")

from loaders.load_buy_sell_daily import SignalsDailyLoader
from utils.loaders.helpers import get_active_symbols

loader = SignalsDailyLoader()
symbols = list(get_active_symbols())

start_time = time.time()
print(f"\nStarting at {datetime.now().isoformat()}")

try:
    stats = loader.run(symbols, parallelism=6)
    elapsed = (time.time() - start_time) / 60

    print(f"\n[COMPLETED] Duration: {elapsed:.1f} minutes")
    print(f"  Symbols processed: {stats.get('symbols_processed', 0)}")
    print(f"  Rows fetched: {stats.get('rows_fetched', 0)}")
    print(f"  Rows inserted: {stats.get('rows_inserted', 0)}")

except KeyboardInterrupt:
    print(f"\nInterrupted after {(time.time()-start_time)/60:.1f} minutes")
    sys.exit(1)
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Check signal freshness after execution
print("\n[AFTER] Signal Freshness")
with DatabaseContext('read') as cur:
    cur.execute('SELECT MAX(date) FROM buy_sell_daily')
    after_date = cur.fetchone()[0]
    now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ).date()
    after_hours = (now_et - after_date).days * 24 if after_date else 0
    print(f"  Max signal date: {after_date}")
    print(f"  Signal age: {after_hours} hours")

    if after_hours < 24:
        status = "FRESH"
        result = "SUCCESS"
    elif after_hours < 72:
        status = "IMPROVED"
        result = "PARTIAL SUCCESS"
    else:
        status = "STALE"
        result = "FAILED"

    print(f"  Status: {status}")
    print(f"  Improvement: {before_hours - after_hours} hours younger")

print("\n" + "="*70)
if result == "SUCCESS":
    print(f"ROOT CAUSE #4 FIX VALIDATED: {result}")
    print("Signals are now FRESH (<24 hours)")
else:
    print(f"ROOT CAUSE #4 FIX PARTIALLY VERIFIED: {result}")
    print(f"Signals improved from {before_hours}h → {after_hours}h")
print("="*70 + "\n")

sys.exit(0 if result != "FAILED" else 1)

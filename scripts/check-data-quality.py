#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext

print("="*80)
print("DATA QUALITY CHECK")
print("="*80)
print()

try:
    with DatabaseContext('read') as cur:
        print("[OK] Database connected")
        print()

        # Price coverage
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily")
        symbols = cur.fetchone()[0]
        cur.execute("SELECT MAX(date) FROM price_daily")
        latest_date = cur.fetchone()[0]
        print("Price Data: {} symbols, latest: {}".format(symbols, latest_date))

        # Today's prices
        today = date.today()
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s", (today,))
        today_count = cur.fetchone()[0]
        print("Today's prices ({}): {} symbols".format(today, today_count))
        print()

        # Scores
        cur.execute("SELECT COUNT(*), MAX(date) FROM swing_trader_scores")
        count, date_val = cur.fetchone()
        print("Swing Trader Scores: {}, latest: {}".format(count, date_val))

        cur.execute("SELECT COUNT(*), MAX(date) FROM signal_quality_scores")
        count, date_val = cur.fetchone()
        print("Signal Quality Scores: {}, latest: {}".format(count, date_val))
        print()

        # Data loss detection
        print("Row Counts (data loss check):")
        for table in ['price_daily', 'swing_trader_scores', 'signal_quality_scores']:
            cur.execute("SELECT COUNT(*) FROM {}".format(table))
            count = cur.fetchone()[0]
            status = "[OK]" if count > 100 else "[WARN]"
            print("  {} {}: {:,}".format(status, table, count))

        print()
        print("[SUCCESS] Database OK")

except Exception as e:
    print("[ERROR] Database Error: {}".format(e))
    import traceback
    traceback.print_exc()
    sys.exit(1)

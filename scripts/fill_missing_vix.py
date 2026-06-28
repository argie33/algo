#!/usr/bin/env python3
"""Fill missing VIX data using the last available value (weekend carry-forward)."""

from datetime import date

from utils.db.context import DatabaseContext

try:
    with DatabaseContext('write') as cur:
        # Get the latest VIX value
        cur.execute(
            'SELECT date, close, high, low FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1',
            ('^VIX',)
        )
        row = cur.fetchone()
        if not row:
            print("ERROR: No VIX data found in database")
            exit(1)

        last_date, last_close, last_high, last_low = row
        print(f"Using last VIX data from {last_date}: close={last_close}, high={last_high}, low={last_low}")

        # Insert for missing dates (2026-06-25, 2026-06-26)
        missing_dates = [date(2026, 6, 25), date(2026, 6, 26)]
        for d in missing_dates:
            # Check if already exists
            cur.execute(
                'SELECT COUNT(*) FROM price_daily WHERE symbol = %s AND date = %s',
                ('^VIX', d)
            )
            exists = cur.fetchone()[0] > 0

            if exists:
                print(f"  {d}: Already exists, skipping")
            else:
                cur.execute(
                    'INSERT INTO price_daily (symbol, date, close, high, low, volume) VALUES (%s, %s, %s, %s, %s, 0)',
                    ('^VIX', d, last_close, last_high, last_low)
                )
                print(f"  {d}: Inserted (carry-forward from {last_date})")

    print("\nMissing VIX data filled successfully!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

#!/usr/bin/env python3
"""Debug pivot detection to understand June 2 signal."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import date
from utils.database_context import DatabaseContext

def debug_pivot_detection():
    """Debug the pivot detection for ON near June 2-3."""
    with DatabaseContext('read') as cur:
        start = date(2026, 5, 15)
        end = date(2026, 6, 3)

        cur.execute(
            """SELECT t.date, p.high
               FROM technical_data_daily t
               LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
               WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
               ORDER BY t.date ASC""",
            ('ON', start, end),
        )
        rows = []
        for r in cur.fetchall():
            if r[0] is None or r[1] is None:
                continue
            rows.append({
                "date": r[0].isoformat() if r[0] else None,
                "high": float(r[1]) if r[1] is not None else None,
            })

    print(f"Total rows: {len(rows)}")
    for i, row in enumerate(rows):
        print(f"[{i}] {row['date']}: {row['high']:.2f}")

    # Now manually check if June 2 (should be index ~13 or so from start) is a swing high
    print("\n=== Checking pivot conditions ===")
    for i, row in enumerate(rows):
        if row['date'] == '2026-06-02':
            print(f"\nAnalyzing index {i} ({row['date']}): high={row['high']:.2f}")

            # Check 3-bar lookback
            print(f"  Lookback check (range {max(0, i-3)} to {i-1}):")
            lookback_ok = True
            for k in range(max(0, i-3), i):
                is_ok = rows[k]['high'] < row['high']
                print(f"    [{k}] {rows[k]['date']}: {rows[k]['high']:.2f} < {row['high']:.2f}? {is_ok}")
                lookback_ok = lookback_ok and is_ok
            print(f"  Lookback result: {lookback_ok}")

            # Check 3-bar lookahead
            print(f"  Lookahead check (range {i+1} to {min(len(rows), i+4)}):")
            lookforward_ok = True
            for k in range(i+1, min(len(rows), i+4)):
                is_ok = rows[k]['high'] < row['high']
                print(f"    [{k}] {rows[k]['date']}: {rows[k]['high']:.2f} < {row['high']:.2f}? {is_ok}")
                lookforward_ok = lookforward_ok and is_ok
            print(f"  Lookahead result: {lookforward_ok}")

            print(f"\n  Is {row['date']} a pivot? {lookback_ok and lookforward_ok}")

if __name__ == "__main__":
    debug_pivot_detection()

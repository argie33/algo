#!/usr/bin/env python3
"""Debug ON stock signal generation to verify pivot detection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import date, timedelta
from utils.database_context import DatabaseContext
from loaders.load_buy_sell_daily import SignalsDailyLoader

def debug_on_signals():
    """Debug ON stock signals, especially June 2 BUY."""
    loader = SignalsDailyLoader()

    # Fetch data for ON from April to June
    with DatabaseContext('read') as cur:
        start = date(2026, 4, 1)
        end = date(2026, 6, 3)

        cur.execute(
            """SELECT t.date, t.sma_50, t.sma_200,
                      p.close, p.volume, p.open, p.high, p.low
               FROM technical_data_daily t
               LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
               WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
               ORDER BY t.date ASC""",
            ('ON', start, end),
        )
        rows = []
        for r in cur.fetchall():
            if r[0] is None or r[3] is None:
                continue
            rows.append({
                "date": r[0].isoformat() if r[0] else None,
                "sma_50": float(r[1]) if r[1] is not None else None,
                "sma_200": float(r[2]) if r[2] is not None else None,
                "close": float(r[3]) if r[3] is not None else None,
                "volume": int(r[4]) if r[4] is not None else None,
                "open": float(r[5]) if r[5] is not None else None,
                "high": float(r[6]) if r[6] is not None else None,
                "low": float(r[7]) if r[7] is not None else None,
            })

    if not rows:
        print("No data found for ON stock")
        return

    print(f"Found {len(rows)} days of data for ON from {rows[0]['date']} to {rows[-1]['date']}")
    print("\n=== Key Date Analysis ===")

    # Find April 6 and June 2
    april_6 = None
    june_2 = None
    for i, row in enumerate(rows):
        if row['date'] == '2026-04-06':
            april_6 = (i, row)
        elif row['date'] == '2026-06-02':
            june_2 = (i, row)

    if april_6:
        idx, row = april_6
        print(f"\nApril 6 (index {idx}): High={row['high']:.2f}, Low={row['low']:.2f}, Close={row['close']:.2f}, SMA50={row['sma_50']:.2f}")
        # Show surrounding data
        print("  Surrounding highs (lookback):")
        for j in range(max(0, idx-3), idx):
            print(f"    [{j}] {rows[j]['date']}: {rows[j]['high']:.2f}")
        print("  Surrounding highs (lookahead):")
        for j in range(idx+1, min(len(rows), idx+4)):
            print(f"    [{j}] {rows[j]['date']}: {rows[j]['high']:.2f}")

    if june_2:
        idx, row = june_2
        print(f"\nJune 2 (index {idx}): High={row['high']:.2f}, Low={row['low']:.2f}, Close={row['close']:.2f}, SMA50={row['sma_50']:.2f}")
        # Show surrounding data
        print("  Surrounding highs (lookback):")
        for j in range(max(0, idx-3), idx):
            print(f"    [{j}] {rows[j]['date']}: {rows[j]['high']:.2f}")
        print("  Surrounding highs (lookahead):")
        for j in range(idx+1, min(len(rows), idx+4)):
            print(f"    [{j}] {rows[j]['date']}: {rows[j]['high']:.2f}")

    # Now check what signals are generated
    print("\n=== Generated Signals ===")
    signals = loader._generate_signals('ON', rows)
    for sig in signals:
        print(f"{sig['date']}: {sig['signal']} @ {sig['buylevel']:.2f} (strength={sig['strength']:.2f})")
        print(f"  Reason: {sig['reason']}")

if __name__ == "__main__":
    debug_on_signals()

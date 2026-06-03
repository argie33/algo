#!/usr/bin/env python3
"""Debug script to verify pivot detection for ON symbol."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import date, timedelta
from utils.database_context import DatabaseContext
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_on_data():
    """Fetch technical and price data for ON around June 2, 2026."""
    try:
        with DatabaseContext('read') as cur:
            # Fetch data from May 15 to June 10
            cur.execute(
                """SELECT t.date, p.high, p.low, p.close, t.sma_50, t.sma_200
                   FROM technical_data_daily t
                   LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                   WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
                   ORDER BY t.date ASC""",
                ("ON", date(2026, 5, 15), date(2026, 6, 10)),
            )
            rows = []
            for r in cur.fetchall():
                if r[0] is None:
                    continue
                rows.append({
                    "date": r[0].isoformat() if r[0] else None,
                    "high": float(r[1]) if r[1] is not None else None,
                    "low": float(r[2]) if r[2] is not None else None,
                    "close": float(r[3]) if r[3] is not None else None,
                    "sma_50": float(r[4]) if r[4] is not None else None,
                    "sma_200": float(r[5]) if r[5] is not None else None,
                })
            return rows
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return []

def find_swings(rows):
    """Find all swing highs and lows with 3-bar pivot logic."""
    swings = []
    for i, row in enumerate(rows):
        high = row.get("high")
        low = row.get("low")

        # Check for swing high
        lookback_ok = all(
            rows[k].get("high", 0) is not None and
            (rows[k].get("high", 0) <= high or k >= i)
            for k in range(max(0, i-3), i)
        )
        lookforward_ok = all(
            rows[k].get("high", 0) is not None and
            rows[k].get("high", 0) <= high
            for k in range(i+1, min(len(rows), i+4))
        )
        if lookback_ok and lookforward_ok:
            swings.append((row["date"], "SWING_HIGH", high, row.get("sma_50")))

        # Check for swing low
        lookback_ok = all(
            rows[k].get("low", 999999) is not None and
            (rows[k].get("low", 999999) >= low or k >= i)
            for k in range(max(0, i-3), i)
        )
        lookforward_ok = all(
            rows[k].get("low", 999999) is not None and
            rows[k].get("low", 999999) >= low
            for k in range(i+1, min(len(rows), i+4))
        )
        if lookback_ok and lookforward_ok:
            swings.append((row["date"], "SWING_LOW", low, None))

    return swings

def check_june2_signal(rows):
    """Check if June 2 should have a BUY signal."""
    june2_idx = None
    for i, row in enumerate(rows):
        if row["date"] == "2026-06-02":
            june2_idx = i
            break

    if june2_idx is None:
        print("June 2 not found in data")
        return

    row = rows[june2_idx]
    print(f"\n=== June 2 Bar Data ===")
    print(f"Date: {row['date']}")
    print(f"High: {row['high']}")
    print(f"Low: {row['low']}")
    print(f"Close: {row['close']}")
    print(f"SMA50: {row['sma_50']}")
    print(f"SMA200: {row['sma_200']}")

    # Find most recent swing high before June 2
    recent_swing_high = None
    swing_high_sma50 = None
    swing_high_date = None

    for j in range(max(0, june2_idx-6), june2_idx):
        high = rows[j].get("high")

        lookback_ok = all(
            rows[k].get("high", 0) is not None and
            (rows[k].get("high", 0) <= high or k >= j)
            for k in range(max(0, j-3), j)
        )
        lookforward_ok = all(
            rows[k].get("high", 0) is not None and
            rows[k].get("high", 0) <= high
            for k in range(j+1, min(len(rows), j+4))
        )

        if lookback_ok and lookforward_ok:
            if recent_swing_high is None or high > recent_swing_high:
                recent_swing_high = high
                swing_high_sma50 = rows[j].get("sma_50")
                swing_high_date = rows[j]["date"]

    print(f"\n=== Recent Swing High (lookback 6 bars) ===")
    print(f"Swing High Date: {swing_high_date}")
    print(f"Swing High Price: {recent_swing_high}")
    print(f"SMA50 at swing: {swing_high_sma50}")

    if recent_swing_high:
        print(f"\n=== BUY Signal Checks ===")
        print(f"1. High ({row['high']}) > Swing High ({recent_swing_high}): {row['high'] > recent_swing_high}")
        print(f"2. Swing High ({recent_swing_high}) > SMA50 ({swing_high_sma50}): {recent_swing_high > swing_high_sma50}")

        if row['high'] > recent_swing_high and recent_swing_high > swing_high_sma50:
            breakout_pct = ((row['high'] - recent_swing_high) / recent_swing_high * 100)
            print(f"\n[YES] BUY SIGNAL TRIGGERED")
            print(f"Breakout: {breakout_pct:.2f}%")
        else:
            print(f"\n[NO] BUY SIGNAL")

    # Show last 10 bars for context
    print(f"\n=== Last 10 Bars Context ===")
    for i in range(max(0, june2_idx-9), june2_idx+1):
        r = rows[i]
        marker = " <- June 2" if i == june2_idx else ""
        print(f"{r['date']} | H: {r['high']:.2f} L: {r['low']:.2f} C: {r['close']:.2f} SMA50: {r['sma_50']:.2f}{marker}")

def main():
    print("Fetching ON data...")
    rows = fetch_on_data()

    if not rows:
        print("No data found")
        return

    print(f"Fetched {len(rows)} rows")

    print("\n=== All Swings Detected ===")
    swings = find_swings(rows)
    for date, swing_type, price, sma in swings:
        sma_str = f" (SMA50: {sma:.2f})" if sma else ""
        print(f"{date} | {swing_type}: {price:.2f}{sma_str}")

    check_june2_signal(rows)

if __name__ == "__main__":
    main()

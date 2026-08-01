#!/usr/bin/env python3
"""Diagnose position status bug"""
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

print("=" * 70)
print("POSITION STATUS INCONSISTENCIES")
print("=" * 70)

# Find positions that are marked as open but have closed_at set
try:
    cur.execute('''
    SELECT symbol, quantity, status, closed_at, is_open
    FROM algo_positions
    WHERE status = 'open' AND closed_at IS NOT NULL
    ORDER BY closed_at DESC
    LIMIT 20
    ''')

    broken_positions = cur.fetchall()
    print(f"\nPositions marked OPEN but have closed_at: {len(broken_positions)}")
    if broken_positions:
        print(f"  {'Symbol':<8} {'Qty':>6} {'Status':>8} {'Closed':>30} {'IsOpen':>8}")
        print("  " + "-" * 70)
        for symbol, qty, status, closed_at, is_open in broken_positions:
            print(f"  {symbol:<8} {qty:>6.0f} {status:>8} {closed_at:>30} {is_open}")

except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 70)
print("TOTAL POSITION COUNT BY STATUS")
print("=" * 70)

try:
    cur.execute('''
    SELECT status, COUNT(*) as cnt, SUM(quantity) as total_qty
    FROM algo_positions
    GROUP BY status
    ORDER BY cnt DESC
    ''')

    for status, cnt, total_qty in cur.fetchall():
        print(f"  {status:15} : {cnt:4} positions ({total_qty:8.0f} shares total)")

except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 70)
print("WHEN WERE POSITIONS LAST CLOSED/UPDATED")
print("=" * 70)

try:
    cur.execute('''
    SELECT status, COUNT(*) as cnt,
           MAX(closed_at) as max_closed,
           MAX(updated_at) as max_updated,
           MAX(CASE WHEN closed_at > updated_at THEN closed_at ELSE updated_at END) as max_any
    FROM algo_positions
    GROUP BY status
    ORDER BY max_any DESC NULLS LAST
    ''')

    for status, cnt, max_closed, max_updated, max_any in cur.fetchall():
        print(f"  {status:15}: {cnt:4} positions, last change at {max_any}")

except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 70)
print("CURRENTLY HELD POSITIONS (quantity != 0)")
print("=" * 70)

try:
    cur.execute('''
    SELECT COUNT(*) as cnt, SUM(quantity * current_price) as portfolio_value
    FROM algo_positions
    WHERE quantity != 0
    ''')

    cnt, portfolio_val = cur.fetchone()
    print(f"  Active holdings: {cnt} positions")
    print(f"  Portfolio value: ${portfolio_val:,.2f}" if portfolio_val else "  Portfolio value: $0.00")

    # Check if any of these are marked as not open
    cur.execute('''
    SELECT COUNT(*) as cnt
    FROM algo_positions
    WHERE quantity != 0 AND status != 'open'
    ''')

    not_open_count = cur.fetchone()[0]
    if not_open_count > 0:
        print(f"\n  WARNING: {not_open_count} positions with quantity != 0 but status != 'open'")

        cur.execute('''
        SELECT symbol, quantity, status, closed_at
        FROM algo_positions
        WHERE quantity != 0 AND status != 'open'
        ORDER BY symbol
        ''')

        print("\n  These positions:")
        for symbol, qty, status, closed_at in cur.fetchall():
            print(f"    {symbol:8} qty={qty:6.0f} status={status:10} closed_at={closed_at}")

except Exception as e:
    print(f"  Error: {e}")

cur.close()
conn.close()

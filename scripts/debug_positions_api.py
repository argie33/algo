#!/usr/bin/env python3
"""Debug why API returns 0 positions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2.extras

from utils.data_queries import get_open_positions
from utils.db.context import DatabaseContext

print("\n" + "="*80)
print("DEBUG: Tracing position filtering")
print("="*80)

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Step 1: Check raw data
    print("\n[1] Raw algo_positions table:")
    cur.execute("SELECT COUNT(*) as count, status FROM algo_positions GROUP BY status")
    for row in cur.fetchall():
        print(f"    {row['status']}: {row['count']}")

    # Step 2: Check view data
    print("\n[2] algo_positions_with_risk view:")
    cur.execute("SELECT COUNT(*) as count, status FROM algo_positions_with_risk GROUP BY status")
    for row in cur.fetchall():
        print(f"    {row['status']}: {row['count']}")

    # Step 3: Check get_open_positions function
    print("\n[3] get_open_positions() result:")
    positions = get_open_positions(cur, limit=1000)
    print(f"    Returned: {len(positions)} positions")

    if positions:
        print("\n    Sample positions from get_open_positions():")
        for pos in positions[:3]:
            if isinstance(pos, dict):
                print(f"      {pos.get('symbol')}: symbol={pos.get('symbol')}, status={pos.get('status')}, "
                      f"value={pos.get('position_value')}")
            else:
                print(f"      {pos}")
    else:
        print("\n    !!! No positions returned by get_open_positions() !!!")

        # Manually check the view query
        print("\n    Checking view directly:")
        cur.execute("""
            SELECT symbol, status, position_value
            FROM algo_positions_with_risk
            WHERE status = 'open'
            LIMIT 3
        """)
        view_rows = cur.fetchall()
        print(f"    Direct view query returned: {len(view_rows)} rows")
        for row in view_rows:
            print(f"      {row['symbol']}: {row}")

    # Step 4: Check for data type issues
    print("\n[4] Checking data types returned by view:")
    cur.execute("""
        SELECT symbol, quantity, position_value, status
        FROM algo_positions_with_risk
        WHERE status = 'open'
        LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        print(f"    Row type: {type(row)}")
        print(f"    Row: {row}")
        for key, value in row.items():
            print(f"      {key}: {value} (type: {type(value).__name__})")

print("\n" + "="*80)

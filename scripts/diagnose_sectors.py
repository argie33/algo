#!/usr/bin/env python3
"""Diagnose why positions have Unknown sectors."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2.extras

from utils.db.context import DatabaseContext

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("\n=== SECTOR DATA INVESTIGATION ===\n")

    # Get all open positions and check sector sources
    cur.execute("""
        SELECT symbol FROM algo_positions WHERE status = 'open'
        ORDER BY position_value DESC
        LIMIT 5
    """)
    symbols = [row['symbol'] for row in cur.fetchall()]

    for symbol in symbols:
        print(f"\n{symbol}:")

        # Check algo_trades
        cur.execute("""
            SELECT DISTINCT sector FROM algo_trades
            WHERE symbol = %s AND sector IS NOT NULL
            LIMIT 1
        """, (symbol,))
        trade_sector = cur.fetchone()
        print(f"  From algo_trades: {trade_sector['sector'] if trade_sector else 'NULL'}")

        # Check company_profile
        cur.execute("""
            SELECT sector FROM company_profile WHERE ticker = %s
        """, (symbol,))
        cp_sector = cur.fetchone()
        print(f"  From company_profile: {cp_sector['sector'] if cp_sector else 'NOT FOUND'}")

        # Check what the view returns
        cur.execute("""
            SELECT sector FROM algo_positions_with_risk WHERE symbol = %s
        """, (symbol,))
        view_sector = cur.fetchone()
        print(f"  From view: {view_sector['sector'] if view_sector else 'NULL'}")

    # Check if positions have status='open' only
    print("\n\nOpen vs closed positions:")
    cur.execute("""
        SELECT status, COUNT(*) as count FROM algo_positions GROUP BY status
    """)
    for row in cur.fetchall():
        print(f"  {row['status']}: {row['count']}")

    # Check if get_open_positions() filters work
    print("\n\nTesting get_open_positions():")
    cur.execute("""
        SELECT COUNT(*) as count FROM algo_positions_with_risk
        WHERE status = 'open'
    """)
    open_count = cur.fetchone()['count']
    print(f"  Positions with status='open': {open_count}")

    cur.execute("""
        SELECT COUNT(*) as count FROM algo_positions_with_risk
    """)
    total_count = cur.fetchone()['count']
    print(f"  Total positions from view: {total_count}")
    print(f"  Includes closed: {total_count - open_count}")

    # Key issue: Dashboard filtering
    print("\n\nDashboard API filtering:")
    cur.execute("""
        SELECT * FROM algo_positions_with_risk
        WHERE status = 'open'
        LIMIT 3
    """)
    for row in cur.fetchall():
        print(f"  {row['symbol']:6} status={row['status']} sector={row['sector']}")

#!/usr/bin/env python3
"""Check actual view definition in database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2.extras

from utils.db.context import DatabaseContext

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get the actual view definition
    cur.execute("""
        SELECT definition FROM pg_matviews
        WHERE matviewname = 'algo_positions_with_risk'
    """)
    result = cur.fetchone()

    if result:
        print("ACTUAL VIEW DEFINITION IN DATABASE:")
        print("=" * 80)
        print(result['definition'])
    else:
        print("View not found as materialized view. Checking regular view...")
        cur.execute("""
            SELECT definition FROM information_schema.views
            WHERE table_name = 'algo_positions_with_risk'
        """)
        result = cur.fetchone()
        if result:
            print("VIEW DEFINITION:")
            print("=" * 80)
            print(result['definition'])

#!/usr/bin/env python3
"""Quick check of database loader status."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
from utils.database_context import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        print("✓ Database connected\n")

        # Check recent loader status
        cur.execute("""
            SELECT table_name, latest_date, row_count
            FROM data_loader_status
            ORDER BY latest_date DESC LIMIT 15
        """)
        rows = cur.fetchall()
        print(f"Recent loader status ({len(rows)} tables):")
        for r in rows:
            age_days = (datetime.now().date() - r[1]).days if r[1] else None
            age_str = f"{age_days}d old" if age_days is not None else "NULL"
            print(f"  {r[0]:30s} latest={r[1]} ({age_str:7s}) rows={r[2]:>8}")

        # Check data_patrol_log for recent issues
        two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        cur.execute("""
            SELECT patrol_run_id, MAX(created_at), severity, COUNT(*) as count
            FROM data_patrol_log
            WHERE created_at > %s
            GROUP BY patrol_run_id, severity
            ORDER BY MAX(created_at) DESC
            LIMIT 30
        """, (two_days_ago,))

        patrol_rows = cur.fetchall()
        if patrol_rows:
            print(f"\nRecent patrol findings (last 2 days):")
            for r in patrol_rows:
                print(f"  {r[0]:30s} {r[2]:10s} count={r[3]:3} at {r[1]}")
        else:
            print("\nNo recent patrol findings")

except Exception as e:
    print(f"✗ Database error: {e}")
    import traceback
    traceback.print_exc()

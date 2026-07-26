#!/usr/bin/env python3
"""Debug data-status endpoint."""

from utils.db import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        # Check if algo_orchestrator_runs is in data_loader_status
        cur.execute("""
            SELECT table_name, row_count, last_updated
            FROM data_loader_status
            WHERE table_name = 'algo_orchestrator_runs'
        """)
        result = cur.fetchone()
        if result:
            print(f"Found in data_loader_status: {result}")
            print(f"  table_name: {result[0]}")
            print(f"  row_count: {result[1]}")
            print(f"  last_updated: {result[2]}")
        else:
            print("algo_orchestrator_runs NOT in data_loader_status")

        # Check available tables
        cur.execute("SELECT table_name FROM data_loader_status LIMIT 10")
        tables = cur.fetchall()
        print(f"\nFirst 10 tables in data_loader_status:")
        for t in tables:
            print(f"  - {t[0]}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

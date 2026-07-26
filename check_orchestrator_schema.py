#!/usr/bin/env python3
"""Check algo_orchestrator_runs schema."""

from utils.db import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'algo_orchestrator_runs'
            ORDER BY ordinal_position
        """)
        cols = cur.fetchall()
        print('Columns in algo_orchestrator_runs:')
        for c in cols:
            print(f'  - {c[0]}')

        # Also test the queries that were failing
        print('\nTesting query from data-status endpoint:')
        try:
            cur.execute("""
                SELECT overall_status, halt_reason
                FROM algo_orchestrator_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)
            result = cur.fetchone()
            print(f'✓ Query works. Result: {result}')
        except Exception as e:
            print(f'✗ Query failed: {e}')

except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()

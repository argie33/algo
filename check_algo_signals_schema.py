#!/usr/bin/env python3
"""Check algo_signals schema."""

from utils.db import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'algo_signals'
            ORDER BY ordinal_position
        """)
        cols = cur.fetchall()
        print('Columns in algo_signals:')
        for c in cols:
            print(f'  - {c[0]}')

        # Test the query that uses created_at
        print('\nTesting query that uses created_at:')
        try:
            cur.execute("""
                SELECT COUNT(*) as signal_count,
                       AVG(CAST(signal_quality_score AS FLOAT)) as avg_strength,
                       MAX(created_at) as latest_signal,
                       ARRAY_AGG(DISTINCT symbol) FILTER (WHERE symbol IS NOT NULL) as symbols_with_signals
                FROM algo_signals
                WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
            """)
            result = cur.fetchone()
            print(f'✓ Query works. Result columns: {result}')
        except Exception as e:
            print(f'✗ Query failed: {type(e).__name__}: {e}')

except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()

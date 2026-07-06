#!/usr/bin/env python3
"""Check database schema for the tables used by failing endpoints."""

import sys
sys.path.insert(0, '.')

try:
    from utils.db import DatabaseContext

    db = DatabaseContext('read')
    cur = db.execute_query("SELECT 1")  # Test connection

    tables_to_check = [
        'algo_audit_log',
        'orchestrator_execution_log',
        'circuit_breaker_status',
    ]

    for table in tables_to_check:
        print(f'\n{"="*60}')
        print(f'Checking table: {table}')
        print("="*60)

        # Check if table exists
        try:
            cur = db.execute_query(
                f"""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name='{table}'
                );
                """
            )
            result = cur.fetchone()
            exists = result[0] if result else False
            print(f'Table exists: {exists}')

            if not exists:
                print(f'  ERROR: Table {table} does not exist!')
                continue

            # Get column info
            cur = db.execute_query(
                f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name='{table}'
                ORDER BY ordinal_position;
                """
            )
            cols = cur.fetchall()
            print(f'Columns ({len(cols)}):')
            for col in cols:
                col_name, data_type, nullable = col
                null_str = "NULL" if nullable == 'YES' else "NOT NULL"
                print(f'  - {col_name}: {data_type} {null_str}')

            # Check row count
            cur = db.execute_query(f"SELECT COUNT(*) FROM {table};")
            count = cur.fetchone()[0]
            print(f'Row count: {count}')

            # Get recent data
            if count > 0:
                cur = db.execute_query(f"SELECT * FROM {table} LIMIT 2;")
                print(f'Sample rows:')
                for row in cur.fetchall():
                    print(f'  {dict(row)}')

        except Exception as e:
            print(f'  ERROR: {type(e).__name__}: {e}')

    db.close()

except ImportError as e:
    print(f'Cannot import DatabaseContext: {e}')
    print('Make sure database is configured')
except Exception as e:
    print(f'Error: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

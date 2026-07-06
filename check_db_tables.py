#!/usr/bin/env python3
"""Check if key database tables exist."""

import psycopg2
import os

try:
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=os.environ.get('DB_PORT', '5432'),
        user=os.environ.get('DB_USER', 'algo'),
        password=os.environ.get('DB_PASSWORD', 'algo'),
        database=os.environ.get('DB_NAME', 'algo'),
        connect_timeout=5
    )
    print('[OK] Database connection successful')
    cur = conn.cursor()

    # Check for key tables
    tables = [
        'algo_audit_log',
        'orchestrator_execution_log',
        'circuit_breaker_status',
    ]

    print('\nTable Status:')
    for t in tables:
        try:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                (t,)
            )
            exists = cur.fetchone()[0]
            status = '[EXISTS]' if exists else '[MISSING]'
            print(f'  {t}: {status}')

            if exists:
                # Get row count
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                count = cur.fetchone()[0]
                print(f'    Row count: {count}')
        except Exception as e:
            print(f'  {t}: ERROR - {e}')

    conn.close()
    print('\n[OK] Database check complete')

except psycopg2.OperationalError as e:
    print(f'[FAIL] Database connection failed: {e}')
except Exception as e:
    print(f'[FAIL] Error: {e}')

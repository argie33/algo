#!/usr/bin/env python3
"""Describe table schemas"""
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

tables = ['algo_orchestrator_runs', 'algo_positions', 'algo_runtime_state', 'algo_orchestrator_state']

for table in tables:
    try:
        print(f"\n{'='*70}")
        print(f"TABLE: {table}")
        print('='*70)
        cur.execute(f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
        """, (table,))

        cols = cur.fetchall()
        if not cols:
            print(f"  Table not found")
            continue

        for col_name, col_type, nullable in cols:
            null_str = "NULL" if nullable == 'YES' else "NOT NULL"
            print(f"  {col_name:30} {col_type:20} {null_str}")

    except Exception as e:
        print(f"  Error: {e}")

cur.close()
conn.close()

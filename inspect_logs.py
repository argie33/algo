#!/usr/bin/env python3
"""Inspect log table structure"""
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

print("=" * 70)
print("ORCHESTRATOR_EXECUTION_LOG TABLE SCHEMA")
print("=" * 70)

try:
    cur.execute(f"""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'orchestrator_execution_log'
    ORDER BY ordinal_position
    """)

    cols = cur.fetchall()
    if not cols:
        print("  Table not found")
    else:
        for col_name, col_type in cols:
            print(f"  {col_name:30} {col_type:20}")

    # Try sample query
    print("\n" + "=" * 70)
    print("SAMPLE EXECUTION LOG DATA")
    print("=" * 70)

    cur.execute('''
    SELECT * FROM orchestrator_execution_log
    ORDER BY created_at DESC
    LIMIT 5
    ''')

    # Get column names from cursor description
    col_names = [desc[0] for desc in cur.description]
    for row in cur.fetchall():
        print("\n  Record:")
        for name, value in zip(col_names, row):
            val_str = str(value)[:80] if value else "(null)"
            print(f"    {name:30} = {val_str}")

except Exception as e:
    print(f"  Error: {e}")
    import traceback
    traceback.print_exc()

cur.close()
conn.close()

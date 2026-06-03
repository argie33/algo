#!/usr/bin/env python3
"""Verify algo_metrics_daily table structure and test UPSERT."""
import psycopg2
import os
from datetime import date

db_host = os.getenv('DB_HOST', 'localhost')
db_user = os.getenv('DB_USER', 'postgres')
db_password = os.getenv('DB_PASSWORD', '')
db_name = os.getenv('DB_NAME', 'stocks')

try:
    conn = psycopg2.connect(
        host=db_host,
        user=db_user,
        password=db_password if db_password else None,
        database=db_name
    )
    cur = conn.cursor()

    print("=== ALGO_METRICS_DAILY SCHEMA ===")
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'algo_metrics_daily'
        ORDER BY ordinal_position
    """)
    for col, dtype, nullable, default in cur.fetchall():
        null_str = "NULL" if nullable == "YES" else "NOT NULL"
        default_str = f" DEFAULT {default}" if default else ""
        print(f"  {col:20s} {dtype:15s} {null_str:8s} {default_str}")

    print("\n=== TABLE CONSTRAINTS ===")
    cur.execute("""
        SELECT constraint_name, constraint_type
        FROM information_schema.table_constraints
        WHERE table_name = 'algo_metrics_daily'
    """)
    for name, ctype in cur.fetchall():
        print(f"  {name}: {ctype}")

    print("\n=== TEST UPSERT ===")
    test_date = date(2026, 6, 3)
    test_values = (test_date, 25, 5, 3, 78.5)

    cur.execute("""
        INSERT INTO algo_metrics_daily (date, total_actions, entries, exits, avg_signal_score)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
            total_actions = EXCLUDED.total_actions,
            entries = EXCLUDED.entries,
            exits = EXCLUDED.exits,
            avg_signal_score = EXCLUDED.avg_signal_score
    """, test_values)

    print(f"[OK] UPSERT successful for {test_date}")

    # Verify it was inserted
    cur.execute("SELECT * FROM algo_metrics_daily WHERE date = %s", (test_date,))
    row = cur.fetchone()
    if row:
        print(f"[OK] Data verified in table: {row}")
    else:
        print("[ERROR] Data not found after UPSERT!")

    conn.rollback()  # Rollback test data
    conn.close()
    print("\n[OK] Schema validation complete - UPSERT syntax is supported")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

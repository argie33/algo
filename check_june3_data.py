#!/usr/bin/env python3
"""Check if June 3 data is available for testing."""
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

    print("=== JUNE 3 DATA STATUS ===")
    test_date = date(2026, 6, 3)

    tables_to_check = [
        ('price_daily', 'Stock prices'),
        ('technical_data_daily', 'Technical indicators'),
        ('market_health_daily', 'Market health'),
        ('trend_template_data', 'Trend template'),
        ('buy_sell_daily', 'Buy/Sell signals'),
        ('signal_quality_scores', 'Signal quality'),
        ('swing_trader_scores', 'Swing trader scores'),
    ]

    for table, description in tables_to_check:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date = %s", (test_date,))
        count = cur.fetchone()[0]
        status = "READY" if count > 0 else "MISSING"
        print(f"{description:25s} | {count:6d} rows | {status}")

    print("\n=== AUDIT LOG STATUS (Today's trades) ===")
    cur.execute("""
        SELECT COUNT(*) FROM algo_audit_log
        WHERE DATE(created_at) = %s
    """, (test_date,))
    audit_count = cur.fetchone()[0]
    print(f"Audit log entries: {audit_count}")

    if audit_count > 0:
        cur.execute("""
            SELECT action_type, COUNT(*) FROM algo_audit_log
            WHERE DATE(created_at) = %s
            GROUP BY action_type
        """, (test_date,))
        for action, cnt in cur.fetchall():
            print(f"  {action}: {cnt}")

    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

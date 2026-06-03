#!/usr/bin/env python3
"""Check if June 2 orchestrator run exists."""
import psycopg2
import os

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

    print("=== ALGO_METRICS_DAILY (ALL) ===")
    cur.execute("""
        SELECT date, total_actions, entries, exits, avg_signal_score
        FROM algo_metrics_daily
        ORDER BY date DESC
    """)
    for row in cur.fetchall():
        print(f"{row}")

    print("\n=== CHECK DATE RANGE ===")
    cur.execute("""
        SELECT MIN(date) as first_date, MAX(date) as last_date FROM algo_metrics_daily
    """)
    print(f"Date range in algo_metrics_daily: {cur.fetchone()}")

    print("\n=== TRADES BY DATE ===")
    cur.execute("""
        SELECT entry_time::date, COUNT(*) as count
        FROM algo_trades
        GROUP BY entry_time::date
        ORDER BY entry_time::date DESC
    """)
    for date_col, count in cur.fetchall():
        print(f"  {date_col}: {count} trades")

    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

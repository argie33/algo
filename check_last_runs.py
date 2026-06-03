#!/usr/bin/env python3
"""Check last orchestrator runs and what went wrong."""
import psycopg2
import os
from datetime import datetime, date, timedelta

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

    # Get all orchestrator runs with details
    print("=== ORCHESTRATOR RUNS (Last 10) ===")
    cur.execute("""
        SELECT date, total_actions, entries, exits, avg_signal_score, created_at
        FROM algo_metrics_daily
        ORDER BY date DESC
        LIMIT 10
    """)
    for row in cur.fetchall():
        date_col, actions, entries, exits, score, created = row
        print(f"{date_col} | Actions: {actions:3d} | Entries: {entries:2d} | Exits: {exits:2d} | Score: {score} | Created: {created}")

    print("\n=== LAST SUCCESSFUL RUN DETAILS (2026-05-29) ===")
    cur.execute("""
        SELECT COUNT(*) as entry_count FROM algo_trades
        WHERE entry_time::date = '2026-05-29'
    """)
    print(f"Trades entered: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE entry_time::date = '2026-05-29' AND exit_time IS NOT NULL
    """)
    print(f"Trades exited: {cur.fetchone()[0]}")

    print("\n=== WHAT HAPPENED AFTER MAY 29 ===")
    # Check if there's a halt flag or error marker
    cur.execute("""
        SELECT * FROM algo_alerts
        WHERE created_at >= '2026-05-29'::timestamp
        ORDER BY created_at DESC
        LIMIT 10
    """)
    alerts = cur.fetchall()
    if alerts:
        print(f"Found {len(alerts)} alerts since May 29:")
        for alert in alerts:
            print(f"  {alert}")
    else:
        print("No alerts found")

    print("\n=== DATABASE STATE ===")
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE closed_at IS NULL")
    open_positions = cur.fetchone()[0]
    print(f"Open positions: {open_positions}")

    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE entry_time >= '2026-05-30'::date AND entry_time < '2026-06-03'::date
    """)
    new_trades = cur.fetchone()[0]
    print(f"New trades since May 30: {new_trades}")

    cur.execute("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_NAME='algo_orchestrator_run_log'
        ORDER BY ORDINAL_POSITION
    """)
    cols = cur.fetchall()
    if cols:
        print(f"\nOrchestrator run log columns available: {[c[0] for c in cols]}")
        cur.execute("""
            SELECT run_date, run_id, status, error_message, created_at
            FROM algo_orchestrator_run_log
            ORDER BY created_at DESC
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  {row}")
    else:
        print("\nNo orchestrator_run_log table")

    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

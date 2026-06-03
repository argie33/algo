#!/usr/bin/env python3
"""Check orchestrator execution status."""
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

    print("\n=== RECENT ORCHESTRATOR RUNS ===")
    cur.execute("""
        SELECT date, total_actions, entries, exits, avg_signal_score
        FROM algo_metrics_daily
        ORDER BY date DESC
        LIMIT 10
    """)
    for date_col, actions, entries, exits, score in cur.fetchall():
        print(f"{date_col} | Actions: {actions:3} | Entries: {entries:3} | Exits: {exits:3} | Score: {score}")

    print("\n=== TRADES ===")
    cur.execute("""
        SELECT COUNT(*) FROM algo_trades
        WHERE entry_time >= CURRENT_DATE - INTERVAL '5 days'
    """)
    print(f"Trades in last 5 days: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT COUNT(*) FROM algo_positions WHERE closed_at IS NULL
    """)
    print(f"Open positions: {cur.fetchone()[0]}")

    print("\n=== ALERTS ===")
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'algo_alerts' ORDER BY ordinal_position
    """)
    alert_cols = [row[0] for row in cur.fetchall()]
    print(f"Alert columns: {alert_cols}")

    cur.execute("""
        SELECT * FROM algo_alerts
        WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    rows = cur.fetchall()
    if rows:
        print(f"Recent alerts (last 24h): {len(rows)}")
        for row in rows:
            print(f"  {row}")
    else:
        print("No recent alerts")

    print("\n=== DATA COVERAGE ===")
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE - INTERVAL '1 day'")
    signals_today = cur.fetchone()[0]
    print(f"Buy/Sell signals (yesterday): {signals_today}")

    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = TRUE")
    active_stocks = cur.fetchone()[0]
    print(f"Active symbols: {active_stocks}")

    conn.close()
    print("\nDone")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

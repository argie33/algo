#!/usr/bin/env python3
"""Run orchestrator for missed dates (2026-06-01 and 2026-06-02)."""
import logging
from datetime import date
import psycopg2
import os
import sys

# Force UTF-8 output to prevent encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

logging.getLogger().setLevel(logging.CRITICAL)

from algo.algo_orchestrator import Orchestrator

print("Running orchestrator for missed trading days...\n")

# Run for 2026-06-01 (Monday)
print("[1/2] Running orchestrator for 2026-06-01 (Monday)")
try:
    orch = Orchestrator(run_date=date(2026, 6, 1), dry_run=False, verbose=False)
    result = orch.run()
    print("      [OK] SUCCESS")
except Exception as e:
    print(f"      [ERROR] {e}")

# Run for 2026-06-02 (Tuesday)
print("[2/2] Running orchestrator for 2026-06-02 (Tuesday)")
try:
    orch = Orchestrator(run_date=date(2026, 6, 2), dry_run=False, verbose=False)
    result = orch.run()
    print("      [OK] SUCCESS")
except Exception as e:
    print(f"      [ERROR] {e}")

# Verify metrics were recorded
print("\n[VERIFY] Metrics recorded in database:")
print("-" * 60)

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

    cur.execute("""
        SELECT date, total_actions, entries, exits
        FROM algo_metrics_daily
        WHERE date >= CURRENT_DATE - INTERVAL '5 days'
        ORDER BY date DESC
        LIMIT 10
    """)

    for row in cur.fetchall():
        date_col, actions, entries, exits = row
        status = "NEW" if date_col >= date(2026, 6, 1) else ""
        print(f"  {date_col} | Actions: {actions:3} | Entries: {entries:3} | Exits: {exits:3}  {status}")

    conn.close()
    print("\n[DONE] Orchestrator runs complete and metrics recorded")

except Exception as e:
    print(f"\n[ERROR] Could not verify metrics: {e}")

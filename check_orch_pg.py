#!/usr/bin/env python3
"""Check latest orchestrator run and audit log via PostgreSQL."""
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Get latest orchestrator run
print("=== LATEST ORCHESTRATOR RUN ===")
cur.execute("""
    SELECT * FROM algo_orchestrator_runs
    ORDER BY run_id DESC LIMIT 1
""")
run = cur.fetchone()
if run:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'algo_orchestrator_runs'
        ORDER BY ordinal_position
    """)
    cols = [row[0] for row in cur.fetchall()]
    for col, val in zip(cols, run):
        print(f"{col}: {val}")

    run_id = run[0]  # run_id is first column

    print(f"\n=== AUDIT LOG FOR RUN {run_id} ===")
    cur.execute("""
        SELECT action_type, status, details, created_at
        FROM algo_audit_log
        WHERE action_type LIKE 'PHASE_%'
        ORDER BY created_at
    """)

    logs = cur.fetchall()
    for log in logs:
        print(f"{log[0]:20} -> {log[1]:15} [{log[3]}]")
        if log[2]:
            print(f"  Details: {log[2][:100]}")

cur.close()
conn.close()

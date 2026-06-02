#!/usr/bin/env python3
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext
import time

try:
    with DatabaseContext('write') as cur:
        # Forcefully terminate ALL processes holding advisory locks
        cur.execute("""
            SELECT pid, usename, query_start
            FROM pg_stat_activity
            WHERE pid != pg_backend_pid()
            AND state = 'active'
            ORDER BY query_start
        """)

        procs = cur.fetchall()
        print(f"Found {len(procs)} active processes. Killing stuck loaders...")

        for pid, user, start in procs:
            if user == 'stocks':  # Only kill our loader processes
                print(f"  Terminating {user} PID {pid} (started {start})")
                cur.execute("SELECT pg_terminate_backend(%s)", (pid,))

    # Wait for termination
    time.sleep(1)

    # Verify all locks released
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) FROM pg_locks WHERE locktype = 'advisory' AND granted = true")
        count = cur.fetchone()[0]
        print(f"\nAdvisory locks remaining: {count}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

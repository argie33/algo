#!/usr/bin/env python3
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext

try:
    # Nuke all advisory locks by reconnecting and running multiple release commands
    for attempt in range(3):
        with DatabaseContext('write') as cur:
            # Try multiple approaches to clear locks
            cur.execute("SELECT pg_advisory_unlock_all()")
            print(f"Attempt {attempt+1}: pg_advisory_unlock_all() called")

    # Verify
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) FROM pg_locks WHERE locktype = 'advisory'")
        count = cur.fetchone()[0]
        print(f"Advisory locks remaining: {count}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

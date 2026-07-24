#!/usr/bin/env python3
"""Clear RDS orchestrator lock."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext

try:
    with DatabaseContext("write") as cur:
        # Delete the orchestrator run lock
        cur.execute(
            """
            DELETE FROM rds_distributed_locks
            WHERE lock_key = 'orchestrator-run-lock'
            """
        )
        print(f"[OK] Cleared orchestrator run lock")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

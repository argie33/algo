#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get audit logs related to the problematic run
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'algo_audit_log'
        ORDER BY ordinal_position
    ''')

    cols = cur.fetchall()
    print("algo_audit_log columns:")
    for col in cols:
        print(f"  {col['column_name']}")

    # Get recent audit logs for exit execution
    print("\n\nRecent exit-related audit logs:")
    cur.execute('''
        SELECT *
        FROM algo_audit_log
        WHERE action ILIKE '%exit%' OR details ILIKE '%exit%'
        ORDER BY created_at DESC
        LIMIT 30
    ''')

    logs = cur.fetchall()
    for log in logs:
        print(f"\n{log['created_at']} | {log['action']}")
        if log.get('details'):
            print(f"  Details: {log['details'][:300]}")

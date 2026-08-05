#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get the schema
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_reconciliation_log'
        ORDER BY ordinal_position
    ''')

    cols = cur.fetchall()
    print("algo_reconciliation_log schema:")
    for col in cols:
        print(f"  {col['column_name']:30} {col['data_type']}")

    # Get recent logs
    print("\n\nRecent reconciliation logs:")
    cur.execute('''
        SELECT *
        FROM algo_reconciliation_log
        ORDER BY created_at DESC
        LIMIT 30
    ''')

    logs = cur.fetchall()
    for log in logs:
        ts = log['created_at']
        error = log.get('error_message', '')
        status = log.get('status', '')
        print(f"\n{ts} | {status:20} | Symbol: {log.get('symbol', 'N/A')}")
        if error:
            print(f"  Error: {error[:200]}")

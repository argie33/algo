#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get the schema first
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_exit_check_errors'
        ORDER BY ordinal_position
    ''')

    cols = cur.fetchall()
    print("algo_exit_check_errors schema:")
    for col in cols:
        print(f"  {col['column_name']:30} {col['data_type']}")

    # Get recent errors
    print("\n\nRecent exit check errors:")
    cur.execute('''
        SELECT *
        FROM algo_exit_check_errors
        ORDER BY created_at DESC
        LIMIT 20
    ''')

    errors = cur.fetchall()
    for err in errors:
        print(f"\n{err['created_at']} | {err['symbol']}")
        print(f"  Phase: {err.get('phase_name', 'N/A')}")
        print(f"  Error: {err.get('error_type', 'N/A')}")
        if err.get('error_message'):
            print(f"  Message: {err['error_message'][:200]}")
        if err.get('traceback'):
            print(f"  Traceback: {err['traceback'][:200]}")

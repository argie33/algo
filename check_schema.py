#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get table schema
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'orchestrator_execution_log'
        ORDER BY ordinal_position
    ''')

    rows = cur.fetchall()
    print(f'orchestrator_execution_log columns ({len(rows)} total):\n')
    for row in rows:
        col_name = row['column_name']
        col_type = row['data_type']
        nullable = row['is_nullable']
        print(f"  {col_name:30} {col_type:20} nullable={nullable}")

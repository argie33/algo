#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_trades'
        ORDER BY ordinal_position
    ''')

    cols = cur.fetchall()
    print("algo_trades schema:")
    for col in cols:
        print(f"  {col['column_name']:30} {col['data_type']}")

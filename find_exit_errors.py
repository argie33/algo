#!/usr/bin/env python3
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Check what tables exist related to execution or errors
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    ''')

    tables = cur.fetchall()
    print("All tables in the database:")
    for table in tables:
        print(f"  - {table['table_name']}")

    # Check for error-related tables
    print("\n\nTables that might contain error details:")
    for table in tables:
        name = table['table_name'].lower()
        if any(x in name for x in ['error', 'log', 'exit', 'trade', 'position']):
            print(f"  - {table['table_name']}")

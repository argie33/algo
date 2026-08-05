#!/usr/bin/env python3
"""Verify the ID type mismatch issue."""
import sys
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    print("="*80)
    print("ID TYPE MISMATCH VERIFICATION")
    print("="*80)

    # Check algo_positions.id type and values
    print("\n1. ALGO_POSITIONS TABLE:")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_positions' AND column_name IN ('id', 'position_id')
    """)
    for row in cur.fetchall():
        print(f"  {row['column_name']:20} = {row['data_type']}")

    # Check sample values
    cur.execute("SELECT id, symbol FROM algo_positions LIMIT 3")
    for row in cur.fetchall():
        print(f"  Sample: id={row['id']} (type={type(row['id']).__name__}) | symbol={row['symbol']}")

    # Check algo_trades table
    print("\n2. ALGO_TRADES TABLE:")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_trades' AND column_name IN ('id', 'position_id')
    """)
    for row in cur.fetchall():
        print(f"  {row['column_name']:20} = {row['data_type']}")

    # Check sample values
    cur.execute("""
        SELECT id, trade_id, position_id
        FROM algo_trades
        WHERE status = 'open'
        LIMIT 3
    """)
    for row in cur.fetchall():
        print(f"  Sample: id={row['id']} | position_id={row['position_id']} (type={type(row['position_id']).__name__})")

    # Check if there's a numeric position_id field
    print("\n3. CHECKING FOR NUMERIC POSITION_ID FIELD:")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_trades'
        ORDER BY column_name
    """)
    all_cols = cur.fetchall()
    for row in all_cols:
        if 'position' in row['column_name'].lower():
            print(f"  Found: {row['column_name']:30} = {row['data_type']}")

print("\nDone!")

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
    print("ALGO_POSITIONS - id vs position_id:")
    cur.execute("""
        SELECT id, position_id, symbol, status
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY updated_at DESC
        LIMIT 10
    """)

    for row in cur.fetchall():
        pos_id = row['position_id']
        id_val = row['id']
        print(f"  id={id_val:5} | position_id={pos_id} | {row['symbol']:6} | {row['status']}")

    print("\n\nALGO_TRADES - try matching with position_id:")
    cur.execute("""
        SELECT id, position_id, trade_id, symbol
        FROM algo_trades
        WHERE status = 'open'
        ORDER BY updated_at DESC
        LIMIT 10
    """)

    for row in cur.fetchall():
        pos_id = row['position_id']
        print(f"  trade_id={row['trade_id']:20} | position_id={pos_id} | {row['symbol']}")

        # Try to find matching position using position_id UUID
        cur.execute("""
            SELECT id, symbol, status
            FROM algo_positions
            WHERE position_id = %s
        """, (pos_id,))

        pos = cur.fetchone()
        if pos:
            print(f"    -> MATCH: position {pos['id']} ({pos['symbol']})")
        else:
            print(f"    -> NO MATCH with position_id")

            # Try matching by ID as string
            cur.execute("""
                SELECT id, symbol, status
                FROM algo_positions
                WHERE id = %s::int
            """, (pos_id,))
            pos = cur.fetchone()
            if pos:
                print(f"    -> MATCH by ID: position {pos['id']}")
            else:
                print(f"    -> NO MATCH at all")

#!/usr/bin/env python3
"""Check the critical sync issue between positions and trades."""
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
    print("CRITICAL POSITION-TRADE SYNC ISSUE")
    print("="*80)

    # Get the open positions
    print("\nOPEN POSITIONS:")
    cur.execute("""
        SELECT id, symbol, status, quantity, entry_price, current_price
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY updated_at DESC
        LIMIT 5
    """)

    positions = cur.fetchall()
    for pos in positions:
        pos_id = pos['id']
        print(f"  ID: {pos_id} | {pos['symbol']} | qty={pos['quantity']} | entry={pos['entry_price']} | current={pos['current_price']}")

        # Check for matching trade
        cur.execute("""
            SELECT id, trade_id, symbol, status, entry_price, quantity
            FROM algo_trades
            WHERE position_id = %s
        """, (str(pos_id),))

        trades = cur.fetchall()
        if trades:
            print(f"    -> Found {len(trades)} matching trade(s):")
            for trade in trades:
                print(f"       Trade {trade['trade_id']} | {trade['symbol']} | status={trade['status']} | qty={trade['quantity']}")
        else:
            print(f"    -> NO MATCHING TRADE FOUND!")

    # Check for the opposite - trades with no positions
    print("\n\nOPEN TRADES:")
    cur.execute("""
        SELECT id, trade_id, symbol, status, entry_price, quantity, position_id
        FROM algo_trades
        WHERE status = 'open'
        ORDER BY updated_at DESC
        LIMIT 5
    """)

    trades = cur.fetchall()
    for trade in trades:
        trade_id = trade['id']
        print(f"  Trade {trade['trade_id']} | {trade['symbol']} | qty={trade['quantity']} | position_id={trade['position_id']}")

        # Check for matching position
        pos_id = trade['position_id']
        if pos_id:
            cur.execute("""
                SELECT id, symbol, status, quantity
                FROM algo_positions
                WHERE id::text = %s
            """, (pos_id,))

            pos = cur.fetchone()
            if pos:
                print(f"    -> Found position: {pos['symbol']} | status={pos['status']} | qty={pos['quantity']}")
            else:
                print(f"    -> NO MATCHING POSITION FOUND!")
        else:
            print(f"    -> NO POSITION_ID in trade!")

print("\nDone!")

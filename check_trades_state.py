#!/usr/bin/env python3
"""Check current state of trades in database"""

import os
import sys
from datetime import datetime

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db import DatabaseContext

def check_trades():
    with DatabaseContext('read') as cur:
        # Check recent trades
        cur.execute("""
            SELECT trade_id, symbol, quantity, status, entry_date, entry_price,
                   exit_date, exit_price, exit_reason, created_at
            FROM algo_trades
            WHERE entry_date >= CURRENT_DATE - INTERVAL '2 days'
            ORDER BY created_at DESC
            LIMIT 20
        """)
        trades = cur.fetchall()

        print("\n" + "="*100)
        print("RECENT TRADES (last 2 days)")
        print("="*100)

        if not trades:
            print("No trades found")
            return

        for trade in trades:
            (tid, sym, qty, status, entry_date, entry_price,
             exit_date, exit_price, exit_reason, created_at) = trade

            print(f"\nTrade ID: {tid}")
            print(f"  Symbol: {sym}")
            print(f"  Status: {status}")
            print(f"  Quantity: {qty}")
            print(f"  Entry: {entry_date} @ {entry_price}")
            if status == 'closed':
                print(f"  Exit: {exit_date} @ {exit_price} ({exit_reason})")
            print(f"  Created: {created_at}")

if __name__ == '__main__':
    check_trades()

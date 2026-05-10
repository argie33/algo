#!/usr/bin/env python3
"""Validate position states after orchestrator run"""
from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check positions
    cur.execute("""
        SELECT t.symbol, t.entry_price, t.stop_loss_price, t.target_1_price,
               p.position_id, p.quantity, p.current_stop_price, p.target_levels_hit,
               p.updated_at, p.status
        FROM algo_trades t
        LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
        WHERE t.symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA')
        ORDER BY t.symbol
    """)

    print("\n" + "="*100)
    print("POSITION VALIDATION")
    print("="*100)

    positions = cur.fetchall()
    for row in positions:
        sym, entry, init_stop, t1, pos_id, qty, cur_stop, hits, updated, status = row
        print(f"\n{sym}:")
        try:
            entry = float(entry) if entry else None
            init_stop = float(init_stop) if init_stop else None
            t1 = float(t1) if t1 else None
            cur_stop = float(cur_stop) if cur_stop else None

            if entry:
                print(f"  Entry: ${entry:.2f}")
            if init_stop:
                print(f"  Initial Stop: ${init_stop:.2f}")
            if t1:
                print(f"  Target 1: ${t1:.2f}")
            else:
                print(f"  Target 1: None")
            if cur_stop:
                print(f"  Current Stop: ${cur_stop:.2f}")
            elif init_stop:
                print(f"  Current Stop: ${init_stop:.2f}")
            else:
                print(f"  Current Stop: None")
            print(f"  Quantity: {qty}")
            print(f"  Target Hits: {hits}")
            print(f"  Status: {status}")
            print(f"  Updated: {updated}")

            if cur_stop and init_stop and cur_stop > init_stop:
                print(f"  ✓ STOP RAISED: from ${init_stop:.2f} to ${cur_stop:.2f}")
            elif cur_stop == init_stop:
                print(f"  - Stop unchanged")
        except Exception as e:
            print(f"  Error formatting values: {e}")

        # Check if there were partial exits
        cur.execute("""
            SELECT partial_exit_count, partial_exits_log
            FROM algo_trades
            WHERE symbol = %s AND status IN ('open', 'closed')
            LIMIT 1
        """, (sym,))
        exit_info = cur.fetchone()
        if exit_info:
            count, log = exit_info
            if count > 0:
                print(f"  ✓ PARTIAL EXITS: {count}")
                if log:
                    print(f"    Log: {log[:100]}...")

    print("\n" + "="*100)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

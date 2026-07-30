#!/usr/bin/env python3
import os
os.environ['LOCAL_MODE'] = 'true'

from utils.dotenv_loader import load_env_local
load_env_local()
from utils.db.context import DatabaseContext
from utils.trading import TradeStatus

open_statuses = TradeStatus.all_open()
print(f"Open trade statuses: {open_statuses}")

with DatabaseContext('read') as cur:
    # Check which trades are in open status
    placeholders = ','.join(['%s'] * len(open_statuses))
    cur.execute(f'''
    SELECT t.trade_id, t.symbol, t.status, COUNT(*) as cnt
    FROM algo_trades t
    WHERE t.status IN ({placeholders})
    GROUP BY t.trade_id, t.symbol, t.status
    ORDER BY t.symbol
    ''', open_statuses)

    trades = cur.fetchall()
    print(f"\nTrades in open status: {len(trades)}")
    for trade_id, symbol, status, cnt in trades:
        print(f"  {symbol}: status={status}")

    # Now check the positions for these trades
    print(f"\nPositions Phase 3 would process:")
    cur.execute(f'''
    SELECT t.symbol, t.status as trade_status, p.status as pos_status,
           p.current_price, p.current_stop_price, p.quantity
    FROM algo_trades t
    JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
    WHERE t.status IN ({placeholders}) AND p.status = 'open' AND p.quantity > 0
    ORDER BY t.symbol
    ''', open_statuses)

    rows = cur.fetchall()
    print(f"Total positions to process: {len(rows)}")
    for symbol, t_status, p_status, cur_price, stop_price, qty in rows:
        is_below = "BELOW STOP" if cur_price and stop_price and cur_price <= stop_price else "OK"
        print(f"  {symbol}: price={cur_price}, stop={stop_price} [{is_below}], qty={qty}")

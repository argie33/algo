#!/usr/bin/env python3
"""Audit system data and deployment state"""
from utils.db.context import DatabaseContext
import json
from datetime import datetime

# Check if we have growth scores
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT COUNT(*) as cnt, COUNT(DISTINCT symbol) as unique_symbols
        FROM stock_scores
        WHERE growth_score IS NOT NULL
    """)
    growth_scores = cur.fetchall()
    print("[OK] Growth Scores:", json.dumps(growth_scores, indent=2, default=str))

# Check if we have positions
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT COUNT(*) as total_positions, SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_positions
        FROM algo_trades
    """)
    positions = cur.fetchall()
    print("\n[OK] Positions:", json.dumps(positions, indent=2, default=str))

# Check last trades with MORE detail
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT entry_date, symbol, entry_price, status
        FROM algo_trades
        ORDER BY entry_date DESC
        LIMIT 10
    """)
    last_trades = cur.fetchall()
    print("\n[OK] Last 10 Trades:", json.dumps(last_trades, indent=2, default=str))

# Check orchestrator runs - THIS IS KEY
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT run_id, start_time, end_time, status
        FROM orchestrator_runs
        ORDER BY start_time DESC
        LIMIT 10
    """)
    orch_runs = cur.fetchall()
    print("\n[OK] Orchestrator Runs (last 10):", json.dumps(orch_runs, indent=2, default=str))

# Check portfolio snapshots
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT run_id, timestamp, total_portfolio_value, total_cash, total_positions
        FROM algo_portfolio_snapshots
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    snapshots = cur.fetchall()
    print("\n[OK] Portfolio Snapshots (last 5):", json.dumps(snapshots, indent=2, default=str))

# Check schema for data_loader_status
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='data_loader_status'
    """)
    loader_cols = cur.fetchall()
    print("\n[OK] data_loader_status schema:", json.dumps(loader_cols, indent=2, default=str))

# Check buy_sell_daily signals generated recently
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT COUNT(*) as buy_signals, MAX(date) as max_date
        FROM buy_sell_daily
        WHERE signal = 'BUY'
    """)
    buy_signals = cur.fetchall()
    print("\n[OK] BUY signals in buy_sell_daily:", json.dumps(buy_signals, indent=2, default=str))

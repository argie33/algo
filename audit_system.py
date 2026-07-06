#!/usr/bin/env python3
"""Audit system data and deployment state"""
from utils.db import DatabaseContext
import json

db = DatabaseContext('read')

# Check if we have growth scores
growth_scores = db.fetch_all("""
    SELECT COUNT(*) as cnt, COUNT(DISTINCT symbol) as unique_symbols
    FROM stock_scores
    WHERE growth_score IS NOT NULL
""")
print("Growth Scores:", json.dumps(growth_scores, indent=2, default=str))

# Check if we have positions
positions = db.fetch_all("""
    SELECT COUNT(*) as total_positions, SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open_positions
    FROM algo_trades
""")
print("\nPositions:", json.dumps(positions, indent=2, default=str))

# Check last trades
last_trades = db.fetch_all("""
    SELECT entry_date, symbol, entry_price, status
    FROM algo_trades
    ORDER BY entry_date DESC
    LIMIT 5
""")
print("\nLast Trades:", json.dumps(last_trades, indent=2, default=str))

# Check data loader status
loader_status = db.fetch_all("""
    SELECT table_name, last_successful_load, status
    FROM data_loader_status
    ORDER BY last_successful_load DESC
    LIMIT 10
""")
print("\nLoader Status (last 10):", json.dumps(loader_status, indent=2, default=str))

# Check portfolio snapshots (Phase 9 output)
snapshots = db.fetch_all("""
    SELECT run_id, timestamp, total_portfolio_value, total_cash, total_positions
    FROM algo_portfolio_snapshots
    ORDER BY timestamp DESC
    LIMIT 3
""")
print("\nPortfolio Snapshots (last 3):", json.dumps(snapshots, indent=2, default=str))

# Check orchestrator runs
orch_runs = db.fetch_all("""
    SELECT run_id, start_time, end_time, status
    FROM orchestrator_runs
    ORDER BY start_time DESC
    LIMIT 5
""")
print("\nOrchestrator Runs (last 5):", json.dumps(orch_runs, indent=2, default=str))

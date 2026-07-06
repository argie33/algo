#!/usr/bin/env python3
"""Check portfolio snapshots and orchestrator state"""
from utils.db.context import DatabaseContext
import json
from datetime import datetime, timedelta

with DatabaseContext('read') as cur:
    # Latest portfolio snapshot
    cur.execute("""
        SELECT snapshot_date, total_portfolio_value, total_cash, position_count, created_at
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 5
    """)
    snapshots = cur.fetchall()
    print("Latest Portfolio Snapshots:")
    for s in snapshots:
        print(f"  {s}")

    # Check data loader runs to see if loaders are running
    cur.execute("""
        SELECT table_name, created_at, status
        FROM data_loader_runs
        ORDER BY created_at DESC
        LIMIT 10
    """)
    loader_runs = cur.fetchall()
    print("\nData Loader Runs (last 10):")
    for lr in loader_runs:
        print(f"  {lr}")

    # Check orchestrator state table
    cur.execute("""
        SELECT state, last_update, details
        FROM algo_orchestrator_state
        LIMIT 1
    """)
    orch_state = cur.fetchall()
    print("\nOrchestrator State:")
    for s in orch_state:
        print(f"  {s}")

    # Check algo_runtime_state
    cur.execute("""
        SELECT key, value, last_update
        FROM algo_runtime_state
        WHERE key LIKE '%orchestrator%' OR key LIKE '%scheduler%'
        ORDER BY key
    """)
    runtime = cur.fetchall()
    print("\nRuntime State (orchestrator/scheduler related):")
    for r in runtime:
        print(f"  {r}")

#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext
from datetime import datetime

print("\nOrchestrator Run History:")
print("="*80)

try:
    with DatabaseContext('read') as cur:
        # Get recent trades
        cur.execute("""
            SELECT trade_date, COUNT(*) as trade_count, COUNT(DISTINCT symbol) as unique_symbols
            FROM algo_trades
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 5
        """)

        print("Recent Trading Activity:")
        for row in cur.fetchall():
            trade_date, count, symbols = row
            print(f"  {trade_date}: {count} trades across {symbols} symbols")

        # Check if orchestrator execution table exists and has recent runs
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'orchestrator_executions'
            )
        """)

        if cur.fetchone()[0]:
            cur.execute("""
                SELECT run_id, execution_date, status, created_at
                FROM orchestrator_executions
                ORDER BY execution_date DESC
                LIMIT 3
            """)

            print("\nRecent Orchestrator Executions:")
            for row in cur.fetchall():
                run_id, exec_date, status, created_at = row
                print(f"  {exec_date}: {status} (run_id={run_id})")
        else:
            print("\norchestrator_executions table doesn't exist - using algo_trades as proxy")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("\nTo trigger an orchestrator run now, use:")
print("  python -m algo.algo_orchestrator")
print("="*80)

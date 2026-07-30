import sys
from datetime import datetime
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # Get last 5 orchestration runs
    cur.execute("""
    SELECT 
        run_id,
        run_date,
        overall_status,
        halt_reason,
        execution_time_seconds,
        started_at,
        completed_at
    FROM algo_orchestrator_runs
    ORDER BY started_at DESC
    LIMIT 5
    """)
    
    runs = cur.fetchall()
    for run_id, run_date, status, halt_reason, exec_time, started, completed in runs:
        print(f"\n{'='*70}")
        print(f"Run ID: {run_id}")
        print(f"Run Date: {run_date}")
        print(f"Overall Status: {status}")
        if halt_reason:
            print(f"Halt Reason: {halt_reason}")
        print(f"Execution Time: {exec_time:.2f}s")
        print(f"Started: {started}")
        print(f"Completed: {completed}")

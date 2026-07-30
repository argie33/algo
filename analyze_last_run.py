import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # Get the most recent run from algo_orchestrator_runs
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
    LIMIT 1
    """)
    
    row = cur.fetchone()
    if row:
        (run_id, run_date, status, halt_reason, exec_time, started, completed) = row
        
        print(f"=== LATEST ALGO_ORCHESTRATOR_RUNS ===\n")
        print(f"Run ID: {run_id}")
        print(f"Date: {run_date}")
        print(f"Status: {status}")
        print(f"Duration: {exec_time:.2f}s")
        
        if halt_reason:
            print(f"Halt Reason: {halt_reason[:100]}")
    
    # Get full details from orchestrator_execution_log
    cur.execute("""
    SELECT 
        run_id,
        overall_status,
        summary,
        phase_results
    FROM orchestrator_execution_log
    WHERE run_id = %s
    """, (run_id,))
    
    exec_row = cur.fetchone()
    if exec_row:
        (exec_run_id, exec_status, summary, phase_results) = exec_row
        print(f"\n=== ORCHESTRATOR_EXECUTION_LOG DETAILS ===\n")
        
        if summary:
            print(f"Summary: {summary}")
        
        print(f"\nPhase Details:")
        if phase_results:
            for phase_data in phase_results:
                name = phase_data.get('name', '?')
                phase_num = phase_data.get('phase', '?')
                p_status = phase_data.get('status', '?')
                p_summary = phase_data.get('summary', '')
                
                print(f"  Phase {phase_num}: {name:20} - {p_status:10} - {p_summary[:60]}")

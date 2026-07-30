import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection
import json

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # Get execution log for the latest run
    cur.execute("""
    SELECT 
        run_id,
        overall_status,
        phases_completed,
        phases_halted,
        phases_errored,
        phase_results,
        summary
    FROM orchestrator_execution_log
    WHERE run_id = 'LOCAL-AFTERNOON-20260730-092023-943497'
    """)
    
    row = cur.fetchone()
    if row:
        run_id, status, completed, halted, errored, phase_results, summary = row
        print(f"Run: {run_id}")
        print(f"Overall Status: {status}")
        print(f"Phases - Completed: {completed}, Halted: {halted}, Errored: {errored}")
        
        if phase_results:
            if isinstance(phase_results, str):
                results = json.loads(phase_results)
            else:
                results = phase_results
            
            print("\nPhase Results:")
            if isinstance(results, dict):
                for phase_num, phase_data in sorted(results.items(), key=lambda x: int(x[0])):
                    print(f"\n  Phase {phase_num}:")
                    if isinstance(phase_data, dict):
                        for key, value in phase_data.items():
                            print(f"    {key}: {value}")
                    else:
                        print(f"    {phase_data}")
            else:
                print(f"  Raw: {results}")
        
        if summary:
            print(f"\nSummary:\n{summary}")

import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    
    print("=== HALT FLAG STATUS ===\n")
    
    # Check halt flags
    cur.execute("""
    SELECT key, value
    FROM algo_config
    WHERE key LIKE '%halt%' OR key LIKE '%circuit%'
    ORDER BY key
    """)
    
    halts = cur.fetchall()
    if halts:
        print("Active halt/circuit settings:")
        for key, value in halts:
            print(f"  {key}: {value}")
    else:
        print("OK - No halt-related config flags found")
    
    # Check orchestrator state
    print("\n=== ORCHESTRATOR STATE ===\n")
    
    cur.execute("""
    SELECT key, value
    FROM algo_config
    WHERE key IN ('is_halted', 'halt_reason', 'halt_until')
    """)
    
    state = cur.fetchall()
    has_halt = False
    for key, value in state:
        print(f"{key}: {value}")
        if key == 'is_halted' and value == 'true':
            has_halt = True
    
    if not has_halt:
        print("OK - No active halts")
    
    # Check recent circuit breaker status
    print("\n=== CIRCUIT BREAKER STATUS ===\n")
    
    cur.execute("""
    SELECT key, value
    FROM algo_config
    WHERE key IN ('circuit_breaker_triggered', 'max_daily_loss_pct', 'halt_drawdown_pct')
    """)
    
    circuit = cur.fetchall()
    for key, value in circuit:
        print(f"  {key}: {value}")

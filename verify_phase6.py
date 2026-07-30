import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # Check for any errors in exit checks
    cur.execute("""
    SELECT 
        position_id,
        symbol,
        error_type,
        error_message,
        created_at
    FROM algo_exit_check_errors
    WHERE created_at >= NOW() - INTERVAL '2 hours'
    ORDER BY created_at DESC
    """)
    
    errors = cur.fetchall()
    if errors:
        print(f"Found {len(errors)} exit check errors in last 2 hours:")
        for pos_id, symbol, error_type, message, created in errors:
            print(f"\n  Position {pos_id} ({symbol})")
            print(f"    Type: {error_type}")
            print(f"    Message: {message}")
            print(f"    Created: {created}")
    else:
        print("OK - No exit check errors found")
        
    # Check current positions and their exit status
    cur.execute("""
    SELECT 
        position_id,
        symbol,
        entry_price,
        current_price,
        quantity,
        unrealized_pnl_pct,
        stop_loss_price,
        current_stop_price,
        stage_in_exit_plan,
        is_open
    FROM algo_positions
    WHERE is_open = true
    ORDER BY symbol
    """)
    
    positions = cur.fetchall()
    print(f"\nOK - {len(positions)} open positions:")
    for pos_id, symbol, entry, current, qty, pnl_pct, stop_loss, current_stop, stage, is_open in positions:
        if pnl_pct:
            print(f"  {symbol:5} qty={qty:6.0f}  entry={entry:8.2f}  current={current:8.2f}  P&L={pnl_pct:+6.2f}%")
        else:
            print(f"  {symbol:5} qty={qty:6.0f}  entry={entry:8.2f}  current={current:8.2f}  P&L=?")
        print(f"         stop_loss={stop_loss:8.2f}  current_stop={current_stop:8.2f}  stage={stage}")

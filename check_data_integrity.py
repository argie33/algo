import sys
sys.path.insert(0, '.')
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # Check for NULL values in critical fields
    print("=== DATA INTEGRITY CHECKS ===\n")
    
    # 1. Positions with NULL prices
    cur.execute("""
    SELECT COUNT(*) as null_count
    FROM algo_positions
    WHERE status = 'open' AND (entry_price IS NULL OR current_price IS NULL)
    """)
    null_count = cur.fetchone()[0]
    if null_count > 0:
        print(f"ISSUE: {null_count} open positions with NULL prices")
    else:
        print("OK - All open positions have prices")
    
    # 2. Positions with invalid targets
    cur.execute("""
    SELECT COUNT(*) as invalid_count
    FROM algo_positions
    WHERE status = 'open' AND (
        target_1_price IS NULL OR
        target_2_price IS NULL OR
        target_3_price IS NULL
    )
    """)
    invalid_count = cur.fetchone()[0]
    if invalid_count > 0:
        print(f"ISSUE: {invalid_count} open positions with NULL target prices")
    else:
        print("OK - All open positions have target prices")
    
    # 3. Positions with invalid stop losses
    cur.execute("""
    SELECT COUNT(*) as invalid_count
    FROM algo_positions
    WHERE status = 'open' AND (
        stop_loss_price IS NULL OR 
        current_stop_price IS NULL
    )
    """)
    invalid_count = cur.fetchone()[0]
    if invalid_count > 0:
        print(f"ISSUE: {invalid_count} open positions with NULL stop prices")
    else:
        print("OK - All open positions have stop prices")
    
    # 4. Positions with zero quantity
    cur.execute("""
    SELECT COUNT(*) as zero_qty
    FROM algo_positions
    WHERE status = 'open' AND quantity <= 0
    """)
    zero_qty = cur.fetchone()[0]
    if zero_qty > 0:
        print(f"ISSUE: {zero_qty} open positions with zero/negative quantity")
    else:
        print("OK - All open positions have positive quantity")
    
    # 5. Trades with missing position references
    cur.execute("""
    SELECT COUNT(*) as orphan_count
    FROM algo_trades t
    LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
    WHERE t.status IN ('open', 'filled', 'partially_filled')
    AND p.position_id IS NULL
    """)
    orphan_count = cur.fetchone()[0]
    if orphan_count > 0:
        print(f"ISSUE: {orphan_count} open trades with no position reference")
    else:
        print("OK - All open trades have positions")
    
    # 6. Positions with negative P&L that still have positive stop
    cur.execute("""
    SELECT symbol, entry_price, current_price, stop_loss_price, 
           ROUND((current_price - entry_price) / entry_price * 100, 2) as pnl_pct
    FROM algo_positions
    WHERE status = 'open' 
      AND current_price < entry_price
      AND stop_loss_price > current_price
    ORDER BY pnl_pct ASC
    LIMIT 5
    """)
    bad_stops = cur.fetchall()
    if bad_stops:
        print(f"WARNING: Positions with unrealistic stop losses (below current price):")
        for symbol, entry, current, stop, pnl in bad_stops:
            print(f"  {symbol}: entry={entry:.2f}, current={current:.2f}, stop={stop:.2f}, P&L={pnl}%")
    else:
        print("OK - No unrealistic stop losses")
    
    # 7. Check for positions in 'stage_in_exit_plan' that should have exited
    cur.execute("""
    SELECT symbol, entry_price, current_price, target_levels_hit, stage_in_exit_plan,
           ROUND((current_price - entry_price) / entry_price * 100, 2) as pnl_pct
    FROM algo_positions
    WHERE status = 'open' AND stage_in_exit_plan IS NOT NULL
    ORDER BY symbol
    """)
    staged_positions = cur.fetchall()
    if staged_positions:
        print(f"\nPositions in exit plan stages ({len(staged_positions)}):")
        for symbol, entry, current, hits, stage, pnl in staged_positions:
            print(f"  {symbol}: stage={stage}, hits={hits}, P&L={pnl}%")
    else:
        print("OK - No positions in exit stages")

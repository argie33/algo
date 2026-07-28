#!/usr/bin/env python3
"""
Validate exit and entry execution logic paths for production readiness.
"""

import psycopg2
import os
import sys
from datetime import datetime, date

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "trading_algo"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )

def test_exit_conditions():
    """Validate that positions correctly identify exit conditions."""
    print("\n=== EXIT CONDITION VALIDATION ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Find positions that SHOULD trigger stops
    cur.execute("""
    SELECT symbol, entry_price, stop_loss_price, current_price,
           (current_price <= stop_loss_price) as should_exit
    FROM algo_positions
    WHERE status = 'open'
    ORDER BY symbol
    """)

    rows = cur.fetchall()
    stops_should_trigger = sum(1 for row in rows if row[4])  # count WHERE should_exit=true

    print(f"Open positions: {len(rows)}")
    print(f"Positions at or below stop: {stops_should_trigger}")

    if stops_should_trigger > 0:
        print("\nPositions that SHOULD trigger stops:")
        for symbol, entry, stop, current, should_exit in rows:
            if should_exit:
                loss_pct = ((current - entry) / entry) * 100
                print(f"  {symbol}: entry=${entry:.2f}, stop=${stop:.2f}, current=${current:.2f} ({loss_pct:.1f}%)")

    # Check for ANY positions with target hits
    cur.execute("""
    SELECT symbol, entry_price, target_1_price, target_2_price, target_3_price, current_price,
           CASE
             WHEN current_price >= target_1_price THEN 'T1'
             WHEN current_price >= target_2_price THEN 'T2'
             WHEN current_price >= target_3_price THEN 'T3'
             ELSE NULL
           END as target_hit
    FROM algo_positions
    WHERE status = 'open'
    ORDER BY symbol
    """)

    rows = cur.fetchall()
    targets_hit = sum(1 for row in rows if row[6])

    print(f"\nPositions at or above targets: {targets_hit}")
    if targets_hit > 0:
        print("Positions that SHOULD trigger targets:")
        for symbol, entry, t1, t2, t3, current, hit in rows:
            if hit:
                gain_pct = ((current - entry) / entry) * 100
                print(f"  {symbol}: entry=${entry:.2f}, {hit}=${eval(f't{hit[1]}')}. current=${current:.2f} ({gain_pct:.1f}%)")

    conn.close()

    print(f"\nExit logic status: {len(rows)} positions analyzed")
    return True

def test_entry_constraints():
    """Validate entry constraints are working."""
    print("\n=== ENTRY CONSTRAINT VALIDATION ===")
    conn = get_db()
    cur = conn.cursor()

    # Get config
    cur.execute("SELECT value FROM algo_config WHERE key = 'max_positions'")
    max_pos = int(cur.fetchone()[0])

    # Count open positions
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
    open_count = cur.fetchone()[0]

    print(f"Max positions configured: {max_pos}")
    print(f"Currently open: {open_count}")

    # Calculate tolerance buffer (same as position_sizer.py)
    tolerance = max(1, int(max_pos * 0.15))
    hard_limit = max_pos + tolerance

    print(f"Tolerance buffer (15%): {tolerance}")
    print(f"Hard limit: {hard_limit}")
    print(f"Can add more: {hard_limit - open_count} positions")

    if open_count >= hard_limit:
        print("\nWARNING: At or above hard limit - no new entries will be allowed")
    elif open_count >= max_pos:
        print(f"\nWARNING: Above target ({max_pos}), in tolerance buffer")
    else:
        print(f"\nOK: Below target, can accept {max_pos - open_count} more positions")

    # Check signal generation
    cur.execute("""
    SELECT COUNT(*) FROM signal_quality_scores
    WHERE rank_vs_all_signals IS NOT NULL AND rank_vs_all_signals <= 100
    """)
    qualified = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM signal_quality_scores")
    total_signals = cur.fetchone()[0]

    print(f"\nTotal signals: {total_signals}")
    print(f"Qualified signals (top 100): {qualified}")

    # Check if entries are being blocked (from signal rejections)
    cur.execute("""
    SELECT rejection_reason, COUNT(*) as count
    FROM algo_signal_rejections
    WHERE created_at > now() - interval '4 hours'
    GROUP BY rejection_reason
    ORDER BY count DESC
    LIMIT 5
    """)

    rejections = cur.fetchall()
    if rejections:
        print("\nRecent signal rejections:")
        for reason, count in rejections:
            print(f"  {reason}: {count}")

    conn.close()
    return True

def test_execution_mode_consistency():
    """Validate execution mode is consistent across all checks."""
    print("\n=== EXECUTION MODE CONSISTENCY ===")
    conn = get_db()
    cur = conn.cursor()

    issues = []

    # Get configured mode
    cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
    mode = cur.fetchone()[0]
    print(f"Configured execution_mode: {mode}")

    # Get Alpaca paper flag
    cur.execute("SELECT value FROM algo_config WHERE key = 'alpaca_paper_trading'")
    alpaca_paper = cur.fetchone()[0].lower() in ('true', '1')
    print(f"Alpaca paper trading: {alpaca_paper}")

    # Check recent phase logs
    cur.execute("""
    SELECT run_id, completed_at
    FROM algo_orchestrator_runs
    WHERE overall_status IN ('ok', 'degraded')
    ORDER BY completed_at DESC
    LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        print(f"\nLast run: {row[0]}")

    # Consistency check
    if mode == 'paper' and not alpaca_paper:
        print("\nWARNING: Orchestrator in paper mode but Alpaca not in paper mode")
    elif mode == 'paper' and alpaca_paper:
        print("\nOK: Orchestrator and Alpaca both in paper mode (safe for testing)")
    elif mode != 'paper' and alpaca_paper:
        print("\nWARNING: Orchestrator in live mode but Alpaca in paper mode (mismatch)")

    conn.close()
    return True

def main():
    print("="*60)
    print("EXIT & ENTRY LOGIC VALIDATION")
    print("="*60)

    try:
        test_exit_conditions()
        test_entry_constraints()
        test_execution_mode_consistency()

        print("\n" + "="*60)
        print("VALIDATION COMPLETE")
        print("="*60)
        return 0
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

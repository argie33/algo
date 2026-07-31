#!/usr/bin/env python3
"""Comprehensive audit to find all remaining issues in the system."""

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2

from utils.db import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def check_execution_mode():
    """Check if execution_mode config matches orchestrator expectations."""
    section("1. EXECUTION MODE CONFIGURATION")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check DB config
    cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
    row = cur.fetchone()
    db_mode = row[0] if row else "NOT SET"

    print(f"Database execution_mode: {db_mode}")

    # Check recent orchestrator runs for execution_mode errors
    cur.execute("""
        SELECT COUNT(*), 'execution_mode mismatch'
        FROM orchestrator_execution_log
        WHERE halt_reason ILIKE '%execution_mode%mismatch%'
            AND started_at > NOW() - INTERVAL '24 hours'
    """)
    error_count = cur.fetchone()[0]
    if error_count > 0:
        print(f"[ERROR] FOUND: {error_count} runs failed with execution_mode mismatch errors")
    else:
        print("[OK] No recent execution_mode mismatch errors")

    cur.close()
    conn.close()

def check_exit_execution_errors():
    """Check for exit execution errors in Phase 6."""
    section("2. EXIT EXECUTION (PHASE 6) ERRORS")

    conn = get_db_connection()
    cur = conn.cursor()

    # Find runs with degraded/error phase 6
    cur.execute("""
        SELECT run_id, started_at, overall_status, phase_results::text, halt_reason
        FROM orchestrator_execution_log
        WHERE overall_status IN ('degraded', 'error')
           OR phases_errored > 0
        ORDER BY started_at DESC
        LIMIT 5
    """)

    issues_found = False
    for run_id, started_at, overall_status, phases_json, halt_reason in cur.fetchall():
        try:
            phases = json.loads(phases_json) if isinstance(phases_json, str) else phases_json
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[WARN] Failed to parse phases JSON for run {run_id}: {e}")
            phases = []

        for phase in phases:
            if phase.get('phase') == '6':  # Phase 6 is exit_execution
                if phase.get('status') in ['degraded', 'error']:
                    issues_found = True
                    print(f"\n[INFO][INFO]  RUN {run_id}: {overall_status}")
                    print(f"   Started: {started_at}")
                    print(f"   Summary: {phase.get('summary', 'N/A')}")
                    if halt_reason:
                        print(f"   Halt reason: {halt_reason}")

    if not issues_found:
        print("[INFO] No degraded/error exit execution phases found recently")

    cur.close()
    conn.close()

def check_p_l_completeness():
    """Check if closed trades have complete P&L data."""
    section("3. P&L DATA COMPLETENESS (Closed Trades)")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) as total_closed,
               SUM(CASE WHEN profit_loss_dollars IS NULL THEN 1 ELSE 0 END) as null_pl_dollars,
               SUM(CASE WHEN profit_loss_pct IS NULL THEN 1 ELSE 0 END) as null_pl_pct
        FROM algo_trades
        WHERE status = 'closed'
    """)

    total, null_dollars, null_pct = cur.fetchone()
    print(f"Closed trades: {total}")
    print(f"  Missing profit_loss_dollars: {null_dollars or 0}")
    print(f"  Missing profit_loss_pct: {null_pct or 0}")

    if (null_dollars or 0) > 0 or (null_pct or 0) > 0:
        print(f"[INFO][INFO]  FOUND: {(null_dollars or 0) + (null_pct or 0)} closed trades with incomplete P&L data")
    else:
        print("[INFO] All closed trades have complete P&L data")

    cur.close()
    conn.close()

def check_duplicate_entries():
    """Check for duplicate entries from same signal."""
    section("4. DUPLICATE ENTRY PREVENTION (Same Symbol, Same Day)")

    conn = get_db_connection()
    cur = conn.cursor()

    # Find cases where same symbol has multiple open positions from same signal_date
    cur.execute("""
        SELECT symbol, signal_date, COUNT(*) as cnt, ARRAY_AGG(trade_id) as trade_ids
        FROM algo_trades
        WHERE status != 'closed'
        GROUP BY symbol, signal_date
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """)

    duplicates = cur.fetchall()
    if duplicates:
        print(f"[INFO][INFO]  FOUND: {len(duplicates)} cases of multiple entries per symbol per day")
        for symbol, signal_date, cnt, trade_ids in duplicates:
            print(f"   {symbol} on {signal_date}: {cnt} trades ({trade_ids})")
    else:
        print("[INFO] No duplicate entries from same signal detected")

    cur.close()
    conn.close()

def check_loader_health():
    """Check if loaders are stalling or stuck."""
    section("5. LOADER HEALTH (Staleness Check)")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check freshness of key data tables
    cur.execute("""
        SELECT
            'price_daily' as table_name,
            COALESCE((SELECT MAX(date) FROM price_daily), CURRENT_DATE - INTERVAL '30 days')::date as max_date
        UNION ALL
        SELECT
            'technical_data_daily',
            COALESCE((SELECT MAX(date) FROM technical_data_daily), CURRENT_DATE - INTERVAL '30 days')::date
        UNION ALL
        SELECT
            'algo_signals',
            COALESCE((SELECT MAX(signal_date) FROM algo_signals), CURRENT_DATE - INTERVAL '30 days')::date
        ORDER BY max_date DESC
    """)

    now = datetime.now().date()
    for table_name, max_date in cur.fetchall():
        age_days = (now - max_date).days
        status = "[INFO]" if age_days <= 1 else "[INFO][INFO]"
        print(f"{status} {table_name:25} max_date={max_date}  ({age_days}d old)")

    cur.close()
    conn.close()

def check_position_integrity():
    """Check for orphaned trades or positions."""
    section("6. POSITION INTEGRITY")

    conn = get_db_connection()
    cur = conn.cursor()

    # Orphaned trades (closed but position status unclear)
    cur.execute("""
        SELECT COUNT(DISTINCT t.trade_id)
        FROM algo_trades t
        LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
        WHERE t.status = 'closed' AND p.position_id IS NULL
    """)
    orphaned_count = cur.fetchone()[0]
    if orphaned_count > 0:
        print(f"[INFO][INFO]  FOUND: {orphaned_count} closed trades with no associated position")
    else:
        print("[INFO] No orphaned closed trades")

    # Positions with no current price
    cur.execute("""
        SELECT COUNT(*)
        FROM algo_positions
        WHERE status = 'open' AND current_price IS NULL
    """)
    no_price_count = cur.fetchone()[0]
    if no_price_count > 0:
        print(f"[INFO][INFO]  FOUND: {no_price_count} open positions with no current price")
    else:
        print("[INFO] All open positions have current prices")

    cur.close()
    conn.close()

def check_database_schema():
    """Check for schema issues."""
    section("7. DATABASE SCHEMA VALIDATION")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check if orchestrator_execution_log has expected columns
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'orchestrator_execution_log'
    """)
    columns = {row[0] for row in cur.fetchall()}

    required_columns = {'id', 'run_id', 'overall_status', 'phase_results', 'phases_completed', 'phases_errored'}
    missing = required_columns - columns

    if missing:
        print(f"[INFO][INFO]  MISSING COLUMNS in orchestrator_execution_log: {missing}")
    else:
        print("[INFO] orchestrator_execution_log schema is complete")

    # Check if the schema issue (phase_number not existing) is real
    if 'phase_number' in columns:
        print("   [INFO] phase_number column exists (diagnostics script will work)")
    else:
        print("   [INFO] phase_number column does NOT exist (but this is expected - use phase_results JSONB instead)")

    cur.close()
    conn.close()

def check_consecutive_losses_logic():
    """Check if consecutive losses halt logic can work."""
    section("8. CONSECUTIVE LOSSES HALT LOGIC")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check if we have at least some closed trades with profit_loss_pct to test the logic
    cur.execute("""
        SELECT COUNT(*)
        FROM algo_trades
        WHERE status = 'closed' AND profit_loss_pct IS NOT NULL
    """)
    count = cur.fetchone()[0]

    if count > 0:
        # Get the last few closed trades
        cur.execute("""
            SELECT symbol, exit_date, profit_loss_pct
            FROM algo_trades
            WHERE status = 'closed' AND profit_loss_pct IS NOT NULL
            ORDER BY exit_date DESC
            LIMIT 5
        """)
        recent = cur.fetchall()
        print(f"[INFO] We have {count} closed trades with P&L data")
        print("   Recent closes:")
        for symbol, exit_date, pct in recent:
            status_mark = "[INFO]" if float(pct) < 0 else "[INFO]"
            print(f"   {status_mark} {symbol:6} on {exit_date}: {pct:>6.2f}%")
    else:
        print("[INFO][INFO]  No closed trades with P&L data - consecutive losses logic cannot be tested")

    cur.close()
    conn.close()

def check_phase_timeouts():
    """Check if any phases are timing out."""
    section("9. PHASE TIMEOUTS")

    conn = get_db_connection()
    cur = conn.cursor()

    # Check for Phase 7 (signal generation) which was mentioned as having timeout issues
    cur.execute("""
        SELECT COUNT(*) as timeout_count
        FROM orchestrator_execution_log
        WHERE (halt_reason ILIKE '%Phase 7%timeout%'
            OR halt_reason ILIKE '%signal_generation%timeout%'
            OR halt_reason ILIKE '%phase_7%')
        AND started_at > NOW() - INTERVAL '24 hours'
    """)
    phase7_issues = cur.fetchone()[0]

    if phase7_issues > 0:
        print(f"[INFO][INFO]  FOUND: {phase7_issues} Phase 7 (signal generation) timeouts in last 24h")
    else:
        print("[INFO] No Phase 7 timeouts detected")

    cur.close()
    conn.close()

def main():
    print("\n" + "="*70)
    print("  COMPREHENSIVE SYSTEM AUDIT - Finding All Remaining Issues")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    try:
        check_execution_mode()
        check_exit_execution_errors()
        check_p_l_completeness()
        check_duplicate_entries()
        check_loader_health()
        check_position_integrity()
        check_database_schema()
        check_consecutive_losses_logic()
        check_phase_timeouts()

        print("\n" + "="*70)
        print("  AUDIT COMPLETE")
        print("="*70 + "\n")

    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()

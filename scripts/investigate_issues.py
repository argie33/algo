#!/usr/bin/env python3
"""Comprehensive issue investigation - find all bugs and errors."""

import os
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')

from dotenv import load_dotenv
load_dotenv('/c/Users/arger/code/algo/.env.local')

import psycopg2
from datetime import datetime, timedelta
import json

db_host = os.getenv('DB_HOST', 'localhost')
db_port = int(os.getenv('DB_PORT', '5432'))
db_name = os.getenv('DB_NAME', 'algo_trading')
db_user = os.getenv('DB_USER', 'postgres')
db_password = os.getenv('DB_PASSWORD', '')

def get_connection():
    return psycopg2.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )

def print_section(title):
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}\n")

try:
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Get recent orchestrator runs with errors/degradation
    print_section("1. RECENT ORCHESTRATOR RUNS")
    cursor.execute("""
        SELECT run_id, overall_status, started_at, completed_at, halt_reason
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC
        LIMIT 5
    """)

    for run_id, status, started, completed, halt_reason in cursor.fetchall():
        print(f"  {run_id}")
        print(f"    Status: {status}")
        print(f"    Started: {started}")
        if halt_reason:
            print(f"    Halt: {halt_reason[:150]}")
        print()

    # 2. Get latest phase results in detail
    print_section("2. LATEST ORCHESTRATOR PHASES")
    cursor.execute("""
        SELECT phase_results
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    if row and row[0]:
        for phase_num, result in enumerate(row[0], 1):
            status = result.get('status', 'unknown')
            if status in ['degraded', 'error', 'halted']:
                print(f"  PHASE {phase_num}: {status.upper()}")
                if result.get('error'):
                    print(f"    Error: {str(result.get('error'))[:200]}")
                if result.get('message'):
                    print(f"    Message: {str(result.get('message'))[:300]}")
                print()

    # 3. Exit execution errors
    print_section("3. EXIT EXECUTION ERRORS")
    cursor.execute("""
        SELECT symbol, error_type, error_message, created_at
        FROM algo_exit_check_errors
        WHERE created_at > now() - interval '2 hours'
        ORDER BY created_at DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()
    if rows:
        for symbol, error_type, error_msg, created_at in rows:
            print(f"  {symbol}: {error_type}")
            print(f"    {error_msg[:150]}")
            print(f"    Time: {created_at}")
            print()
    else:
        print("  No recent exit errors\n")

    # 4. Data patrol issues
    print_section("4. DATA PATROL ISSUES (Last 2 hours)")
    cursor.execute("""
        SELECT check_type, severity, message, symbol, created_at
        FROM algo_data_patrol
        WHERE created_at > now() - interval '2 hours'
        ORDER BY created_at DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()
    if rows:
        for check_type, severity, message, symbol, created_at in rows:
            print(f"  {symbol or 'SYSTEM'} [{severity}] {check_type}")
            print(f"    {message[:150]}")
            print()
    else:
        print("  No recent data patrol issues\n")

    # 5. Signal rejection log
    print_section("5. SIGNAL REJECTIONS (Last 2 hours)")
    cursor.execute("""
        SELECT symbol, rejection_reason, created_at
        FROM signal_rejection_log
        WHERE created_at > now() - interval '2 hours'
        ORDER BY created_at DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()
    if rows:
        for symbol, rejection_reason, created_at in rows:
            print(f"  {symbol}: {rejection_reason[:100]}")
            print()
    else:
        print("  No recent signal rejections\n")

    # 6. Data loader issues
    print_section("6. DATA LOADER STATUS")
    cursor.execute("""
        SELECT table_name, status, error_message, last_updated
        FROM data_loader_status
        WHERE status != 'success' OR error_message IS NOT NULL
        ORDER BY last_updated DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()
    if rows:
        for table_name, status, error, run_time in rows:
            print(f"  {table_name}: {status}")
            if error:
                print(f"    Error: {error[:150]}")
            print()
    else:
        print("  All loaders healthy\n")

    # 7. Open positions without required data
    print_section("7. POSITION DATA INTEGRITY")
    cursor.execute("""
        SELECT symbol, status, quantity, current_price, stop_loss_price
        FROM algo_positions
        WHERE is_open = TRUE
        ORDER BY updated_at DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()
    print(f"  Open positions: {cursor.rowcount}")
    for symbol, status, quantity, current_price, stop_loss_price in rows:
        if current_price is None or stop_loss_price is None:
            print(f"  {symbol}: MISSING DATA")
            if current_price is None:
                print(f"    current_price = NULL")
            if stop_loss_price is None:
                print(f"    stop_loss_price = NULL")
        print(f"    qty={quantity}, price={current_price}, stop={stop_loss_price}")
    print()

    # 8. Trades in wrong state
    print_section("8. TRADES IN UNEXPECTED STATE")
    cursor.execute("""
        SELECT trade_id, symbol, status, profit_loss_dollars
        FROM algo_trades
        WHERE status NOT IN ('open', 'closed', 'cancelled')
        LIMIT 10
    """)

    rows = cursor.fetchall()
    if rows:
        for trade_id, symbol, status, pnl in rows:
            print(f"  {trade_id} ({symbol}): {status}")
            print(f"    P&L: {pnl}")
            print()
    else:
        print("  All trades in normal state\n")

    # 9. Configuration errors/warnings
    print_section("9. CONFIGURATION CHECK")
    cursor.execute("""
        SELECT key, value FROM algo_config
        WHERE key IN ('execution_mode', 'alpaca_paper_trading', 'max_positions',
                      'min_hold_days', 'base_risk_pct')
        ORDER BY key
    """)

    for key, value in cursor.fetchall():
        print(f"  {key}: {value}")
    print()

    # 10. Transaction abort patterns
    print_section("10. TRANSACTION ABORT PATTERNS")
    cursor.execute("""
        SELECT symbol, COUNT(*) as error_count,
               ARRAY_AGG(DISTINCT error_type) as error_types
        FROM algo_exit_check_errors
        WHERE error_message LIKE '%transaction is aborted%'
           OR error_message LIKE '%InFailedSqlTransaction%'
           OR error_type = 'InFailedSqlTransaction'
        GROUP BY symbol
        ORDER BY error_count DESC
    """)

    rows = cursor.fetchall()
    if rows:
        for symbol, count, error_types in rows:
            print(f"  {symbol}: {count} errors")
            print(f"    Types: {error_types}")
            print()
    else:
        print("  No transaction abort patterns found\n")

    cursor.close()
    conn.close()

    print_section("INVESTIGATION COMPLETE")
    print("Check above for issues that need fixing.\n")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

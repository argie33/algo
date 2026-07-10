#!/usr/bin/env python3
import psycopg2
from datetime import datetime
import sys
import json

try:
    conn = psycopg2.connect(
        host='localhost',
        user='stocks',
        database='stocks',
        port=5432,
        sslmode='disable'
    )
    cur = conn.cursor()

    print("\n" + "="*80)
    print("COMPLETE END-TO-END SYSTEM VERIFICATION - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*80)

    # 1. ORCHESTRATOR EXECUTION
    print("\n1. ORCHESTRATOR EXECUTION STATUS")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(started_at) as latest_run,
        MAX(completed_at) as latest_completion,
        COUNT(*) as total_runs_last_24h
    FROM algo_orchestrator_runs
    WHERE started_at > NOW() - get_interval_sql('24h')
    """)
    result = cur.fetchone()
    if result and result[0]:
        latest = result[0]
        now = datetime.now(latest.tzinfo)
        hours_ago = (now - latest).total_seconds() / 3600
        print(f"[OK] Latest run: {latest} ({hours_ago:.1f} hours ago)")
        print(f"[OK] Latest completion: {result[1]}")
        print(f"[OK] Total runs (24h): {result[2]}")
    else:
        print("[ERROR] NO ORCHESTRATOR RUNS FOUND")

    # 2. LAST RUN PHASE STATUS
    print("\n2. LAST ORCHESTRATOR RUN - PHASE STATUS")
    print("-" * 80)
    cur.execute("""
    SELECT
        overall_status,
        phases_completed,
        phases_halted,
        phases_errored,
        halt_reason,
        phase_results
    FROM orchestrator_execution_log
    ORDER BY created_at DESC
    LIMIT 1
    """)
    result = cur.fetchone()
    if result:
        status = result[0]
        completed = result[1] or 0
        halted = result[2] or 0
        errored = result[3] or 0
        halt_reason = result[4] or ""
        status_icon = "[OK]" if status == "success" else "[ERROR]" if status == "failed" else "[WARN]"
        print(f"{status_icon} Overall Status: {status}")
        print(f"   Phases Completed: {completed}, Halted: {halted}, Errored: {errored}")
        if halt_reason:
            print(f"   Halt Reason: {halt_reason}")

        # Parse phase results
        if result[5]:
            try:
                phases_list = json.loads(result[5])
                for phase in phases_list:
                    phase_name = phase.get('name', '?')
                    phase_num = phase.get('phase', '?')
                    phase_status = phase.get('status', 'unknown')
                    phase_icon = "[OK]" if phase_status == "ok" else "[ERROR]" if phase_status == "failed" else "[WARN]" if phase_status == "degraded" else "[-]" if phase_status == "skipped" else "[?]"
                    print(f"   {phase_icon} Phase {phase_num}: {phase_name} ({phase_status})")
            except json.JSONDecodeError as e:
                print(f"   [ERROR] Failed to parse phase results JSON: {e}")
            except (TypeError, KeyError, AttributeError) as e:
                print(f"   [ERROR] Phase results data structure invalid: {e}")
            except Exception as e:
                print(f"   [ERROR] Unexpected error parsing phase results: {type(e).__name__}: {e}")
    else:
        print("  No execution log found")

    # 3. DATA FRESHNESS - PRICES
    print("\n3. DATA FRESHNESS - PRICE DATA")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(date) as latest_price_date,
        COUNT(DISTINCT symbol) as symbols_with_data,
        NOW() - MAX(date) as age
    FROM price_daily
    WHERE date > NOW() - get_interval_sql('30d')
    """)
    result = cur.fetchone()
    if result and result[0]:
        age_days = result[2].days
        age_hours = int(result[2].total_seconds() / 3600)
        if age_days <= 1:
            status = "[OK]"
        elif age_days <= 3:
            status = "[WARN]"
        else:
            status = "[ERROR]"
        print(f"{status} Latest price date: {result[0]} ({age_days}d {age_hours % 24}h old)")
        print(f"[OK] Symbols with data: {result[1]:,}")
    else:
        print("[ERROR] NO PRICE DATA FOUND")

    # 4. DATA FRESHNESS - TECHNICAL INDICATORS
    print("\n4. DATA FRESHNESS - TECHNICAL INDICATORS")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(date) as latest_technical_date,
        COUNT(DISTINCT symbol) as symbols_with_data,
        NOW() - MAX(date) as age
    FROM technical_data_daily
    WHERE date > NOW() - get_interval_sql('30d')
    """)
    result = cur.fetchone()
    if result and result[0]:
        age_days = result[2].days
        age_hours = int(result[2].total_seconds() / 3600)
        if age_days <= 1:
            status = "[OK]"
        elif age_days <= 3:
            status = "[WARN]"
        else:
            status = "[ERROR]"
        print(f"{status} Latest technical date: {result[0]} ({age_days}d {age_hours % 24}h old)")
        print(f"[OK] Symbols with data: {result[1]:,}")
    else:
        print("[ERROR] NO TECHNICAL DATA FOUND")

    # 5. DATA FRESHNESS - STOCK SCORES
    print("\n5. DATA FRESHNESS - STOCK SCORES")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(updated_at) as latest_scores_date,
        COUNT(*) as total_scores,
        COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as scores_with_values,
        NOW() - MAX(updated_at) as age
    FROM stock_scores
    """)
    result = cur.fetchone()
    if result and result[0]:
        age_days = result[3].days
        age_hours = int(result[3].total_seconds() / 3600)
        if age_days <= 1:
            status = "[OK]"
        elif age_days <= 3:
            status = "[WARN]"
        else:
            status = "[ERROR]"
        print(f"{status} Latest scores: {result[0]} ({age_days}d {age_hours % 24}h old)")
        print(f"[OK] Total scores: {result[1]:,}")
        pct = (100*result[2]//result[1]) if result[1] > 0 else 0
        print(f"[OK] Scores with values: {result[2]:,} ({pct}%)")
    else:
        print("[ERROR] NO STOCK SCORES FOUND")

    # 6. DATA FRESHNESS - TRADING SIGNALS
    print("\n6. DATA FRESHNESS - TRADING SIGNALS (BUY/SELL DAILY)")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(date) as latest_signal_date,
        COUNT(DISTINCT symbol) as symbols_with_signals,
        SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) as buy_signals,
        SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END) as sell_signals,
        NOW() - MAX(date) as age
    FROM buy_sell_daily
    WHERE date > NOW() - get_interval_sql('30d')
    """)
    result = cur.fetchone()
    if result and result[0]:
        age_days = result[4].days
        age_hours = int(result[4].total_seconds() / 3600)
        if age_days <= 1:
            status = "[OK]"
        elif age_days <= 3:
            status = "[WARN]"
        else:
            status = "[ERROR]"
        print(f"{status} Latest signals: {result[0]} ({age_days}d {age_hours % 24}h old)")
        print(f"[OK] Symbols with signals: {result[1]:,}")
        print(f"[OK] BUY signals: {result[2] or 0}")
        print(f"[OK] SELL signals: {result[3] or 0}")
    else:
        print("[ERROR] NO TRADING SIGNALS FOUND")

    # 7. POSITIONS
    print("\n7. PORTFOLIO STATE - OPEN POSITIONS")
    print("-" * 80)
    cur.execute("""
    SELECT
        COUNT(*) as open_positions,
        SUM(quantity) as total_shares,
        SUM(position_value) as total_position_value,
        MAX(updated_at) as updated_at
    FROM algo_positions
    WHERE is_open = true
    """)
    result = cur.fetchone()
    if result[0] and result[0] > 0:
        print(f"[OK] Open positions: {result[0]}")
        print(f"[OK] Total shares: {result[1]}")
        val = result[2]
        if val:
            print(f"[OK] Position value: ${val:,.2f}")
        print(f"[OK] Last updated: {result[3]}")
    else:
        print("[OK] No open positions (system idle or all positions closed)")

    # 8. TRADES
    print("\n8. PORTFOLIO STATE - RECENT TRADES")
    print("-" * 80)
    cur.execute("""
    SELECT
        COUNT(*) as total_trades,
        COUNT(DISTINCT DATE(trade_date)) as trading_days,
        MAX(trade_date) as latest_trade_date,
        SUM(CASE WHEN profit_loss_dollars > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN profit_loss_dollars < 0 THEN 1 ELSE 0 END) as losing_trades,
        ROUND(SUM(profit_loss_dollars)::numeric, 2) as total_pnl
    FROM algo_trades
    WHERE trade_date > NOW()::date - get_interval_sql('30d')
    """)
    result = cur.fetchone()
    if result and result[0] and result[0] > 0:
        print(f"[OK] Total trades (30d): {result[0]}")
        print(f"[OK] Trading days: {result[1]}")
        print(f"[OK] Latest trade: {result[2]}")
        print(f"[OK] Winning trades: {result[3]}")
        print(f"[OK] Losing trades: {result[4]}")
        pnl = result[5]
        if pnl:
            print(f"[OK] Total P&L: ${pnl:,.2f}")
    else:
        print("[OK] No trades in last 30 days")

    # 9. DATA LOADER STATUS
    print("\n9. DATA LOADER STATUS (RECENT)")
    print("-" * 80)
    cur.execute("""
    SELECT
        table_name,
        status,
        COALESCE(row_count, 0) as rows,
        COALESCE(completion_pct, 0) as pct,
        age_days,
        last_updated
    FROM data_loader_status
    ORDER BY last_updated DESC
    LIMIT 20
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            status_icon = "[OK]" if row[1] == "SUCCESS" else "[ERROR]" if row[1] == "FAILED" else "[WARN]"
            print(f"  {status_icon} {row[0]}: {row[1]} ({row[3]:.1f}%, {row[2]:,} rows)")
    else:
        print("  No recent loader runs")

    # 10. PORTFOLIO SNAPSHOTS
    print("\n10. PORTFOLIO SNAPSHOTS (FOR DASHBOARD FRESHNESS)")
    print("-" * 80)
    cur.execute("""
    SELECT
        MAX(snapshot_date) as latest_snapshot,
        COUNT(*) as total_snapshots,
        NOW() - MAX(snapshot_date) as age
    FROM algo_portfolio_snapshots
    """)
    result = cur.fetchone()
    if result and result[0]:
        age_minutes = int(result[2].total_seconds() / 60)
        age_hours = int(result[2].total_seconds() / 3600)
        age_days = result[2].days
        if age_minutes < 5:
            status = "[OK]"
        elif age_hours < 1:
            status = "[OK]"
        elif age_days <= 1:
            status = "[WARN]"
        else:
            status = "[ERROR]"
        print(f"{status} Latest snapshot: {result[0]}")
        print(f"    Age: {age_days}d {age_hours%24}h {age_minutes%60}m")
        print(f"    Total snapshots: {result[1]}")
    else:
        print("[ERROR] NO PORTFOLIO SNAPSHOTS FOUND - Dashboard will fail")

    # 11. ALPACA PAPER TRADING / EXECUTION MODE
    print("\n11. EXECUTION MODE & TRADES")
    print("-" * 80)
    cur.execute("""
    SELECT
        execution_mode,
        COUNT(*) as count
    FROM algo_trades
    WHERE trade_date > NOW()::date - get_interval_sql('7d')
    GROUP BY execution_mode
    """)
    results = cur.fetchall()
    if results:
        for row in results:
            print(f"[OK] Execution mode '{row[0]}': {row[1]} trades (7d)")
    else:
        print("[OK] No trades yet (system warming up)")

    # 12. DASHBOARD REQUIRED FIELDS
    print("\n12. DASHBOARD PANEL READINESS")
    print("-" * 80)

    # Check portfolio panel data
    cur.execute("""
    SELECT
        COUNT(CASE WHEN total_portfolio_value IS NOT NULL THEN 1 END) as has_value,
        COUNT(CASE WHEN total_cash IS NOT NULL THEN 1 END) as has_cash,
        COUNT(*) as total_rows
    FROM algo_portfolio_snapshots
    WHERE snapshot_date > NOW() - get_interval_sql('1d')
    """)
    result = cur.fetchone()
    if result and result[2] > 0:
        print(f"[OK] Portfolio Panel: {result[2]} snapshots")
        print(f"    With value: {result[0]}, With cash: {result[1]}")
    else:
        print("[ERROR] Portfolio Panel: Missing snapshot data")

    # Check positions panel
    cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN symbol IS NOT NULL THEN 1 END) as has_symbol,
        COUNT(CASE WHEN entry_price IS NOT NULL THEN 1 END) as has_price
    FROM algo_positions
    WHERE status = 'OPEN'
    """)
    result = cur.fetchone()
    if result and result[0] > 0:
        print(f"[OK] Positions Panel: {result[0]} open positions")
    else:
        print("[OK] Positions Panel: No data needed")

    # Check signals panel
    cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) as buys
    FROM buy_sell_daily
    WHERE date = CURRENT_DATE
    """)
    result = cur.fetchone()
    if result and result[0] > 0:
        print(f"[OK] Signals Panel: {result[0]} signals ({result[1]} buys)")
    else:
        print("[OK] Signals Panel: No signals today")

    # Check scores panel
    cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as has_score
    FROM stock_scores
    WHERE updated_at > NOW() - get_interval_sql('1d')
    """)
    result = cur.fetchone()
    if result and result[0] > 0:
        print(f"[OK] Scores Panel: {result[0]} scores")
    else:
        print("[WARN] Scores Panel: Missing recent scores")

    print("\n" + "="*80)
    print("END OF VERIFICATION REPORT")
    print("="*80)

    cur.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

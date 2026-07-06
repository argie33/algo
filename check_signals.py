#!/usr/bin/env python3
"""Check if signals are being generated"""
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta, timezone

with DatabaseContext('read') as cur:
    # Check buy_sell_daily schema first
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='buy_sell_daily'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    print("buy_sell_daily columns:")
    for c in cols:
        print(f"  {c}")

    # Check most recent BUY signals generated (use available columns)
    cur.execute("""
        SELECT date, COUNT(*) as buy_count
        FROM buy_sell_daily
        WHERE signal = 'BUY'
        GROUP BY date
        ORDER BY date DESC
        LIMIT 10
    """)
    buy_signals = cur.fetchall()
    print("\nBUY Signals by Date (last 10):")
    for row in buy_signals:
        print(f"  {row}")

    # Check most recent ALL signals
    cur.execute("""
        SELECT date, signal, COUNT(*) as count
        FROM buy_sell_daily
        GROUP BY date, signal
        ORDER BY date DESC, signal DESC
        LIMIT 20
    """)
    all_signals = cur.fetchall()
    print("\nAll Signals by Date and Type (last 20):")
    for row in all_signals:
        print(f"  {row}")

    # Check algo_signals table (Phase 7 output)
    cur.execute("""
        SELECT generation_date, signal_type, COUNT(*) as count
        FROM algo_signals
        GROUP BY generation_date, signal_type
        ORDER BY generation_date DESC
        LIMIT 10
    """)
    algo_sigs = cur.fetchall()
    print("\nAlgo Signals (Phase 7 output) - last 10:")
    for row in algo_sigs:
        print(f"  {row}")

    # Check for Phase 7 execution logs
    cur.execute("""
        SELECT timestamp, action, details
        FROM orchestrator_execution_log
        WHERE action LIKE '%phase_7%' OR action LIKE '%signal%'
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    phase7_logs = cur.fetchall()
    print("\nOrchestrator Phase 7/Signal Logs (last 5):")
    for row in phase7_logs:
        print(f"  {row}")

    # Check for buy_sell_daily ETF signals
    cur.execute("""
        SELECT date, signal, COUNT(*) as count
        FROM buy_sell_daily_etf
        GROUP BY date, signal
        ORDER BY date DESC
        LIMIT 10
    """)
    etf_sigs = cur.fetchall()
    print("\nBUY_SELL_DAILY_ETF Signals (last 10):")
    for row in etf_sigs:
        print(f"  {row}")

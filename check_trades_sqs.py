#!/usr/bin/env python3
"""Check latest trades for signal_quality_score issues."""

import psycopg2
import os
from datetime import datetime, date

try:
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cur = conn.cursor()

    # Get trades from last 3 days
    cur.execute("""
        SELECT
            id, symbol, entry_date, signal_quality_score,
            trend_template_score, entry_price, entry_quantity, status
        FROM algo_trades
        WHERE entry_date >= CURRENT_DATE - INTERVAL '3 days'
        ORDER BY entry_date DESC, id DESC
        LIMIT 20
    """)

    print("=" * 120)
    print("LATEST TRADES & SIGNAL QUALITY SCORES")
    print("=" * 120)

    rows = cur.fetchall()
    sqs_null_count = 0
    sqs_notnull_count = 0

    for row in rows:
        trade_id, symbol, entry_date, sqs, trend, entry_px, qty, status = row
        sqs_str = f"{sqs:.0f}" if sqs is not None else "NULL"
        trend_str = f"{trend:.1f}" if trend is not None else "NULL"

        if sqs is None:
            sqs_null_count += 1
            flag = "WARN"
        else:
            sqs_notnull_count += 1
            flag = "OK"

        print(f"{flag} {symbol:5} {entry_date} sqs={sqs_str:3} trend={trend_str:4} "
              f"entry=${entry_px:7.2f} qty={qty:5} status={status}")

    print("=" * 120)
    print(f"Summary: {sqs_notnull_count} trades with SQS, {sqs_null_count} trades with NULL SQS")
    print("=" * 120)

    # Check algo_signals table structure
    print("\nChecking algo_signals table columns...")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='algo_signals'")
    cols = [row[0] for row in cur.fetchall()]
    print(f"Columns: {cols}")

    # Check if Phase 7 is computing signal_quality_score
    print("\nChecking Phase 7 signal data...")
    try:
        cur.execute("""
            SELECT COUNT(*), signal_date
            FROM algo_signals
            GROUP BY signal_date
            ORDER BY signal_date DESC
            LIMIT 10
        """)
        sig_rows = cur.fetchall()
        if sig_rows:
            print("Signals by date:")
            for count, sig_date in sig_rows:
                print(f"  {sig_date}: {count} signals")
        else:
            print("  No Phase 7 signals found")
    except Exception as e:
        print(f"  Error checking signals: {e}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

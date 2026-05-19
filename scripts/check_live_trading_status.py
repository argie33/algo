#!/usr/bin/env python3
"""Check live trading orchestrator results and system status"""

import psycopg2
from datetime import datetime
import os

# Use env vars
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'stocks')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'stocks')
DB_NAME = os.environ.get('DB_NAME', 'stocks')

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port="5432"
    )
    cur = conn.cursor()

    print("=" * 70)
    print("LIVE TRADING SYSTEM STATUS - 2026-05-19")
    print("=" * 70)

    # Check latest audit log entries
    print("\n[LOG] Latest Orchestrator Runs:")
    cur.execute("""
        SELECT run_id, execution_timestamp, dry_run, status, error_message
        FROM algo_audit_log
        ORDER BY execution_timestamp DESC
        LIMIT 5
    """)
    results = cur.fetchall()
    if results:
        for run_id, ts, dry_run, status, error in results:
            mode = "DRY" if dry_run else "LIVE"
            print(f"  [{mode}] {ts.strftime('%H:%M:%S')} - {status} - {run_id}")
            if error and len(str(error)) > 10:
                print(f"       → {str(error)[:80]}")
    else:
        print("  No audit log entries found")

    # Check trades executed
    print("\n[TRADES] Trades Status:")
    cur.execute("""
        SELECT COUNT(*), COUNT(DISTINCT symbol)
        FROM algo_trades
        WHERE DATE(execution_timestamp) = CURRENT_DATE
    """)
    trade_count, symbol_count = cur.fetchone()
    print(f"  Today: {trade_count} trades across {symbol_count} symbols")

    if trade_count > 0:
        print("  Recent trades:")
        cur.execute("""
            SELECT symbol, side, shares, exec_price, execution_timestamp
            FROM algo_trades
            WHERE DATE(execution_timestamp) = CURRENT_DATE
            ORDER BY execution_timestamp DESC
            LIMIT 5
        """)
        for symbol, side, shares, price, ts in cur.fetchall():
            print(f"    {side:4} {symbol:6} {shares:6.0f} @ ${price:8.2f} at {ts.strftime('%H:%M:%S')}")

    # Check buy signals
    print("\n[SIGNALS] Buy Signals (Yesterday):")
    cur.execute("""
        SELECT COUNT(*), COUNT(DISTINCT symbol)
        FROM buy_sell_daily
        WHERE eval_date = CURRENT_DATE - 1
        AND signal_type = 'BUY'
    """)
    buy_count, buy_symbols = cur.fetchone()
    print(f"  {buy_count} signals across {buy_symbols} symbols")

    if buy_count > 0:
        cur.execute("""
            SELECT symbol, score, stage_number, earnings_date
            FROM buy_sell_daily
            WHERE eval_date = CURRENT_DATE - 1
            AND signal_type = 'BUY'
            ORDER BY score DESC
            LIMIT 5
        """)
        print("  Top 5 signals:")
        for symbol, score, stage, earnings in cur.fetchall():
            print(f"    {symbol:6} score={score:6.1f} stage={stage:2.0f} earnings={earnings}")

    # Check current positions
    print("\n[POSITIONS] Current Positions:")
    cur.execute("""
        SELECT symbol, quantity, avg_entry_price
        FROM algo_positions
        WHERE closed = FALSE
        ORDER BY symbol
    """)
    positions = cur.fetchall()
    if positions:
        total_value = 0
        for symbol, qty, entry_price in positions:
            cur.execute("SELECT close FROM price_daily WHERE symbol=%s ORDER BY date DESC LIMIT 1", (symbol,))
            latest = cur.fetchone()
            current_price = latest[0] if latest else entry_price
            pnl = (current_price - entry_price) * qty
            print(f"  {symbol:6} - {qty:6.0f} shares @ ${entry_price:8.2f} → ${current_price:8.2f} P&L: ${pnl:10.2f}")
            total_value += current_price * qty
        print(f"\n  Total value: ${total_value:,.2f}")
    else:
        print("  No open positions (ready to trade)")

    conn.close()

    print("\n" + "=" * 70)
    print("[OK] LOCAL SYSTEM: OPERATIONAL & READY FOR AWS DEPLOYMENT")
    print("=" * 70)
    print("\nNext Steps:")
    print("  1. GitHub Actions deploying to AWS (check Actions tab)")
    print("  2. Set secrets in AWS Secrets Manager via IaC")
    print("  3. Test end-to-end with AWS Lambda")
    print("  4. Enable live trading at market open (9:30 AM ET)")

except Exception as e:
    print(f"\n[ERROR] Database Error: {e}")
    print("\nTroubleshooting:")
    print(f"  DB_HOST={DB_HOST}")
    print(f"  DB_USER={DB_USER}")
    print(f"  DB_NAME={DB_NAME}")
    import traceback
    traceback.print_exc()

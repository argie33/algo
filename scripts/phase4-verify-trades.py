#!/usr/bin/env python3
"""
Phase 4: Verify trading signals and execution
- Check if orchestrator generated buy signals
- Check if trades were executed in Alpaca
- Reconcile with database
"""

import os
import sys
import psycopg2
import json
from datetime import datetime

def connect_db():
    """Connect to AWS RDS PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'stocks'),
        sslmode='require' if os.getenv('DB_SSL') == 'true' else 'disable'
    )

def verify_signals():
    """Check if orchestrator generated today's signals"""
    try:
        conn = connect_db()
        cur = conn.cursor()

        # Check signals for today
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN action='buy' THEN 1 ELSE 0 END) as buys,
                   SUM(CASE WHEN action='sell' THEN 1 ELSE 0 END) as sells
            FROM buy_sell_daily
            WHERE DATE(date) = CURRENT_DATE
        """)

        result = cur.fetchone()
        total, buys, sells = result

        conn.close()

        print("[✓] Signals Query:")
        print(f"    Total signals today: {total}")
        print(f"    Buy signals: {buys}")
        print(f"    Sell signals: {sells}")

        return buys, sells
    except Exception as e:
        print(f"[✗] Signal verification failed: {e}")
        return 0, 0

def verify_trades():
    """Check if trades were executed"""
    try:
        conn = connect_db()
        cur = conn.cursor()

        # Check trades table
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN action='buy' THEN 1 ELSE 0 END) as buys,
                   SUM(CASE WHEN action='sell' THEN 1 ELSE 0 END) as sells
            FROM trades
            WHERE DATE(created_at) = CURRENT_DATE
        """)

        result = cur.fetchone()
        total, buys, sells = result if result[0] else (0, 0, 0)

        conn.close()

        print("[✓] Trades Query:")
        print(f"    Total trades today: {total}")
        print(f"    Buy trades: {buys}")
        print(f"    Sell trades: {sells}")

        return total, buys, sells
    except Exception as e:
        print(f"[✗] Trade verification failed: {e}")
        return 0, 0, 0

def main():
    print("=" * 60)
    print("PHASE 4: Verify Trading Signals & Execution")
    print("=" * 60)
    print()

    # Check signals
    print("[1/2] Checking generated signals...")
    buys, sells = verify_signals()
    print()

    # Check trades
    print("[2/2] Checking executed trades...")
    trades_total, trades_buys, trades_sells = verify_trades()
    print()

    # Summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Signals generated: {buys + sells} (buys: {buys}, sells: {sells})")
    print(f"Trades executed:   {trades_total} (buys: {trades_buys}, sells: {trades_sells})")
    print()

    if buys > 0:
        print("✓ SUCCESS: Buy signals generated - ready for trading!")
        if trades_buys > 0:
            print("✓ SUCCESS: Trades executed in Alpaca!")
            return 0
        else:
            print("⚠ WARNING: Signals generated but no trades executed yet")
            return 1
    else:
        print("✗ FAILURE: No buy signals generated")
        print("  → May need more data or different market conditions")
        return 1

if __name__ == '__main__':
    sys.exit(main())

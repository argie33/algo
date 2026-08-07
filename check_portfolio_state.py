#!/usr/bin/env python3
"""Check portfolio state to understand Phase 8 execution."""

import os
import sys
from datetime import date

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    from utils.db.connection import get_db_connection

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Check open positions
        print("=" * 80)
        print("PORTFOLIO STATE - OPEN POSITIONS")
        print("=" * 80)
        cur.execute("""
            SELECT symbol, entry_price, quantity, entry_date, is_open
            FROM algo_positions
            WHERE is_open = true
            ORDER BY entry_date DESC
            LIMIT 15
        """)
        rows = cur.fetchall()
        print(f"Open positions: {len(rows)}")
        for symbol, entry_price, qty, entry_date, is_open in rows:
            print(f"  {symbol}: {qty} @ ${entry_price:.2f} (entered {entry_date})")

        # Check position limit
        print("\n" + "=" * 80)
        print("POSITION LIMIT CHECK")
        print("=" * 80)
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE is_open = true")
        open_count = cur.fetchone()[0]
        limit = 15
        print(f"Open positions: {open_count}/{limit}")
        if open_count >= limit:
            print(f"❌ AT LIMIT - Phase 8 blocked from new entries")
        else:
            print(f"✅ Can add {limit - open_count} more positions")

        # Check recent trades
        print("\n" + "=" * 80)
        print("RECENT TRADE ACTIVITY")
        print("=" * 80)
        cur.execute("""
            SELECT trade_id, symbol, entry_date, status, entry_quantity
            FROM algo_trades
            WHERE entry_date >= CURRENT_DATE - interval '5 days'
            ORDER BY entry_date DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
        print(f"Trades (last 5 days): {len(rows)}")
        for trade_id, symbol, entry_date, status, qty in rows:
            print(f"  {trade_id}: {symbol} {qty}sh on {entry_date} (status={status})")

        # Check for duplicate prevention
        print("\n" + "=" * 80)
        print("DUPLICATE/IDEMPOTENT TRADES")
        print("=" * 80)
        cur.execute("""
            SELECT COUNT(*) as voided_dupes
            FROM algo_trades
            WHERE status = 'voided_duplicate'
              AND entry_date >= CURRENT_DATE - 1
        """)
        voided = cur.fetchone()[0]
        print(f"Voided duplicate trades today: {voided}")

        # Check concentration
        print("\n" + "=" * 80)
        print("CONCENTRATION ANALYSIS")
        print("=" * 80)
        cur.execute("""
            SELECT ROUND(SUM(quantity * entry_price)::numeric, 2) as total_exposure
            FROM algo_positions
            WHERE is_open = true
        """)
        total_exposure = cur.fetchone()[0] or 0
        print(f"Total portfolio exposure (open positions): ${total_exposure:,.2f}")

        # Get portfolio value
        cur.execute("""
            SELECT ROUND(portfolio_value::numeric, 2)
            FROM equity_curve_daily
            ORDER BY date DESC
            LIMIT 1
        """)
        result = cur.fetchone()
        portfolio_value = result[0] if result else 71891.52
        concentration_pct = (total_exposure / portfolio_value * 100) if portfolio_value else 0
        print(f"Portfolio value: ${portfolio_value:,.2f}")
        print(f"Concentration: {concentration_pct:.1f}%")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

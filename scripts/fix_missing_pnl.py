#!/usr/bin/env python3
"""Fix missing P&L values for closed trades."""

from utils.db import DatabaseContext

def main():
    """Fix NULL P&L values."""
    with DatabaseContext("write") as cur:
        print("\n" + "="*80)
        print("FIXING NULL PROFIT_LOSS_PCT IN CLOSED TRADES")
        print("="*80 + "\n")

        # Find all closed trades with NULL exit_price
        cur.execute("""
            SELECT trade_id, symbol, entry_price, entry_date, exit_date
            FROM algo_trades
            WHERE status = 'closed' AND exit_price IS NULL
            ORDER BY exit_date DESC
        """)

        trades_to_fix = cur.fetchall()

        if not trades_to_fix:
            print("✓ No trades with NULL exit_price found!\n")
            return

        print(f"Found {len(trades_to_fix)} closed trades with missing exit prices:\n")

        for trade in trades_to_fix:
            trade_id, symbol, entry_price, entry_date, exit_date = trade
            print(f"Trade: {trade_id} ({symbol})")
            print(f"  Entry: ${entry_price:.4f} on {entry_date}")
            print(f"  Closed: {exit_date} (NO EXIT PRICE)")

        print("\n" + "="*80)
        print("SOLUTION:")
        print("="*80)
        print("""
These trades are missing exit prices. Options:

1. DELETE TEST TRADES: If these are demo/test trades (DEMO-, TEST-, etc.),
   they should be deleted from the database.

2. MARK AS INCOMPLETE: If these are real trades, update them with actual
   exit prices from broker history.

3. UPDATE CIRCUIT BREAKER LOGIC: Make circuit breaker checks skip NULL P&L
   instead of failing.

For now, let's check if these are test trades...
        """)

        # Check trade ID patterns
        test_trades = [t for t in trades_to_fix if any(
            x in t[0] for x in ['TEST', 'DEMO', 'PROD']
        )]

        print(f"\nTest/Demo trades: {len(test_trades)}")
        print(f"Unknown trades: {len(trades_to_fix) - len(test_trades)}\n")

        if test_trades:
            print("RECOMMENDATION: Delete test trades to allow Phase 2 to proceed")
            print("Run this command to delete them:\n")
            print("  python -m algo.infrastructure.db_cleanup --delete-test-trades")

if __name__ == "__main__":
    main()

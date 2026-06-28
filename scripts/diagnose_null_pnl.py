#!/usr/bin/env python3
"""Diagnose NULL profit_loss_pct in trades."""

from utils.db import DatabaseContext

def main():
    """Check for NULL P&L values."""
    with DatabaseContext("read") as cur:
        print("\n" + "="*80)
        print("DIAGNOSING NULL PROFIT_LOSS_PCT IN ALGO_TRADES")
        print("="*80 + "\n")

        # Check for closed trades with NULL P&L
        cur.execute("""
            SELECT COUNT(*) as null_pnl_count,
                   COUNT(*) FILTER (WHERE status = 'closed') as closed_count,
                   COUNT(*) FILTER (WHERE status = 'closed' AND profit_loss_pct IS NULL) as closed_null_pnl
            FROM algo_trades
        """)

        row = cur.fetchone()
        total = row[0]
        closed = row[1]
        closed_null = row[2]

        print(f"Total trades: {total}")
        print(f"Closed trades: {closed}")
        print(f"Closed trades with NULL profit_loss_pct: {closed_null}\n")

        if closed_null > 0:
            print(f"CRITICAL: {closed_null} closed trades have NULL P&L values!\n")

            # Show examples
            print("Examples of trades with NULL P&L:")
            cur.execute("""
                SELECT trade_id, symbol, status, entry_price, exit_price,
                       profit_loss_dollars, profit_loss_pct, exit_date
                FROM algo_trades
                WHERE status = 'closed' AND profit_loss_pct IS NULL
                LIMIT 10
            """)

            for row in cur.fetchall():
                trade_id, symbol, status, entry_price, exit_price, pnl_dollars, pnl_pct, exit_date = row
                print(f"\nTrade: {trade_id} ({symbol})")
                print(f"  Status: {status}")
                print(f"  Entry: ${entry_price} -> Exit: ${exit_price}")
                print(f"  P&L: ${pnl_dollars} ({pnl_pct})")
                print(f"  Exit Date: {exit_date}")

        else:
            print("✓ No NULL P&L values found - trades are complete!\n")

if __name__ == "__main__":
    main()

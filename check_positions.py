#!/usr/bin/env python3
from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute("""
    SELECT symbol, quantity, current_price, avg_entry_price, stop_loss_price,
           unrealized_pnl, unrealized_pnl_pct, status, days_since_entry
    FROM algo_positions
    WHERE status = 'open' AND quantity > 0
    ORDER BY unrealized_pnl ASC
    """)

    rows = cur.fetchall()
    print(f"Total open positions: {len(rows)}\n")
    print(f"{'Symbol':<8} {'Qty':<6} {'Entry':<8} {'Stop':<8} {'P&L %':<8} {'Days':<6}")
    print("-" * 50)

    total_pnl = 0
    for row in rows:
        symbol, qty, price, entry, stop, pnl, pnl_pct, status, days = row
        total_pnl += pnl if pnl else 0
        print(f"{symbol:<8} {qty:<6.0f} ${entry:<7.2f} ${stop:<7.2f} {pnl_pct:<7.1f}% {days:<6.0f}")

    print("-" * 50)
    print(f"Total P&L: ${total_pnl:.2f}")

    # Check risk calculation
    cur.execute("SELECT SUM(unrealized_pnl) FROM algo_positions WHERE status='open'")
    total_pnl_db = cur.fetchone()[0]
    print(f"DB Total P&L: ${total_pnl_db:.2f}" if total_pnl_db else "DB Total P&L: $0.00")

#!/usr/bin/env python3
from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    # Get closed trades from the last 30 trades to understand why win rate is 7.7%
    cur.execute('''
    SELECT
        symbol,
        entry_date,
        exit_date,
        entry_price,
        exit_price,
        quantity,
        profit_loss_pct,
        exit_reason,
        status
    FROM algo_trades
    WHERE status = 'closed'
      AND exit_date IS NOT NULL
      AND exit_r_multiple IS NOT NULL
      AND trade_id NOT ILIKE 'EXT-%'
    ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
    LIMIT 30
    ''')

    trades = cur.fetchall()
    wins = 0
    losses = 0

    print("=== LAST 30 CLOSED STRATEGIC TRADES ===")
    print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'P&L%':<8} {'Reason':<25}")
    print("-" * 80)

    for trade in trades:
        symbol, entry_date, exit_date, entry_price, exit_price, qty, pnl_pct, reason, status = trade

        if pnl_pct is None:
            continue

        pnl_pct = float(pnl_pct)
        if pnl_pct > 0:
            wins += 1
            status_str = "WIN "
        elif pnl_pct < 0:
            losses += 1
            status_str = "LOSS"
        else:
            status_str = "FLAT"

        reason_short = reason[:20] if reason else "unknown"
        print(f"{symbol:<8} {str(entry_date):<12} {str(exit_date):<12} {pnl_pct:>6.1f}% {reason_short:<25} {status_str}")

    total = wins + losses
    if total > 0:
        wr = 100 * wins / total
        print("-" * 80)
        print(f"Wins: {wins}/{total} = {wr:.1f}% win rate")
        print(f"Losses: {losses}/{total} = {100*losses/total:.1f}% loss rate")

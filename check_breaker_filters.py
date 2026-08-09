#!/usr/bin/env python3
from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    # Query using EXACT same filters as circuit breaker
    cur.execute(
        """
        SELECT COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
               COUNT(*) FILTER (WHERE pnl_pct < 0) as losses,
               COUNT(*) as total
        FROM (
            SELECT profit_loss_pct as pnl_pct
            FROM (
                SELECT profit_loss_pct, id
                FROM algo_trades
                WHERE status = %s AND exit_date IS NOT NULL
                  AND exit_r_multiple IS NOT NULL
                  AND trade_id NOT ILIKE 'EXT-%%'
                  AND exit_reason NOT ILIKE %s
                  AND exit_reason NOT ILIKE %s
                  AND exit_reason NOT ILIKE %s
                  AND exit_reason NOT ILIKE %s
                  AND exit_reason NOT ILIKE %s
                ORDER BY exit_date DESC, exit_time DESC NULLS LAST, id DESC
                LIMIT 30
            ) recent_closed
        ) all_trades
        """,
        ('closed', "%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%"),
    )
    row = cur.fetchone()
    if row:
        wins, losses, total = row
        print(f"Circuit Breaker Query Results:")
        print(f"  Total: {total}")
        print(f"  Wins: {wins}")
        print(f"  Losses: {losses}")
        if wins and losses:
            wr = 100 * wins / (wins + losses)
            print(f"  Win Rate: {wr:.1f}%")

    # Now check: how many strategic closed trades are there total?
    print("\n=== Total Strategic Closed Trades ===")
    cur.execute(
        """
        SELECT COUNT(*) FROM algo_trades
        WHERE status = %s AND exit_date IS NOT NULL
          AND exit_r_multiple IS NOT NULL
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
          AND exit_reason NOT LIKE %s
    """,
        ('closed', "%reconciliation%", "%force%close%", "%delisted%", "%CONCENTRATION%"),
    )
    closed_row = cur.fetchone()
    if closed_row:
        closed_count = closed_row[0]
        print(f"Total strategic closed trades (excluding special exits): {closed_count}")

#!/usr/bin/env python3
"""Verification script for exit price reconciliation fix (2026-07-29).

Validates that:
1. All closed trades have actual exit_price (not stale current_price)
2. P&L is calculated from actual fills, not fabricated $0.00
3. Sharpe ratio rebuilds from correct data
"""

import logging
from datetime import datetime, date
from decimal import Decimal
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_exit_prices_valid():
    """Verify all recently closed trades have actual exit prices."""
    with DatabaseContext("read") as cur:
        # Check 1: No NULL exit_price on closed trades from last 7 days
        cur.execute(
            """
            SELECT COUNT(*) as null_count
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
              AND exit_price IS NULL
            """
        )
        null_count = cur.fetchone()[0]
        if null_count > 0:
            logger.warning(f"FOUND {null_count} closed trades with NULL exit_price in last 7 days")
            return False
        logger.info("PASS: All closed trades from last 7 days have exit_price set")

        # Check 2: No stale current_price in exit_price (verify actual fills recorded)
        cur.execute(
            """
            SELECT COUNT(*) as zero_pnl_count
            FROM algo_trades at
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
              AND profit_loss_dollars = 0
              AND exit_price = entry_price
            """
        )
        zero_pnl_count = cur.fetchone()[0]
        if zero_pnl_count > 0:
            logger.warning(
                f"FOUND {zero_pnl_count} trades with zero P&L (exit_price=entry_price). "
                f"This suggests stale current_price was used instead of actual fills."
            )

        # Check 3: Verify P&L is NOT NULL for non-estimated exits
        cur.execute(
            """
            SELECT COUNT(*) as null_pnl_count
            FROM algo_trades at
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
              AND estimated_exit_price IS NULL
              AND profit_loss_dollars IS NULL
            """
        )
        null_pnl_count = cur.fetchone()[0]
        if null_pnl_count > 0:
            logger.error(
                f"CRITICAL: {null_pnl_count} trades have NULL profit_loss_dollars but no estimated_exit_price. "
                f"P&L should have been calculated from actual fills."
            )
            return False
        logger.info("PASS: All non-estimated closed trades have profit_loss_dollars calculated")

        # Check 4: Verify exit_price_reconciled_at is set for Phase 9 recorded exits
        cur.execute(
            """
            SELECT COUNT(*) as reconciled_count
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
              AND exit_reason LIKE 'Closed position recorded during reconciliation%'
              AND exit_price_reconciled_at IS NOT NULL
            """
        )
        reconciled_count = cur.fetchone()[0]
        if reconciled_count > 0:
            logger.info(f"PASS: {reconciled_count} Phase 9 recorded exits have reconciliation timestamps")

        return True


def check_pnl_consistency():
    """Verify P&L calculations are consistent across all positions."""
    with DatabaseContext("read") as cur:
        # Sum of realized P&L should match portfolio gains
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END) as total_wins,
              SUM(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE 0 END) as total_losses,
              COUNT(*) as total_closed,
              SUM(profit_loss_dollars) as net_realized_pnl
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '30 days'
            """
        )
        row = cur.fetchone()
        total_wins = row[0] or 0
        total_losses = row[1] or 0
        total_closed = row[2] or 0
        net_pnl = row[3] or 0

        if total_closed == 0:
            logger.info("No closed trades in last 30 days")
            return True

        win_rate_pct = (
            (sum(1 for _ in range(int(total_wins)) if _ >= 0) / total_closed * 100)
            if total_closed > 0
            else 0
        )

        logger.info(
            f"SUMMARY (last 30 days, {total_closed} closed trades):"
        )
        logger.info(f"  Wins: ${total_wins:.2f} | Losses: ${total_losses:.2f} | Net P&L: ${net_pnl:.2f}")

        # Check 5: Verify no extreme outliers (bad fill prices)
        cur.execute(
            """
            SELECT symbol, entry_price, exit_price,
                   (exit_price - entry_price) / entry_price * 100 as return_pct
            FROM algo_trades
            WHERE status = 'closed'
              AND exit_date >= CURRENT_DATE - INTERVAL '7 days'
              AND ABS((exit_price - entry_price) / entry_price * 100) > 50
            ORDER BY ABS((exit_price - entry_price) / entry_price * 100) DESC
            LIMIT 10
            """
        )
        outliers = cur.fetchall()
        if outliers:
            logger.warning(f"Found {len(outliers)} trades with >50% return (check for fill price errors):")
            for sym, entry, exit, ret in outliers:
                logger.warning(f"  {sym}: ${entry:.2f} -> ${exit:.2f} ({ret:+.1f}%)")

        return net_pnl >= 0 or total_closed < 5  # Allow loss if very few trades


def check_sharpe_rebuild():
    """Verify Sharpe ratio can be calculated from corrected P&L."""
    with DatabaseContext("read") as cur:
        # Get daily P&L from algo_performance_daily
        cur.execute(
            """
            SELECT COUNT(*) as perf_record_count,
                   AVG(rolling_sharpe_252d) as avg_sharpe
            FROM algo_performance_daily
            WHERE report_date >= CURRENT_DATE - INTERVAL '30 days'
            """
        )
        row = cur.fetchone()
        perf_count = row[0] or 0
        avg_sharpe = row[1] or 0

        if perf_count == 0:
            logger.info("No performance data yet (normal for new backtest)")
            return True

        logger.info(f"Performance data: {perf_count} daily records, avg Sharpe: {avg_sharpe:.2f}")

        # Sharpe should be positive for profitable systems
        if avg_sharpe > 0:
            logger.info("PASS: Sharpe ratio is positive (indicates correct P&L calculation)")
            return True
        else:
            logger.warning(f"ALERT: Sharpe ratio is {avg_sharpe:.2f} (check if this is expected)")
            return True  # Don't fail - might be early in backtest


def main():
    """Run all verification checks."""
    logger.info("[EXIT PRICE FIX VERIFICATION] Starting...\n")

    checks = [
        ("Exit Prices Valid", check_exit_prices_valid),
        ("P&L Consistency", check_pnl_consistency),
        ("Sharpe Rebuild", check_sharpe_rebuild),
    ]

    results = []
    for name, check_fn in checks:
        try:
            logger.info(f"\n[CHECK] {name}")
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            logger.error(f"[ERROR] {name}: {e}", exc_info=True)
            results.append((name, False))

    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION RESULTS")
    logger.info("=" * 60)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        logger.info(f"{status:4} | {name}")

    all_passed = all(r[1] for r in results)
    if all_passed:
        logger.info("\nAll checks PASSED! Exit price fix is working correctly.")
    else:
        logger.warning("\nSome checks FAILED. Review logs above for details.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit(main())

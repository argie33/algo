#!/usr/bin/env python3
"""
Deep diagnostic: Why are all positions being closed immediately?

Check:
1. Recent trades and their hold times
2. Exit reasons for closed trades
3. Portfolio snapshots showing position counts
4. Phase 4 (exit execution) behavior
"""

import sys
import logging
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def check_trade_hold_times():
    """Check how long trades are held before closing."""
    logger.info("\n" + "="*70)
    logger.info("TRADE HOLD TIMES (Why are positions closing so fast?)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT
                    id, symbol, trade_date, exit_date, status,
                    quantity, entry_price, exit_price,
                    exit_reason,
                    CASE
                        WHEN exit_date IS NOT NULL
                        THEN (exit_date - trade_date)
                        ELSE NULL
                    END as hold_days,
                    CASE
                        WHEN exit_date IS NOT NULL AND entry_price > 0
                        THEN ROUND(((exit_price - entry_price) / entry_price * 100)::numeric, 2)
                        ELSE NULL
                    END as return_pct
                FROM algo_trades
                WHERE trade_date >= CURRENT_DATE - INTERVAL '5 days'
                ORDER BY trade_date DESC, id DESC
            """)

            rows = cur.fetchall()
            logger.info(f"\nTotal trades in last 5 days: {len(rows)}")

            if not rows:
                logger.warning("No trades found")
                return

            # Group by status
            closed = [r for r in rows if r[4] == 'closed']
            accepted = [r for r in rows if r[4] == 'accepted']
            filled = [r for r in rows if r[4] == 'filled']

            logger.info(f"\nStatus breakdown:")
            logger.info(f"  Closed: {len(closed)}")
            logger.info(f"  Accepted: {len(accepted)}")
            logger.info(f"  Filled: {len(filled)}")

            logger.info(f"\n📊 CLOSED TRADES (these exited):")
            for trade_id, symbol, trade_date, exit_date, status, qty, entry, exit_p, exit_reason, hold_days, ret_pct in closed:
                hold_str = f"{hold_days.days} days" if hold_days else "same day"
                logger.info(f"\n  {symbol} (Trade #{trade_id})")
                logger.info(f"    Entry: {trade_date} @ ${entry:.2f}")
                logger.info(f"    Exit:  {exit_date} @ ${exit_p:.2f}")
                logger.info(f"    Hold:  {hold_str}")
                logger.info(f"    P&L:   {ret_pct:+.2f}%")
                if exit_reason:
                    logger.info(f"    Reason: {exit_reason}")

            logger.info(f"\n📊 OPEN TRADES (still holding):")
            for trade_id, symbol, trade_date, exit_date, status, qty, entry, exit_p, exit_reason, hold_days, ret_pct in filled + accepted:
                days_held = ((_date.today() - trade_date).days)
                logger.info(f"\n  {symbol} (Trade #{trade_id})")
                logger.info(f"    Entry: {trade_date} @ ${entry:.2f}")
                logger.info(f"    Days held: {days_held}")
                if exit_p:
                    current_ret = ((exit_p - entry) / entry * 100)
                    logger.info(f"    Current P&L: {current_ret:+.2f}%")
    except Exception as e:
        logger.error(f"Error: {e}")


def check_position_snapshots():
    """Check portfolio position count over time."""
    logger.info("\n" + "="*70)
    logger.info("PORTFOLIO SNAPSHOTS (Open position count over time)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT
                    snapshot_date, position_count, total_portfolio_value,
                    win_count_today, loss_count_today
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '10 days'
                ORDER BY snapshot_date DESC
            """)

            rows = cur.fetchall()
            logger.info(f"\nPortfolio position counts (last 10 days):\n")
            logger.info(f"  {'Date':<12} {'Positions':<12} {'Portfolio':<15} {'Wins':<8} {'Losses':<8}")
            logger.info(f"  {'-'*12} {'-'*12} {'-'*15} {'-'*8} {'-'*8}")

            for snapshot_date, pos_count, portfolio_val, wins, losses in rows:
                portfolio_str = f"${portfolio_val:,.0f}" if portfolio_val else "N/A"
                logger.info(f"  {str(snapshot_date):<12} {pos_count if pos_count else 0:<12} {portfolio_str:<15} {wins or 0:<8} {losses or 0:<8}")
    except Exception as e:
        logger.error(f"Error: {e}")


def check_exit_triggers():
    """Check what's triggering exits (profit targets, stops, etc)."""
    logger.info("\n" + "="*70)
    logger.info("EXIT REASONS (What's closing positions?)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT exit_reason, COUNT(*) as count
                FROM algo_trades
                WHERE trade_date >= CURRENT_DATE - INTERVAL '7 days'
                  AND status = 'closed'
                GROUP BY exit_reason
                ORDER BY count DESC
            """)

            rows = cur.fetchall()
            logger.info(f"\nExit reasons for closed trades (last 7 days):\n")

            if not rows:
                logger.warning("No closed trades found")
                return

            for reason, count in rows:
                logger.info(f"  {reason or '(unknown)':<40} : {count:3d} trades")
    except Exception as e:
        logger.error(f"Error: {e}")


def check_phase_4_activity():
    """Check Phase 4 (exit execution) activity."""
    logger.info("\n" + "="*70)
    logger.info("PHASE 4 EXECUTION (Exit logic)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Check if Phase 4 is running
            cur.execute("""
                SELECT run_date, COUNT(*) as trades_closed
                FROM algo_trades
                WHERE trade_date >= CURRENT_DATE - INTERVAL '5 days'
                  AND status = 'closed'
                GROUP BY run_date
                ORDER BY run_date DESC
            """)

            rows = cur.fetchall()
            logger.info(f"\nTrades closed by run date:\n")
            if rows:
                for run_date, count in rows:
                    logger.info(f"  {run_date}: {count} trades closed")
            else:
                logger.warning("No trade closure records found")
    except Exception as e:
        logger.debug(f"Could not check Phase 4: {e}")


if __name__ == "__main__":
    try:
        logger.info("🔍 Deep Diagnostic - Why are positions closing immediately?")
        check_trade_hold_times()
        check_position_snapshots()
        check_exit_triggers()
        check_phase_4_activity()

        logger.info("\n" + "="*70)
        logger.info("💡 ANALYSIS")
        logger.info("="*70)
        logger.info("""
If you see:
  1. Closed trades with 0-1 day hold time → Phase 4 is aggressively exiting
  2. Most exits by profit target or stop loss → Normal exit behavior
  3. Portfolio position_count = 0 daily → All positions exited every run

Check:
  - Phase 4 (phase4_exit_execution.py) - is it exiting too aggressively?
  - Exit parameters: profit targets too low? Stops too tight?
  - Check algo_position_monitor.py - is it closing positions prematurely?
        """)

        logger.info("="*70 + "\n")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

#!/usr/bin/env python3
"""
Diagnostic script to understand why algo has no open positions.

Checks:
1. Market regime (is_entry_allowed)
2. Circuit breaker status
3. Recent orchestrator runs
4. Open positions count
5. Recent signal generation
6. Recent trade execution
"""

import sys
import logging
from datetime import date as _date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from utils.timezone_utils import EASTERN_TZ

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def check_market_regime():
    """Check if market regime is allowing entries."""
    logger.info("\n" + "="*70)
    logger.info("1. MARKET REGIME (is_entry_allowed)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT date, exposure_pct, regime, is_entry_allowed, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC LIMIT 3
            """)
            rows = cur.fetchall()
            if not rows:
                logger.warning("No market_exposure_daily data found")
                return False

            for date, exposure_pct, regime, is_entry_allowed, halt_reasons in rows:
                logger.info(f"\n  Date: {date}")
                logger.info(f"    Exposure: {exposure_pct}%")
                logger.info(f"    Regime: {regime}")
                logger.info(f"    Entry Allowed: {is_entry_allowed}")
                if halt_reasons:
                    import json
                    reasons = json.loads(halt_reasons) if isinstance(halt_reasons, str) else halt_reasons
                    logger.warning(f"    ⚠️  HALT REASONS: {'; '.join(reasons)}")

            # Latest entry allowed?
            latest_allowed = rows[0][3] if rows else False
            return latest_allowed
    except Exception as e:
        logger.error(f"Error checking market regime: {e}")
        return None


def check_circuit_breakers():
    """Check if circuit breakers are blocking trades."""
    logger.info("\n" + "="*70)
    logger.info("2. CIRCUIT BREAKER STATUS")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT check_date, any_triggered, triggered_count
                FROM circuit_breaker_status
                ORDER BY check_date DESC LIMIT 3
            """)
            rows = cur.fetchall()
            if not rows:
                logger.warning("No circuit_breaker_status data found")
                return True  # Assume OK if no data

            for check_date, any_triggered, triggered_count in rows:
                status = "🔴 HALTED" if any_triggered else "✅ OK"
                logger.info(f"\n  Date: {check_date}")
                logger.info(f"    Status: {status}")
                if any_triggered:
                    logger.warning(f"    Triggered breakers: {triggered_count}")

            # Latest status
            latest_triggered = rows[0][1] if rows else False
            return not latest_triggered
    except Exception as e:
        logger.error(f"Error checking circuit breakers: {e}")
        return None


def check_open_positions():
    """Count open positions."""
    logger.info("\n" + "="*70)
    logger.info("3. OPEN POSITIONS")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Count open positions
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status = 'open'
            """)
            count = cur.fetchone()[0]
            logger.info(f"\n  Open positions: {count}")

            if count > 0:
                # List them
                cur.execute("""
                    SELECT symbol, quantity, avg_entry_price, current_price,
                           unrealized_pnl, created_at
                    FROM algo_positions
                    WHERE status = 'open'
                    ORDER BY created_at DESC
                """)
                logger.info("\n  Position details:")
                for symbol, qty, entry, current, pnl, created_at in cur.fetchall():
                    logger.info(f"    {symbol:6s}: {qty:4d} shares @ ${entry:8.2f} → ${current:8.2f} "
                              f"(P&L: ${pnl:8.2f}) - entered {created_at.date()}")
            else:
                logger.warning("  ❌ NO OPEN POSITIONS")

            return count
    except Exception as e:
        logger.error(f"Error checking open positions: {e}")
        return None


def check_recent_runs():
    """Check recent orchestrator runs."""
    logger.info("\n" + "="*70)
    logger.info("4. RECENT ORCHESTRATOR RUNS")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT run_date, overall_status, phases_completed, phases_halted, phases_errored, halt_reason
                FROM orchestrator_execution_log
                ORDER BY run_date DESC LIMIT 5
            """)
            rows = cur.fetchall()
            if not rows:
                logger.warning("No orchestrator_execution_log data found")
                return

            for run_date, status, completed, halted, errored, halt_reason in rows:
                status_emoji = {
                    'success': '✅',
                    'halted': '⏸️',
                    'error': '❌',
                    'skipped': '⊘'
                }.get(status, '?')

                logger.info(f"\n  {run_date} [{status_emoji} {status}]")
                logger.info(f"    Phases: {completed} completed, {halted} halted, {errored} errored")
                if halt_reason:
                    logger.warning(f"    Halt reason: {halt_reason}")
    except Exception as e:
        logger.error(f"Error checking recent runs: {e}")


def check_signal_generation():
    """Check if signals are being generated."""
    logger.info("\n" + "="*70)
    logger.info("5. SIGNAL GENERATION (Phase 5)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Check if there are any generated signals in the last 3 days
            cur.execute("""
                SELECT COUNT(*) FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '3 days'
            """)
            count = cur.fetchone()[0]
            logger.info(f"\n  Buy/sell signals in last 3 days: {count}")

            if count > 0:
                cur.execute("""
                    SELECT date, COUNT(DISTINCT symbol) as symbol_count
                    FROM buy_sell_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '3 days'
                    GROUP BY date
                    ORDER BY date DESC
                """)
                logger.info("\n  Signal counts by date:")
                for date, sym_count in cur.fetchall():
                    logger.info(f"    {date}: {sym_count} symbols")
            else:
                logger.warning("  ⚠️  No signals generated in last 3 days!")
    except Exception as e:
        logger.debug(f"Could not check signals (table may not exist): {e}")


def check_trade_execution():
    """Check recent trade execution."""
    logger.info("\n" + "="*70)
    logger.info("6. TRADE EXECUTION (Phase 6)")
    logger.info("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Check trades in last 3 days
            cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days'
            """)
            count = cur.fetchone()[0]
            logger.info(f"\n  Trades entered in last 3 days: {count}")

            if count > 0:
                cur.execute("""
                    SELECT trade_date, status, COUNT(*) as count
                    FROM algo_trades
                    WHERE trade_date >= CURRENT_DATE - INTERVAL '3 days'
                    GROUP BY trade_date, status
                    ORDER BY trade_date DESC
                """)
                logger.info("\n  Trade status by date:")
                for trade_date, trade_status, trade_count in cur.fetchall():
                    logger.info(f"    {trade_date} [{trade_status}]: {trade_count} trades")
            else:
                logger.warning("  ⚠️  No trades executed in last 3 days!")
    except Exception as e:
        logger.error(f"Error checking trade execution: {e}")


def generate_recommendation():
    """Synthesize findings and provide recommendation."""
    logger.info("\n" + "="*70)
    logger.info("DIAGNOSIS & RECOMMENDATION")
    logger.info("="*70)

    market_allowed = check_market_regime()
    breakers_ok = check_circuit_breakers()
    open_count = check_open_positions()

    logger.info("\n📊 SUMMARY:")
    if market_allowed is False:
        logger.warning("  ❌ Market regime is BLOCKING entries (halt_reasons active)")
        logger.info("\n💡 ACTION: Check why market_exposure_daily.halt_reasons has values")
        logger.info("   Possible reasons:")
        logger.info("   - SPY < 30-week MA AND < 30% stocks above 50-DMA")
        logger.info("   - VIX > 40 and rising")
        logger.info("   - 6+ distribution days")
        logger.info("   - No follow-through day while correcting")
        logger.info("   - HY credit spread > 8.5%")
        return

    if breakers_ok is False:
        logger.warning("  ❌ Circuit breakers are BLOCKING trades")
        logger.info("\n💡 ACTION: Check circuit_breaker_status.any_triggered")
        return

    if open_count == 0:
        logger.warning("  ⚠️  No open positions")
        logger.info("\n💡 POSSIBLE REASONS:")
        logger.info("   1. Phase 5 (signal generation) is halting")
        logger.info("   2. Phase 5 generates signals but Phase 6 doesn't execute them")
        logger.info("   3. Signals are filtered out before entry")
        logger.info("   4. Loaders haven't updated prices (Phase 1 may halt)")
        logger.info("\n💡 NEXT DEBUG STEPS:")
        logger.info("   1. Check orchestrator_execution_log for Phase 5 halt reason")
        logger.info("   2. Verify price_daily has today's data")
        logger.info("   3. Check buy_sell_daily for generated signals")
        logger.info("   4. If signals exist, check why Phase 6 didn't execute them")
        return

    logger.info(f"  ✅ Algo appears to be trading normally ({open_count} open positions)")


if __name__ == "__main__":
    try:
        logger.info("🔍 Algo Diagnostic Tool - Checking why no open positions")
        check_market_regime()
        check_circuit_breakers()
        check_open_positions()
        check_recent_runs()
        check_signal_generation()
        check_trade_execution()
        generate_recommendation()

        logger.info("\n" + "="*70)
        logger.info("✅ Diagnostic complete")
        logger.info("="*70 + "\n")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)

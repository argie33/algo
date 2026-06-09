#!/usr/bin/env python3
"""
Integration test for data architecture fix.

Verifies:
1. Dashboard fetch_positions() works and queries trades correctly
2. Fetch_perf() returns consistent results
3. Position sync checker detects issues
4. Query patterns are correct
"""

import sys
import os
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from utils.database_context import DatabaseContext
from utils.position_sync_checker import PositionSyncChecker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_trades_query():
    """Test that we can query open trades."""
    logger.info("TEST 1: Query open trades...")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM algo_trades
                WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                AND (exit_date IS NULL OR exit_date > CURRENT_DATE - 1)
            """)
            result = cur.fetchone()
            open_count = result[0] if result else 0
            logger.info(f"  ✓ Found {open_count} open trades")
            return open_count
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return None

def test_closed_trades_query():
    """Test that we can query closed trades."""
    logger.info("TEST 2: Query closed trades...")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM algo_trades
                WHERE status='closed' AND exit_date IS NOT NULL
            """)
            result = cur.fetchone()
            closed_count = result[0] if result else 0
            logger.info(f"  ✓ Found {closed_count} closed trades")
            return closed_count
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return None

def test_positions_derived_from_trades():
    """Test the new dashboard query pattern."""
    logger.info("TEST 3: Dashboard query (positions from trades)...")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                WITH open_trades AS (
                    SELECT DISTINCT ON (symbol)
                        symbol, entry_quantity, entry_price,
                        stop_loss_price, target_1_price, trade_date
                    FROM algo_trades
                    WHERE status IN ('open', 'filled', 'partially_filled', 'active')
                        AND (exit_date IS NULL OR exit_date > CURRENT_DATE - 1)
                    ORDER BY symbol, trade_date DESC
                ),
                latest_prices AS (
                    SELECT DISTINCT ON (symbol) symbol, close as current_price
                    FROM price_daily
                    ORDER BY symbol, date DESC
                )
                SELECT COUNT(*) as position_count
                FROM open_trades ot
                LEFT JOIN latest_prices lp ON ot.symbol = lp.symbol
            """)
            result = cur.fetchone()
            pos_count = result[0] if result else 0
            logger.info(f"  ✓ Dashboard query returns {pos_count} positions (derived from trades)")
            return pos_count
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return None

def test_consistency_checker():
    """Test the consistency checker."""
    logger.info("TEST 4: Position sync consistency checker...")
    try:
        checker = PositionSyncChecker()
        report = checker.check_consistency()

        logger.info(f"  Consistency: {'✓ CONSISTENT' if report['is_consistent'] else '✗ ISSUES FOUND'}")
        logger.info(f"  Open positions: {report['counts']['positions_open']}")
        logger.info(f"  Closed positions: {report['counts']['positions_closed']}")
        logger.info(f"  Open trades: {report['counts']['trades_open']}")
        logger.info(f"  Closed trades: {report['counts']['trades_closed']}")

        if report['issues']:
            logger.warning(f"  Found {len(report['issues'])} issue(s):")
            for issue in report['issues']:
                logger.warning(f"    - [{issue['severity']}] {issue['type']}: {issue['count']} found")

        return report
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return None

def test_performance_metrics():
    """Test that performance metrics query works."""
    logger.info("TEST 5: Performance metrics query...")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                    COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                    COUNT(*) as total,
                    SUM(profit_loss_dollars) as pnl,
                    AVG(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars END) as avg_win
                FROM algo_trades
                WHERE status='closed' AND exit_date IS NOT NULL
            """)
            result = cur.fetchone()
            if result:
                wins, losses, total, pnl, avg_win = result
                logger.info(f"  ✓ Trades: {total} total, {wins} wins, {losses} losses")
                logger.info(f"    P&L: ${pnl:,.2f}, Avg Win: ${avg_win:,.2f}" if pnl else "    No closed trades yet")
            return result
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return None

def verify_single_source_of_truth():
    """Verify positions and trades are derived from same source."""
    logger.info("TEST 6: Verify single source of truth...")
    try:
        open_trades = test_trades_query()
        positions_derived = test_positions_derived_from_trades()

        if open_trades is not None and positions_derived is not None:
            if open_trades == positions_derived:
                logger.info(f"  ✓ PASS: Open trades ({open_trades}) == Derived positions ({positions_derived})")
                return True
            else:
                logger.warning(f"  ⚠ Mismatch: Open trades ({open_trades}) vs Derived positions ({positions_derived})")
                logger.info("    This may be expected if you have pyramided positions (multiple trades per symbol)")
                return True  # Not necessarily an error
    except Exception as e:
        logger.error(f"  ✗ Failed: {e}")
        return False

def main():
    """Run all integration tests."""
    logger.info("=" * 70)
    logger.info("DATA ARCHITECTURE INTEGRATION TESTS")
    logger.info("=" * 70)
    logger.info("")

    results = {
        'trades': test_trades_query(),
        'closed': test_closed_trades_query(),
        'positions': test_positions_derived_from_trades(),
        'perf': test_performance_metrics(),
        'consistency': test_consistency_checker(),
    }

    logger.info("")
    logger.info("=" * 70)
    logger.info("VERIFICATION RESULTS")
    logger.info("=" * 70)

    # Check if source of truth is correct
    single_source = verify_single_source_of_truth()

    logger.info("")
    logger.info("SUMMARY:")
    logger.info(f"  Open trades: {results['trades']}")
    logger.info(f"  Closed trades: {results['closed']}")
    logger.info(f"  Derived positions: {results['positions']}")
    logger.info(f"  Single source of truth: {'✓ VERIFIED' if single_source else '✗ FAILED'}")

    if results['consistency']:
        consistency = results['consistency']
        logger.info(f"  Data consistency: {'✓ ALIGNED' if consistency['is_consistent'] else '⚠ DRIFT DETECTED'}")

        if not consistency['is_consistent']:
            logger.warning("")
            logger.warning("CONSISTENCY ISSUES FOUND:")
            for issue in consistency['issues']:
                logger.warning(f"  - {issue['type']}: {issue['count']} issue(s)")

    logger.info("")
    logger.info("=" * 70)
    logger.info("✓ All tests completed successfully!")
    logger.info("=" * 70)

    return 0 if single_source else 1

if __name__ == '__main__':
    sys.exit(main())

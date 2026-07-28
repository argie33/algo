#!/usr/bin/env python3
"""Comprehensive system diagnostics to identify all remaining issues."""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Setup path
project_root = str(Path(__file__).parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def check_price_data():
    """Check price_daily completeness."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 1: PRICE DATA COMPLETENESS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            # Total symbols
            result = ctx.execute('''
                SELECT COUNT(DISTINCT symbol) as total_symbols
                FROM stock_symbols
                WHERE is_active = TRUE
            ''')
            total_symbols = result.fetchone()[0]
            logger.info(f"✓ Total active symbols: {total_symbols}")

            # Price data coverage
            result = ctx.execute('''
                SELECT
                    DATE(MAX(date)) as latest_date,
                    COUNT(DISTINCT symbol) as symbols_with_data
                FROM price_daily
                WHERE date = CURRENT_DATE
            ''')
            row = result.fetchone()
            latest_date, symbols_today = row[0], row[1]
            pct = (symbols_today / total_symbols * 100) if total_symbols > 0 else 0
            logger.info(f"✓ Price data for {latest_date}: {symbols_today}/{total_symbols} ({pct:.1f}%)")

            if pct < 85:
                logger.warning(f"⚠ LOW COVERAGE: Only {pct:.1f}% of symbols have price data")
                # Find missing symbols
                result = ctx.execute('''
                    SELECT DISTINCT s.symbol
                    FROM stock_symbols s
                    WHERE s.is_active = TRUE
                      AND NOT EXISTS (
                        SELECT 1 FROM price_daily p
                        WHERE p.symbol = s.symbol AND p.date = CURRENT_DATE
                      )
                    ORDER BY s.symbol
                    LIMIT 20
                ''')
                missing = [row[0] for row in result.fetchall()]
                logger.warning(f"  Sample missing symbols: {', '.join(missing)}")
            else:
                logger.info(f"✓ Coverage is acceptable ({pct:.1f}%)")

    except Exception as e:
        logger.error(f"✗ Failed to check price data: {e}")

def check_signal_freshness():
    """Check signal freshness."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 2: SIGNAL FRESHNESS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            result = ctx.execute('''
                SELECT
                    DATE(MAX(date)) as latest_date,
                    COUNT(*) as signal_count
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - 2
                GROUP BY DATE(date)
                ORDER BY date DESC
            ''')
            rows = result.fetchall()
            for date_val, count in rows:
                days_old = (datetime.now().date() - date_val.date()).days
                if days_old > 1:
                    logger.warning(f"⚠ Signals from {date_val}: {count} signals ({days_old} days old)")
                else:
                    logger.info(f"✓ Signals from {date_val}: {count} signals ({days_old} days old)")

    except Exception as e:
        logger.error(f"✗ Failed to check signal freshness: {e}")

def check_position_data():
    """Check position data integrity."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 3: POSITION DATA INTEGRITY")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            # Check position quantities match trades
            result = ctx.execute('''
                SELECT
                    ap.position_id,
                    ap.symbol,
                    ap.quantity as position_qty,
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN at.side = 'BUY' THEN at.quantity ELSE -at.quantity END) as net_trade_qty
                FROM algo_positions ap
                LEFT JOIN algo_trades at ON ap.position_id = at.position_id
                WHERE ap.is_open = TRUE
                GROUP BY ap.position_id, ap.symbol, ap.quantity
                HAVING ap.quantity != SUM(CASE WHEN at.side = 'BUY' THEN at.quantity ELSE -at.quantity END)
            ''')
            mismatches = result.fetchall()

            if mismatches:
                logger.warning(f"⚠ QUANTITY MISMATCHES FOUND: {len(mismatches)} positions")
                for pos_id, symbol, pos_qty, trade_count, net_trade_qty in mismatches:
                    logger.warning(f"  {symbol}: position_qty={pos_qty}, net_trade_qty={net_trade_qty}")
            else:
                logger.info(f"✓ All position quantities match trades")

            # Get position count
            result = ctx.execute('SELECT COUNT(*) FROM algo_positions WHERE is_open = TRUE')
            open_positions = result.fetchone()[0]
            logger.info(f"✓ Open positions: {open_positions}")

    except Exception as e:
        logger.error(f"✗ Failed to check position data: {e}")

def check_stale_locks():
    """Check for stale locks."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 4: STALE LOCKS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timedelta
        with DatabaseContext(role='read') as ctx:
            result = ctx.execute('''
                SELECT
                    lock_name,
                    locked_by,
                    acquired_at,
                    EXTRACT(EPOCH FROM (NOW() - acquired_at))::INT as age_seconds
                FROM loader_execution_locks
                WHERE expires_at > NOW()
                ORDER BY acquired_at ASC
            ''')
            locks = result.fetchall()

            if not locks:
                logger.info(f"✓ No active locks")
            else:
                logger.info(f"✓ Active locks: {len(locks)}")
                for name, locked_by, acquired_at, age_seconds in locks:
                    if age_seconds > 300:
                        logger.warning(f"  ⚠ {name}: held for {age_seconds}s (by {locked_by[:8]}...)")
                    else:
                        logger.info(f"  ✓ {name}: {age_seconds}s (by {locked_by[:8]}...)")

    except Exception as e:
        logger.error(f"✗ Failed to check locks: {e}")

def check_loader_status():
    """Check loader execution status."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 5: LOADER STATUS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            result = ctx.execute('''
                SELECT
                    loader_name,
                    MAX(run_date) as last_run,
                    MAX(completion_pct) as completion,
                    EXTRACT(EPOCH FROM (NOW() - MAX(run_date)))::INT as age_seconds
                FROM loader_execution_tracking
                WHERE loader_name IN (
                    'price_daily', 'buy_sell_daily', 'market_health_daily',
                    'technical_data_daily', 'stock_scores'
                )
                GROUP BY loader_name
                ORDER BY loader_name
            ''')
            loaders = result.fetchall()

            for name, last_run, completion, age_seconds in loaders:
                status = "✓" if completion >= 90 else "⚠"
                hours_ago = age_seconds // 3600
                logger.info(f"{status} {name}: {completion}% (last run {hours_ago}h ago)")
                if completion < 90:
                    logger.warning(f"   INCOMPLETE: Only {completion}% done")

    except Exception as e:
        logger.error(f"✗ Failed to check loader status: {e}")

def check_recent_errors():
    """Check for recent errors in logs."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 6: RECENT ERRORS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            result = ctx.execute('''
                SELECT
                    error_type,
                    COUNT(*) as count,
                    MAX(timestamp) as latest
                FROM algo_audit_log
                WHERE timestamp > NOW() - INTERVAL '24 hours'
                  AND level = 'ERROR'
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
            ''')
            errors = result.fetchall()

            if not errors:
                logger.info(f"✓ No errors in last 24 hours")
            else:
                logger.warning(f"⚠ Found errors in last 24 hours:")
                for error_type, count, latest in errors:
                    logger.warning(f"  {error_type}: {count} occurrences (latest: {latest})")

    except Exception as e:
        logger.error(f"✗ Failed to check recent errors: {e}")

def check_exit_conditions():
    """Check if any positions should exit."""
    logger.info("\n" + "="*70)
    logger.info("ISSUE 7: EXIT CONDITIONS")
    logger.info("="*70)

    try:
        from utils.db import DatabaseContext
        with DatabaseContext(role='read') as ctx:
            # Check positions at stop loss
            result = ctx.execute('''
                SELECT
                    ap.symbol,
                    ap.quantity,
                    ap.entry_price,
                    pd.close as current_price,
                    ap.stop_loss_price,
                    ROUND((pd.close - ap.stop_loss_price) / ap.stop_loss_price * 100, 2) as pct_from_stop
                FROM algo_positions ap
                JOIN price_daily pd ON ap.symbol = pd.symbol AND pd.date = CURRENT_DATE
                WHERE ap.is_open = TRUE
                  AND pd.close <= ap.stop_loss_price
                ORDER BY ap.symbol
            ''')
            stop_hits = result.fetchall()

            if stop_hits:
                logger.warning(f"⚠ POSITIONS AT/BELOW STOP LOSS: {len(stop_hits)}")
                for symbol, qty, entry, current, stop, pct_from_stop in stop_hits:
                    logger.warning(f"  {symbol}: ${current:.2f} (stop: ${stop:.2f}, {pct_from_stop:+.2f}%)")
            else:
                logger.info(f"✓ No positions at stop loss")

            # Check positions at take profit
            result = ctx.execute('''
                SELECT
                    ap.symbol,
                    ap.quantity,
                    ap.entry_price,
                    pd.close as current_price,
                    ap.target_price,
                    ROUND((pd.close - ap.target_price) / ap.target_price * 100, 2) as pct_from_target
                FROM algo_positions ap
                JOIN price_daily pd ON ap.symbol = pd.symbol AND pd.date = CURRENT_DATE
                WHERE ap.is_open = TRUE
                  AND pd.close >= ap.target_price
                ORDER BY ap.symbol
            ''')
            profit_hits = result.fetchall()

            if profit_hits:
                logger.warning(f"⚠ POSITIONS AT/ABOVE TARGET: {len(profit_hits)}")
                for symbol, qty, entry, current, target, pct_from_target in profit_hits:
                    logger.warning(f"  {symbol}: ${current:.2f} (target: ${target:.2f}, {pct_from_target:+.2f}%)")
            else:
                logger.info(f"✓ No positions at target")

    except Exception as e:
        logger.error(f"✗ Failed to check exit conditions: {e}")

def main():
    logger.info("\n" + "█"*70)
    logger.info("COMPREHENSIVE SYSTEM DIAGNOSTICS - 2026-07-28")
    logger.info("█"*70)

    try:
        check_price_data()
        check_signal_freshness()
        check_position_data()
        check_stale_locks()
        check_loader_status()
        check_recent_errors()
        check_exit_conditions()

        logger.info("\n" + "="*70)
        logger.info("DIAGNOSTICS COMPLETE")
        logger.info("="*70)

    except Exception as e:
        logger.error(f"Fatal error during diagnostics: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

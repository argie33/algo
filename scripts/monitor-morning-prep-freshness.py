#!/usr/bin/env python3
"""
Monitor morning prep pipeline data freshness for Monday 2 AM ET run.

Checks if critical tables have fresh data (< 1 day old) with ≥90% symbol coverage.
Monitors across 8 critical tables:
- price_daily
- technical_data_daily
- buy_sell_daily
- signal_quality_scores
- swing_trader_scores
- market_health_daily
- trend_template_data
- sector_ranking

Run: python3 scripts/monitor-morning-prep-freshness.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple
from utils.database_context import DatabaseContext
from algo.algo_market_calendar import MarketCalendar

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

CRITICAL_TABLES = [
    'price_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'signal_quality_scores',
    'swing_trader_scores',
    'market_health_daily',
    'trend_template_data',
    'sector_ranking',
]

MIN_SYMBOL_COVERAGE = 0.90  # 90% minimum


def get_et_now() -> datetime:
    """Get current time in ET."""
    return datetime.now(ZoneInfo("America/New_York"))


def get_trading_day(date_obj=None) -> datetime:
    """Get the most recent trading day."""
    if date_obj is None:
        date_obj = get_et_now().date()

    # Work backward to find most recent trading day
    while not MarketCalendar.is_trading_day(date_obj):
        date_obj -= timedelta(days=1)

    return date_obj


def check_table_freshness(table_name: str, cur) -> Dict:
    """
    Check if a table has fresh data (< 1 day old) with good symbol coverage.

    Returns:
        {
            'table': str,
            'fresh': bool,
            'max_date': str,
            'days_old': float,
            'active_symbols': int,
            'total_symbols': int,
            'coverage_pct': float,
            'is_market_health': bool,
            'error': str or None
        }
    """
    is_market_health = table_name in ['market_health_daily', 'sector_ranking']

    try:
        # Get max date in table
        cur.execute(f"SELECT MAX(date) FROM {table_name}")
        row = cur.fetchone()
        max_date = row[0] if row else None

        if max_date is None:
            return {
                'table': table_name,
                'fresh': False,
                'max_date': None,
                'days_old': None,
                'active_symbols': 0,
                'total_symbols': 0,
                'coverage_pct': 0.0,
                'is_market_health': is_market_health,
                'error': 'No data found'
            }

        # Calculate days old
        et_now = get_et_now()
        max_date_et = max_date if hasattr(max_date, 'tzinfo') else max_date
        if isinstance(max_date_et, str):
            from datetime import date
            max_date_et = datetime.fromisoformat(max_date_et).date()

        if isinstance(max_date_et, datetime):
            max_date_et = max_date_et.date()

        today_et = et_now.date()
        days_old = (today_et - max_date_et).days

        # Get symbol coverage
        if is_market_health:
            # market_health_daily and sector_ranking are market-wide (no per-symbol)
            coverage_pct = 100.0
            active_symbols = 1
            total_symbols = 1
        else:
            # Get count of unique symbols in table for max_date
            cur.execute(
                f"SELECT COUNT(DISTINCT symbol) FROM {table_name} WHERE date = %s",
                (max_date,)
            )
            row = cur.fetchone()
            active_symbols = row[0] if row else 0

            # Get total symbols (note: stock_symbols table doesn't have 'active' column)
            # This is a schema accuracy issue - loaders query for non-existent column
            cur.execute("SELECT COUNT(*) FROM stock_symbols")
            row = cur.fetchone()
            total_symbols = row[0] if row else 4500

            coverage_pct = (active_symbols / total_symbols * 100) if total_symbols > 0 else 0.0

        # Determine freshness: < 1 day old AND good coverage
        fresh = days_old < 1 and coverage_pct >= MIN_SYMBOL_COVERAGE * 100

        return {
            'table': table_name,
            'fresh': fresh,
            'max_date': str(max_date),
            'days_old': days_old,
            'active_symbols': active_symbols,
            'total_symbols': total_symbols,
            'coverage_pct': coverage_pct,
            'is_market_health': is_market_health,
            'error': None
        }

    except Exception as e:
        logger.error(f"Failed to check {table_name}: {e}")
        return {
            'table': table_name,
            'fresh': False,
            'max_date': None,
            'days_old': None,
            'active_symbols': 0,
            'total_symbols': 0,
            'coverage_pct': 0.0,
            'is_market_health': is_market_health,
            'error': str(e)
        }


def check_all_tables() -> Tuple[List[Dict], bool]:
    """Check freshness of all critical tables. Returns (results, all_fresh)."""
    results = []

    try:
        with DatabaseContext('read') as cur:
            for table in CRITICAL_TABLES:
                result = check_table_freshness(table, cur)
                results.append(result)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return results, False

    # All fresh if all tables have fresh data
    all_fresh = all(r['fresh'] for r in results)

    return results, all_fresh


def format_results(results: List[Dict]) -> str:
    """Format results for display."""
    lines = []
    lines.append("\n" + "="*100)
    lines.append("DATA FRESHNESS CHECK -- {}".format(get_et_now().strftime('%Y-%m-%d %H:%M:%S ET')))
    lines.append("="*100)

    fresh_count = sum(1 for r in results if r['fresh'])
    total_count = len(results)

    lines.append("\nStatus: {}/{} tables fresh\n".format(fresh_count, total_count))

    for r in results:
        status = "[OK] FRESH" if r['fresh'] else "[!!] STALE"

        if r['error']:
            lines.append("  {:30s} {:15s} -- ERROR: {}".format(r['table'], status, r['error']))
        elif r['max_date'] is None:
            lines.append("  {:30s} {:15s} -- No data found".format(r['table'], status))
        else:
            if r['is_market_health']:
                coverage_str = "(market-wide)"
            else:
                coverage_str = "{:.0f}% coverage ({}/{} symbols)".format(
                    r['coverage_pct'], r['active_symbols'], r['total_symbols']
                )

            lines.append(
                "  {:30s} {:15s} -- Date: {}, Age: {:.1f}d, {}".format(
                    r['table'], status, r['max_date'], r['days_old'], coverage_str
                )
            )

    lines.append("\n" + "="*100)

    return "\n".join(lines)


def main():
    """Check data freshness."""
    results, all_fresh = check_all_tables()

    output = format_results(results)
    logger.info(output)
    print(output)

    # Return exit code based on freshness
    if all_fresh:
        logger.info("✓ All critical tables have fresh data! Morning prep pipeline ready.")
        return 0
    else:
        stale_tables = [r['table'] for r in results if not r['fresh']]
        logger.warning(f"⚠ Stale data detected in: {', '.join(stale_tables)}")
        return 1


if __name__ == '__main__':
    sys.exit(main())

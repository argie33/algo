#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK (Simplified)

Only check ONE thing: Are recent prices loaded?
- Query price_daily for the most recent available date
- Verify that date is the last trading day (or today on a trading day)
- Verify 95%+ symbol coverage
- That's it. Done in <1 minute.

This replaces the 2000-line complexity with 100 lines of actual logic.
No grace periods, no hung task detection, no failsafe triggers.
"""

import logging
import time
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable

from utils.database_context import DatabaseContext
from algo.algo_alerts import AlertManager
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 1: Verify recent price data is loaded.

    The morning prep pipeline loads EOD prices for the last completed trading day,
    not for the current calendar day (which may just be opening). This check finds
    the most recent date in price_daily and verifies it is the last trading day
    before today.
    """
    phase_start = time.time()

    logger.info("[PHASE 1] Starting price data freshness check")

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SET statement_timeout = 10000")  # 10s timeout

            # Check 1: Find the most recent date in price_daily
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(1, 'price_data', 'halt', 'price_daily table is empty')
                return PhaseResult(1, 'price_data', 'halted', {}, True,
                                 'price_daily table is empty')

            # Check 2: Is the most recent date the last trading day before today?
            # At 9:30 AM ET when markets just open, the price loader has loaded
            # EOD data for the previous trading day (e.g., Friday when today is Monday).
            from algo.algo_market_calendar import MarketCalendar
            last_trading_day = run_date - timedelta(days=1)
            while last_trading_day > run_date - timedelta(days=10):
                if MarketCalendar.is_trading_day(last_trading_day):
                    break
                last_trading_day -= timedelta(days=1)

            # Allow data from last_trading_day or run_date (if today's prices loaded)
            if max_date < last_trading_day:
                days_stale = (last_trading_day - max_date).days
                logger.critical(
                    f"[PHASE 1] Price data is {days_stale} trading day(s) stale. "
                    f"Latest: {max_date}, expected: {last_trading_day}"
                )
                log_phase_result_fn(1, 'price_staleness', 'halt',
                                   f'Price data stale: latest={max_date}, expected>={last_trading_day}')
                return PhaseResult(1, 'price_staleness', 'halted', {}, True,
                                 f'Price data too old: {max_date} vs expected {last_trading_day}')

            # Check 3: How many symbols have data on the most recent date?
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (max_date,)
            )
            symbols_loaded = cur.fetchone()[0] or 0

            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM stock_symbols "
                "WHERE COALESCE(active, TRUE) AND COALESCE(etf, 'N') != 'Y'"
            )
            total_active = cur.fetchone()[0] or 1
            coverage = (symbols_loaded / total_active) * 100

            if coverage < 95:
                logger.critical(
                    f"[PHASE 1] INSUFFICIENT COVERAGE: {symbols_loaded}/{total_active} "
                    f"symbols ({coverage:.1f}%) for {max_date} — need ≥95%"
                )
                log_phase_result_fn(1, 'price_coverage', 'halt',
                                   f'Price coverage {coverage:.1f}% < 95% threshold')
                return PhaseResult(1, 'price_coverage', 'halted', {}, True,
                                 f'Insufficient price coverage: {coverage:.1f}%')

            elapsed = time.time() - phase_start

            # SUCCESS
            logger.info(f"[PHASE 1] ✓ PASS")
            logger.info(f"  - Most recent prices: {max_date} ({symbols_loaded} symbols, {coverage:.1f}%)")
            logger.info(f"  - Last trading day: {last_trading_day}")
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            log_phase_result_fn(1, 'price_freshness', 'success',
                               f'{max_date}: {symbols_loaded} symbols, {coverage:.1f}% coverage')

            return PhaseResult(1, 'price_freshness', 'ok',
                             {'price_date': str(max_date), 'symbols_loaded': symbols_loaded, 'coverage_pct': coverage},
                             False, 'Price data fresh and complete')

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, 'error', 'error', str(e)[:100])
        return PhaseResult(1, 'error', 'error', {}, True, f'Phase 1 error: {str(e)[:100]}')

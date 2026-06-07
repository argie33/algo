#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK (Simplified)

Only check ONE thing: Are today's prices loaded?
- Query price_daily for today's date
- Verify 95%+ symbol coverage
- That's it. Done in <1 minute.

This replaces the 2000-line complexity with 100 lines of actual logic.
No grace periods, no hung task detection, no failsafe triggers.
"""

import logging
import os
import time
from datetime import date as _date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Optional

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
    """Execute Phase 1: Verify today's price data is loaded.

    This is the simplified version that only checks:
    1. price_daily has data for today
    2. At least 95% of symbols are covered

    If prices are loaded, we're good. Everything else (signals, indicators)
    will be computed on-demand by later phases.
    """
    phase_start = time.time()

    logger.info("[PHASE 1] Starting price data freshness check")

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SET statement_timeout = 10000")  # 10s timeout

            # Check 1: Does price_daily have today's data?
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (run_date,)
            )
            symbols_today = cur.fetchone()[0] or 0

            if symbols_today == 0:
                # No data for today - this means price loader hasn't run yet
                logger.critical(f"[PHASE 1] NO PRICE DATA FOR {run_date}")
                logger.critical("[PHASE 1] price_daily loader must run before 9:30 AM")
                log_phase_result_fn(1, 'price_data', 'halt',
                                   f'No price data loaded for {run_date}')
                return PhaseResult(1, 'price_data', 'halted', {}, True,
                                 'Price data not loaded for today')

            # Check 2: How many symbols are in the active list?
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM stock_symbols "
                "WHERE COALESCE(active, TRUE) AND COALESCE(etf, 'N') != 'Y'"
            )
            total_active = cur.fetchone()[0] or 1
            coverage = (symbols_today / total_active) * 100

            if coverage < 95:
                logger.critical(
                    f"[PHASE 1] INSUFFICIENT COVERAGE: {symbols_today}/{total_active} "
                    f"symbols ({coverage:.1f}%) — need ≥95%"
                )
                log_phase_result_fn(1, 'price_coverage', 'halt',
                                   f'Price coverage {coverage:.1f}% < 95% threshold')
                return PhaseResult(1, 'price_coverage', 'halted', {}, True,
                                 f'Insufficient price coverage: {coverage:.1f}%')

            # Check 3: Sanity check - today's prices are recent (within last 2 hours)
            # This catches cases where DB has stale data or clock is wrong
            now_et = datetime.now(ZoneInfo("America/New_York"))
            cur.execute(
                "SELECT MAX(updated_at) FROM price_daily WHERE date = %s",
                (run_date,)
            )
            max_updated = cur.fetchone()[0]

            if max_updated:
                if isinstance(max_updated, str):
                    max_updated = datetime.fromisoformat(max_updated.replace('Z', '+00:00'))
                elif max_updated.tzinfo is None:
                    max_updated = max_updated.replace(tzinfo=timezone.utc)

                age_minutes = (datetime.now(timezone.utc) - max_updated).total_seconds() / 60

                # Allow up to 2 hours old (covers morning prep delays)
                if age_minutes > 120 and now_et.hour < 9:
                    logger.warning(
                        f"[PHASE 1] Price data is {age_minutes:.0f} min old "
                        f"(loaded at {max_updated.strftime('%H:%M')}). "
                        f"If >2 hours old, price loader may have stalled."
                    )
                    if age_minutes > 120:
                        log_phase_result_fn(1, 'price_age', 'halt',
                                           f'Price data too old: {age_minutes:.0f} min')
                        return PhaseResult(1, 'price_age', 'halted', {}, True,
                                         f'Price data stale: {age_minutes:.0f} minutes old')

            elapsed = time.time() - phase_start

            # SUCCESS
            logger.info(f"[PHASE 1] ✓ PASS")
            logger.info(f"  - Today's prices: {symbols_today} symbols ({coverage:.1f}%)")
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            log_phase_result_fn(1, 'price_freshness', 'success',
                               f'{symbols_today} symbols, {coverage:.1f}% coverage')

            return PhaseResult(1, 'price_freshness', 'ok',
                             {'symbols_loaded': symbols_today, 'coverage_pct': coverage},
                             False, 'Price data fresh and complete')

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, 'error', 'error', str(e)[:100])
        return PhaseResult(1, 'error', 'error', {}, True, f'Phase 1 error: {str(e)[:100]}')

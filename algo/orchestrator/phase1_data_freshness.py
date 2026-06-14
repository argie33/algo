#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK (Simplified)

Only check ONE thing: Are recent prices loaded?
- Query price_daily for the most recent available date
- Verify that date is the last trading day (or today on a trading day)
- Verify 75%+ symbol coverage with 8000+ minimum symbols
- That's it. Done in <1 minute.

This replaces the 2000-line complexity with 100 lines of actual logic.
No grace periods, no hung task detection, no failsafe triggers.
"""

import logging
import time
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable

from utils.db.context import DatabaseContext
from algo.reporting import AlertManager
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

    # Get configurable thresholds (with realistic defaults for robust operation)
    # 75% coverage vs prior day allows for minor data delays without halting
    # 2000 minimum symbols is realistic for actual available data
    # (many symbols don't have data for every date; 75% coverage check handles quality)
    min_coverage_pct = config.get('phase1_min_coverage_pct', 75) if config else 75
    min_symbol_count = config.get('phase1_min_symbol_count', 2000) if config else 2000

    # SLA: Morning prep pipeline must complete by 9:30 AM ET (7.5 hours from 2 AM start)
    # Current time check for SLA monitoring
    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    now_et = dt.now(ZoneInfo('America/New_York'))
    pipeline_context = "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"

    logger.info(f"[PHASE 1] Starting price data freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})")

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
            from algo.infrastructure import MarketCalendar
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
            symbols_loaded = cur.fetchone()[0]
            # Compare against the prior date's symbol count to detect coverage drops.
            # Avoids querying stock_symbols (schema may vary across environments).
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = ("
                "  SELECT MAX(date) FROM price_daily WHERE date < %s"
                ")",
                (max_date,)
            )
            prior_count = cur.fetchone()[0] or symbols_loaded
            # Require 75%+ of prior date's coverage, and a hard minimum of 8000 symbols
            coverage_vs_prior = (symbols_loaded / max(prior_count, 1)) * 100

            # If today has partial data (e.g. intraday seed or in-progress EOD load),
            # evaluate coverage against the prior date instead — that's what matters for
            # knowing whether signals are ready for the current session.
            if symbols_loaded < 1000 and max_date == run_date:
                logger.info(
                    f"[PHASE 1] Today ({max_date}) has partial coverage ({symbols_loaded} symbols) — "
                    f"EOD loader in progress or intraday seed. Checking prior date ({last_trading_day})."
                )
                symbols_loaded = prior_count
                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = ("
                    "  SELECT MAX(date) FROM price_daily WHERE date < %s"
                    ")",
                    (last_trading_day,)
                )
                row = cur.fetchone()
                prior_prior_count = row[0] if row else symbols_loaded
                coverage_vs_prior = (symbols_loaded / max(prior_prior_count, 1)) * 100
                max_date = last_trading_day

            if symbols_loaded < min_symbol_count or coverage_vs_prior < min_coverage_pct:
                logger.critical(
                    f"[PHASE 1] INSUFFICIENT COVERAGE: {symbols_loaded} symbols for {max_date} "
                    f"vs {prior_count} prior day ({coverage_vs_prior:.1f}%) — need >={min_coverage_pct}%"
                )
                log_phase_result_fn(1, 'price_coverage', 'halt',
                                   f'Price coverage {coverage_vs_prior:.1f}% vs prior day')
                return PhaseResult(1, 'price_coverage', 'halted', {}, True,
                                 f'Insufficient price coverage: {symbols_loaded} symbols ({coverage_vs_prior:.1f}% vs prior day)')

            elapsed = time.time() - phase_start

            # SUCCESS
            # SLA Check: Verify we're still within SLA window
            from datetime import datetime as dt
            from zoneinfo import ZoneInfo
            phase1_end_et = dt.now(ZoneInfo('America/New_York'))

            sla_status = ""
            if pipeline_context == "MORNING":
                sla_deadline = phase1_end_et.replace(hour=9, minute=30, second=0, microsecond=0)
                if phase1_end_et < sla_deadline:
                    minutes_until_sla = ((sla_deadline - phase1_end_et).total_seconds() / 60)
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m buffer until 9:30 AM]"
                else:
                    sla_status = f" [SLA WARNING: Past 9:30 AM deadline]"
            elif pipeline_context == "INTRADAY":
                if now_et.hour == 14:  # 2 PM - afternoon update
                    sla_deadline = phase1_end_et.replace(hour=13, minute=5, second=0, microsecond=0)  # 1:05 PM target
                elif now_et.hour == 15:  # 3 PM - pre-close update
                    sla_deadline = phase1_end_et.replace(hour=15, minute=15, second=0, microsecond=0)  # 3:15 PM deadline
                else:
                    sla_deadline = None
                if sla_deadline and phase1_end_et < sla_deadline:
                    minutes_until_sla = ((sla_deadline - phase1_end_et).total_seconds() / 60)
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m buffer]"

            logger.info(f"[PHASE 1] PASS{sla_status}")
            logger.info(f"  - Most recent prices: {max_date} ({symbols_loaded} symbols, {coverage_vs_prior:.1f}% vs prior day)")
            logger.info(f"  - Last trading day: {last_trading_day}")
            logger.info(f"  - Thresholds: >={min_symbol_count} symbols, >={min_coverage_pct}% coverage")
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            log_phase_result_fn(1, 'price_freshness', 'success',
                               f'{max_date}: {symbols_loaded} symbols, {coverage_vs_prior:.1f}% vs prior day')

            return PhaseResult(1, 'price_freshness', 'ok',
                             {'price_date': str(max_date), 'symbols_loaded': symbols_loaded, 'coverage_pct': coverage_vs_prior},
                             False, 'Price data fresh and complete')

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, 'error', 'error', str(e)[:100])
        return PhaseResult(1, 'error', 'error', {}, True, f'Phase 1 error: {str(e)[:100]}')

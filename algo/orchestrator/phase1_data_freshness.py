#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify ALL signal-critical tables are fresh before trading:
1. price_daily: Must have last trading day data (75%+ symbol coverage)
2. buy_sell_daily: Buy/sell signals for last trading day
3. technical_data_daily: Technical indicators for last trading day
4. swing_trader_scores: Swing scoring (must be <24h old)
5. signal_quality_scores: Signal quality ratings (must be <24h old)
6. market_exposure_daily: Market exposure limits (must be present and fresh)
7. sector_ranking: Sector data for last trading day

If ANY critical table is stale or missing, halt trading to prevent degraded signal generation.
No partial trading with incomplete data: all-or-nothing freshness gate.
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
    """Execute Phase 1: Verify ALL signal-critical tables are fresh.

    Checks that price_daily, buy_sell_daily, technical_data_daily, swing_trader_scores,
    signal_quality_scores, market_exposure_daily, and sector_ranking are all recent
    and complete. No trading without all critical data fresh.
    """
    phase_start = time.time()

    min_coverage_pct = config.get('phase1_min_coverage_pct', 75) if config else 75
    min_symbol_count = config.get('phase1_min_symbol_count', 2000) if config else 2000
    signal_freshness_hours = config.get('phase1_signal_freshness_hours', 24) if config else 24
    max_stale_hours = signal_freshness_hours

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo
    now_et = dt.now(ZoneInfo('America/New_York'))
    pipeline_context = "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"

    logger.info(f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})")

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SET statement_timeout = 15000")  # 15s timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(1, 'price_data', 'halt', 'price_daily table is empty')
                return PhaseResult(1, 'price_data', 'halted', {}, True, 'price_daily table is empty')

            from algo.infrastructure import MarketCalendar
            last_trading_day = run_date - timedelta(days=1)
            while last_trading_day > run_date - timedelta(days=10):
                if MarketCalendar.is_trading_day(last_trading_day):
                    break
                last_trading_day -= timedelta(days=1)

            if max_date < last_trading_day:
                days_stale = (last_trading_day - max_date).days
                logger.critical(f"[PHASE 1] Price data stale: {max_date} vs expected {last_trading_day}")
                log_phase_result_fn(1, 'price_staleness', 'halt',
                                   f'Price data {days_stale} days stale')
                return PhaseResult(1, 'price_staleness', 'halted', {}, True,
                                 f'Price data too old: {max_date} vs {last_trading_day}')

            # Verify price coverage
            cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s", (max_date,))
            symbols_loaded = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
                "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
                (max_date,)
            )
            prior_count = cur.fetchone()[0] or symbols_loaded
            coverage_pct = (symbols_loaded / max(prior_count, 1)) * 100

            if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
                logger.critical(f"[PHASE 1] Insufficient price coverage: {symbols_loaded} symbols ({coverage_pct:.1f}%)")
                log_phase_result_fn(1, 'price_coverage', 'halt',
                                   f'Price coverage {coverage_pct:.1f}% vs {min_coverage_pct}%')
                return PhaseResult(1, 'price_coverage', 'halted', {}, True,
                                 f'Insufficient price coverage: {coverage_pct:.1f}%')

            # Check all critical signal tables
            critical_tables = {
                'buy_sell_daily': 'Buy/sell signals',
                'technical_data_daily': 'Technical indicators',
                'swing_trader_scores': 'Swing trader scores',
                'signal_quality_scores': 'Signal quality scores',
                'market_exposure_daily': 'Market exposure limits',
                'sector_ranking': 'Sector rankings',
            }

            now_utc = datetime.now(timezone.utc)
            stale_tables = []

            for table_name, description in critical_tables.items():
                try:
                    # Check if table exists and has recent data
                    cur.execute(f"SELECT MAX(date) FROM {table_name}")
                    table_max_date = cur.fetchone()[0]

                    if table_max_date is None:
                        logger.critical(f"[PHASE 1] {description} ({table_name}) is EMPTY")
                        stale_tables.append(f"{description} is empty")
                        continue

                    # Check staleness
                    if table_max_date < max_date:
                        days_behind = (max_date - table_max_date).days
                        logger.warning(f"[PHASE 1] {description} is {days_behind} day(s) behind prices")
                        stale_tables.append(f"{description} is {days_behind} day(s) stale")

                    # For time-based freshness (swing/quality scores updated frequently)
                    if table_name in ['swing_trader_scores', 'signal_quality_scores']:
                        cur.execute(f"SELECT MAX(created_at) FROM {table_name}")
                        max_created = cur.fetchone()[0]
                        if max_created:
                            if max_created.tzinfo is None:
                                max_created = max_created.replace(tzinfo=timezone.utc)
                            age_hours = (now_utc - max_created).total_seconds() / 3600
                            if age_hours > max_stale_hours:
                                logger.critical(f"[PHASE 1] {description} is {age_hours:.1f}h old (max {max_stale_hours}h)")
                                stale_tables.append(f"{description} is {age_hours:.1f}h old")

                except Exception as e:
                    logger.warning(f"[PHASE 1] Could not check {description}: {e}")
                    stale_tables.append(f"{description} check failed: {str(e)[:50]}")

            if stale_tables:
                logger.critical(f"[PHASE 1] CRITICAL DATA GAPS: {'; '.join(stale_tables)}")
                log_phase_result_fn(1, 'signal_tables_stale', 'halt',
                                   f"Stale/missing signal data: {'; '.join(stale_tables[:3])}")
                # Alert on signal staleness
                from algo.reporting.notifications import notify_signal_staleness
                notify_signal_staleness(stale_tables)
                return PhaseResult(1, 'signal_tables_stale', 'halted', {}, True,
                                 f"Critical tables stale/missing: {stale_tables[0]}")

            elapsed = time.time() - phase_start
            phase1_end_et = dt.now(ZoneInfo('America/New_York'))

            sla_status = ""
            if pipeline_context == "MORNING":
                sla_deadline = phase1_end_et.replace(hour=9, minute=30, second=0, microsecond=0)
                if phase1_end_et < sla_deadline:
                    minutes_until_sla = ((sla_deadline - phase1_end_et).total_seconds() / 60)
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m until 9:30 AM]"
                else:
                    sla_status = f" [SLA WARNING: Past 9:30 AM]"

            logger.info(f"[PHASE 1] PASS - ALL CRITICAL DATA FRESH{sla_status}")
            logger.info(f"  - Prices: {max_date} ({symbols_loaded} symbols, {coverage_pct:.1f}%)")
            logger.info(f"  - All signal tables verified fresh and complete")
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            log_phase_result_fn(1, 'all_tables_fresh', 'success',
                               f'All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%')

            return PhaseResult(1, 'all_tables_fresh', 'ok',
                             {'price_date': str(max_date), 'symbols_loaded': symbols_loaded, 'coverage_pct': coverage_pct},
                             False, 'All critical data fresh and complete')

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, 'error', 'error', str(e)[:100])
        return PhaseResult(1, 'error', 'error', {}, True, f'Phase 1 error: {str(e)[:100]}')

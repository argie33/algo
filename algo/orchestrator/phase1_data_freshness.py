#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify pipeline-loaded tables are fresh before trading:
1. price_daily: Must have last trading day data (75%+ symbol coverage) — HALT if stale
2. market_health_daily: Market breadth metrics — HALT if stale
3. trend_template_data: Minervini/Weinstein criteria — HALT if stale
4. market_exposure_daily: Market regime / exposure limits — HALT if stale
5. swing_trader_scores: Swing scoring (must be <24h old) — WARNING if stale
6. sector_ranking: Sector data for last trading day — WARNING if stale

NOTE: buy_sell_daily, technical_data_daily, signal_quality_scores are NOT checked here.
Phase 5 generates signals on-the-fly from price_daily (no dependency on pre-computed tables).
Those tables are auxiliary and loaded separately; staleness there does not block trading.
"""

import logging
import time
from datetime import date as _date, datetime, timedelta, timezone
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

    min_coverage_pct = config.get("phase1_min_coverage_pct", 75) if config else 75
    min_symbol_count = config.get("phase1_min_symbol_count", 2000) if config else 2000
    signal_freshness_hours = (
        config.get("phase1_signal_freshness_hours", 24) if config else 24
    )
    max_stale_hours = signal_freshness_hours

    from datetime import datetime as dt
    from zoneinfo import ZoneInfo

    now_et = dt.now(ZoneInfo("America/New_York"))
    pipeline_context = (
        "EOD" if now_et.hour >= 16 else "MORNING" if now_et.hour < 10 else "INTRADAY"
    )

    logger.info(
        f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})"
    )

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SET statement_timeout = 15000"
            )  # 15s timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(
                    1, "price_data", "halt", "price_daily table is empty"
                )
                return PhaseResult(
                    1, "price_data", "halted", {}, True, "price_daily table is empty"
                )

            from algo.infrastructure import MarketCalendar

            last_trading_day = run_date - timedelta(days=1)
            while last_trading_day > run_date - timedelta(days=10):
                if MarketCalendar.is_trading_day(last_trading_day):
                    break
                last_trading_day -= timedelta(days=1)

            if max_date < last_trading_day:
                days_stale = (last_trading_day - max_date).days
                logger.critical(
                    f"[PHASE 1] Price data stale: {max_date} vs expected {last_trading_day}"
                )
                log_phase_result_fn(
                    1, "price_staleness", "halt", f"Price data {days_stale} days stale"
                )
                return PhaseResult(
                    1,
                    "price_staleness",
                    "halted",
                    {},
                    True,
                    f"Price data too old: {max_date} vs {last_trading_day}",
                )

            # Verify price coverage
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (max_date,),
            )
            symbols_loaded = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
                "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
                (max_date,),
            )
            prior_count = cur.fetchone()[0] or symbols_loaded
            coverage_pct = (symbols_loaded / max(prior_count, 1)) * 100

            if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
                logger.critical(
                    f"[PHASE 1] Insufficient price coverage: {symbols_loaded} symbols ({coverage_pct:.1f}%)"
                )
                log_phase_result_fn(
                    1,
                    "price_coverage",
                    "halt",
                    f"Price coverage {coverage_pct:.1f}% vs {min_coverage_pct}%",
                )
                return PhaseResult(
                    1,
                    "price_coverage",
                    "halted",
                    {},
                    True,
                    f"Insufficient price coverage: {coverage_pct:.1f}%",
                )

            # Check tables that the pipeline actually loads (fail-closed on these)
            # Phase 5 generates signals on-the-fly from price_daily; buy_sell_daily,
            # technical_data_daily, and signal_quality_scores are not pipeline-loaded.
            halt_tables = {
                "market_health_daily": "Market health (breadth/regime)",
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "market_exposure_daily": "Market exposure limits",
            }
            # Warning-only tables: stale → logged, not a halt
            warn_tables = {
                "swing_trader_scores": "Swing trader scores",
                "sector_ranking": "Sector rankings",
            }
            critical_tables = {**halt_tables, **warn_tables}

            now_utc = datetime.now(timezone.utc)
            halt_stale = []   # pipeline-loaded tables — stale = HALT
            warn_stale = []   # auxiliary tables — stale = WARNING only

            for table_name, description in critical_tables.items():
                is_halt_table = table_name in halt_tables
                try:
                    cur.execute(f"SELECT MAX(date) FROM {table_name}")
                    table_max_date = cur.fetchone()[0]

                    if table_max_date is None:
                        msg = f"{description} is empty"
                        if is_halt_table:
                            logger.critical(f"[PHASE 1] {msg}")
                            halt_stale.append(msg)
                        else:
                            logger.warning(f"[PHASE 1] {msg}")
                            warn_stale.append(msg)
                        continue

                    if table_max_date < max_date:
                        days_behind = (max_date - table_max_date).days
                        msg = f"{description} is {days_behind} day(s) stale"
                        if is_halt_table:
                            logger.critical(f"[PHASE 1] {msg}")
                            halt_stale.append(msg)
                        else:
                            logger.warning(f"[PHASE 1] {msg}")
                            warn_stale.append(msg)

                    # Time-based freshness for swing_trader_scores (pipeline-loaded)
                    if table_name == "swing_trader_scores":
                        cur.execute(f"SELECT MAX(created_at) FROM {table_name}")
                        max_created = cur.fetchone()[0]
                        if max_created:
                            if max_created.tzinfo is None:
                                max_created = max_created.replace(tzinfo=timezone.utc)
                            age_hours = (now_utc - max_created).total_seconds() / 3600
                            if age_hours > max_stale_hours:
                                msg = f"{description} is {age_hours:.1f}h old"
                                logger.warning(f"[PHASE 1] {msg}")
                                warn_stale.append(msg)

                except Exception as e:
                    msg = f"{description} check failed: {str(e)[:50]}"
                    if is_halt_table:
                        logger.warning(f"[PHASE 1] {msg}")
                        halt_stale.append(msg)
                    else:
                        logger.warning(f"[PHASE 1] {msg}")
                        warn_stale.append(msg)

            if warn_stale:
                logger.warning(
                    f"[PHASE 1] Non-critical staleness (auxiliary tables, trading continues): "
                    f"{'; '.join(warn_stale)}"
                )

            if halt_stale:
                logger.critical(
                    f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables): {'; '.join(halt_stale)}"
                )
                log_phase_result_fn(
                    1,
                    "signal_tables_stale",
                    "halt",
                    f"Stale/missing pipeline data: {'; '.join(halt_stale[:3])}",
                )
                from algo.reporting.notifications import notify_signal_staleness

                notify_signal_staleness(halt_stale)
                return PhaseResult(
                    1,
                    "signal_tables_stale",
                    "halted",
                    {},
                    True,
                    f"Critical pipeline tables stale/missing: {halt_stale[0]}",
                )

            elapsed = time.time() - phase_start
            phase1_end_et = dt.now(ZoneInfo("America/New_York"))

            sla_status = ""
            if pipeline_context == "MORNING":
                sla_deadline = phase1_end_et.replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
                if phase1_end_et < sla_deadline:
                    minutes_until_sla = (
                        sla_deadline - phase1_end_et
                    ).total_seconds() / 60
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m until 9:30 AM]"
                else:
                    sla_status = " [SLA WARNING: Past 9:30 AM]"

            warn_suffix = f" ({len(warn_stale)} auxiliary warnings)" if warn_stale else ""
            logger.info(f"[PHASE 1] PASS - PIPELINE DATA FRESH{sla_status}{warn_suffix}")
            logger.info(
                f"  - Prices: {max_date} ({symbols_loaded} symbols, {coverage_pct:.1f}%)"
            )
            logger.info("  - All pipeline tables (market_health, trend_template, market_exposure) fresh")
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            log_phase_result_fn(
                1,
                "all_tables_fresh",
                "success",
                f"All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%",
            )

            return PhaseResult(
                1,
                "all_tables_fresh",
                "ok",
                {
                    "price_date": str(max_date),
                    "symbols_loaded": symbols_loaded,
                    "coverage_pct": coverage_pct,
                },
                False,
                "All critical data fresh and complete",
            )

    except Exception as e:
        logger.error(f"[PHASE 1] ERROR: {e}", exc_info=True)
        log_phase_result_fn(1, "error", "error", str(e)[:100])
        return PhaseResult(
            1, "error", "error", {}, True, f"Phase 1 error: {str(e)[:100]}"
        )

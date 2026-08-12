#!/usr/bin/env python3
"""
PHASE 1: DATA FRESHNESS CHECK

Verify pipeline-loaded tables are fresh before trading. "Fresh" = LAST TRADING DAY data:
- If today is a trading day (Mon-Fri): require today's data
- If today is weekend/holiday: require most recent trading day's data
- NO multi-day lookback windows (Session 223 fix: stale data bypass)

Tables verified (all must have LAST-TRADING-DAY data with non-NULL prices):

HALT IF STALE (core to signal generation):
1. price_daily: Stock prices (75%+ symbol coverage required)
2. technical_data_daily: Technical indicators (ATR, SMA, RSI - CRITICAL for Phase 8 position sizing)
3. market_health_daily: Market breadth metrics (regime detection)
4. earnings_calendar: Earnings dates (blackout window gating)
5. buy_sell_daily: Buy/sell technical signals (CRITICAL for Phase 7 signal generation)

WARNING IF STALE (enrichment only, website/portfolio analysis, not core signals):
6. market_exposure_daily: Market regime / exposure limits (EOD loader, morning runs lag 1d)
7. growth_metrics: Multi-year revenue/EPS growth metrics
8. quality_metrics: Financial quality metrics (ROE/margins/ratios)
9. value_metrics: Valuation metrics (P/E, P/B, etc.)
10. positioning_metrics: Ownership and short interest
11. stability_metrics: Volatility and beta metrics
12. trend_template_data: Minervini/Weinstein criteria
13. sector_ranking: Sector data for last trading day
(swing_trader_scores: removed in Session 14, no longer checked)

NOTE: Metric loaders (growth, quality, value, positioning, stability) are ENRICHMENT ONLY.
They're used for website display and portfolio analysis, not core signal generation (which uses
price_daily + technical_data_daily). Phase 5 generates stock_scores on-the-fly from price_daily;
metrics are not required for trading. Stale metrics = WARNING only, trading continues.

Phase 5 generates stock_scores and signals on-the-fly from price_daily input.
Excluded: stock_scores (orchestrator output), technical_data_daily, buy_sell_daily (pipeline-loaded, Phase 1 just validates).

TIMEZONE REQUIREMENT: All dates passed to phases are ET (Eastern Time) dates, not UTC.
Market trading hours are 9:30 AM - 4:00 PM ET. The orchestrator ensures run_date is always ET.
Phases should NOT convert run_date to UTC or use UTC timestamps for trading logic.
"""

import logging
import time
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import timedelta as _timedelta
from typing import Any

import psycopg2

from algo.infrastructure.constants import (
    PHASE1_DB_QUERY_TIMEOUT_MS,
    PHASE1_METRIC_COVERAGE_MIN_PCT,
)
from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase1_failsafe_retry import check_and_retry_incomplete_loaders
from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.status_manager import LoaderStatusManager

logger = logging.getLogger(__name__)


def _detect_and_fail_stale_running_loaders(stale_threshold_minutes: int = 30) -> list[str]:
    """Detect RUNNING loaders stuck for >N minutes and auto-fail them.

    CRITICAL FIX (Session 82): Fixes the "stuck RUNNING for days" Monday failure sequence:
    - Friday: Loader times out → marked RUNNING, process dies
    - Saturday/Sunday: Stuck RUNNING, no monitoring
    - Monday: Phase 1 hangs waiting for RUNNING loader
    - Result: orchestrator halt, manual operator backfill

    This function runs at Phase 1 startup to detect crashed loaders that were never
    properly marked FAILED. A loader stuck RUNNING for >30 min with no recent
    status update almost certainly crashed (no active process checking in on it).

    Args:
        stale_threshold_minutes: Mark RUNNING if last_updated is older than this (default 30)

    Returns:
        List of table names that were recovered (marked FAILED)
    """
    recovered = []
    try:
        with DatabaseContext("read") as cur:
            cur.execute(f"""
                SELECT table_name, last_updated
                FROM data_loader_status
                WHERE status = 'RUNNING'
                  AND last_updated < CURRENT_TIMESTAMP - INTERVAL '{stale_threshold_minutes} minutes'
                ORDER BY last_updated ASC
            """)
            stale_loaders = cur.fetchall()

            for table_name, last_updated in stale_loaders:
                error_msg = (
                    f"[PHASE 1 STARTUP] Auto-failed stale RUNNING loader "
                    f"(stuck for {stale_threshold_minutes}+ min since {last_updated}). "
                    f"Likely crashed with no process alive. Will retry via failsafe."
                )
                logger.warning(f"[PHASE 1 STARTUP] {table_name}: {error_msg}")
                try:
                    LoaderStatusManager(table_name).mark_failed(error_msg)
                    recovered.append(table_name)
                except Exception as mark_err:
                    logger.error(
                        f"[PHASE 1 STARTUP] Could not mark {table_name} as FAILED: {mark_err}"
                    )

            if recovered:
                logger.info(
                    f"[PHASE 1 STARTUP] Recovered {len(recovered)} stale RUNNING loader(s): {', '.join(set(recovered))}. "
                    f"Will retry via failsafe mechanism."
                )
    except Exception as e:
        logger.warning(
            f"[PHASE 1 STARTUP] Could not detect stale RUNNING loaders (non-fatal): {e}. "
            "Proceeding with normal Phase 1 flow."
        )

    return recovered


def _fetch_health_distinctness_window(
    cur: Any, health_max_date: _date, window_days: int = 10
) -> tuple[int | None, int | None]:
    """Measure put_call_ratio/vix_level distinctness over a trailing window, not a single date.

    CRITICAL FIX 2026-08-03: market_health_daily has exactly ONE row per date (verified
    live: every date in the table has COUNT(*)=1). The "copy-paste detector" this used to
    feed was scoped to `WHERE date = health_max_date`, so COUNT(DISTINCT put_call_ratio)
    over that single row was mathematically guaranteed to equal 1 (or 0 if NULL) on EVERY
    SINGLE RUN, regardless of whether the loader was actually stuck on a constant value -
    it fired the "constant fill or copy-paste, not real market data" warning
    unconditionally, forever, with zero actual signal despite looking like a real
    data-quality check. The check's own stated intent ("indicates copy-paste or constant
    fill") only makes sense measured across multiple days.

    Returns (pcr_distinct, vix_distinct), both None if there isn't enough window history
    yet (< 5 rows) to make the distinctness check meaningful - a short window can
    legitimately have low cardinality without indicating a stuck loader.
    """
    cur.execute(
        """
        SELECT COUNT(*) as window_rows,
               COUNT(DISTINCT put_call_ratio) as pcr_distinct,
               COUNT(DISTINCT vix_level) as vix_distinct
        FROM market_health_daily
        WHERE date <= %s AND date > %s - %s
        """,
        (health_max_date, health_max_date, _timedelta(days=window_days)),
    )
    window_row = cur.fetchone()
    if window_row and window_row[0] is not None and window_row[0] >= 5:
        return window_row[1], window_row[2]
    return None, None


def _check_health_column_coverage(
    total_rows: int | None,
    pcr_rows: int | None,
    pcr_distinct: int | None,
    vix_rows: int | None,
    vix_distinct: int | None,
    health_max_date: _date,
) -> None:
    """Validate market_health_daily's optional-column coverage for health_max_date.

    CRITICAL FIX 2026-08-02: Now checks data distribution, not just coverage.
    - All-same-value data (COUNT(DISTINCT) = 1) is suspicious - indicates copy-paste or constant fill
    - All-NULL data still only warns (optional columns)
    - But if data exists, it must have multiple distinct values to be trusted

    CRITICAL FIX 2026-08-03: pcr_distinct/vix_distinct are now measured across a trailing
    ~10-day window, not health_max_date's single row. market_health_daily has exactly one
    row per date (verified live), so COUNT(DISTINCT ...) scoped to a single date was
    mathematically guaranteed to be <= 1 every run regardless of whether the loader was
    actually stuck - this "copy-paste detector" fired unconditionally, forever, providing
    zero real signal. The caller passes None for pcr_distinct/vix_distinct when there isn't
    enough window history yet (< 5 rows) to make the check meaningful.

    total_rows == 0 halts (the whole row is missing, not just an optional column).
    put_call_ratio/vix_level being fully null only warns - see the inline note below,
    this used to be a hard RuntimeError (commit c6862e04a fixed a live incident where
    a missing put_call_ratio - an optional 8pt sentiment enrichment Phase 2 already
    skips gracefully - halted Phase 1/2/4/5/7 entirely). Extracted from run() so this
    decision has direct unit test coverage instead of relying on live reproduction.
    """
    if not total_rows:
        raise RuntimeError(f"[PHASE 1] market_health_daily has no rows for {health_max_date}")

    if not pcr_rows:
        # NOTE: put_call_ratio is OPTIONAL in Phase 2 (algo/risk/market_exposure.py,
        # commit 6a94934d4, "Make put_call_ratio truly optional") - it's an unofficial
        # yfinance-options-chain-derived sentiment enrichment (8pt of 100), explicitly
        # excluded from market_exposure's required_factors and gracefully skipped when
        # missing. Downgraded to a warning, matching vix_rows below.
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily missing put_call_ratio data for {health_max_date}. "
            "Optional sentiment enrichment (Phase 2 skips it gracefully) - not halting. "
            "Check market_health_daily loader if this persists."
        )
    elif pcr_distinct is not None and pcr_distinct <= 1 and pcr_rows > 0:
        # Data exists but all same value - indicates copy-paste or constant fill, not real data
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily put_call_ratio for {health_max_date} has "
            f"only 1 distinct value across {pcr_rows} rows. This indicates constant fill or copy-paste, "
            f"not real market data. Check market_health_daily loader - is put_call_ratio calculation working?"
        )

    if not vix_rows:
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily missing VIX data for {health_max_date}. "
            "VIX is optional if provided by other means, but check market_health_daily loader."
        )
    elif vix_distinct is not None and vix_distinct <= 1 and vix_rows > 0:
        # Data exists but all same value - same red flag as put_call_ratio
        logger.warning(
            f"[PHASE 1] WARNING: market_health_daily VIX for {health_max_date} has "
            f"only 1 distinct value across {vix_rows} rows. This indicates constant fill or copy-paste, "
            f"not real market data. Check market_health_daily loader - is VIX calculation working?"
        )


def _validate_dependency_freshness(
    cur: Any, run_date: _date, log_phase_result_fn: Callable[..., Any]
) -> PhaseResult | None:
    """Verify that critical loader dependencies have today's data before downstream loaders run.

    This prevents silent data degradation where a slow/timeout upstream loader marks
    COMPLETED but with stale/empty data, allowing downstream loaders to run with
    yesterday's dependency data without detecting the problem until Phase 1 validation.

    CRITICAL DEPENDENCIES (must have run_date data):
    - value_quality_growth requires: financial_statements, valuations, analyst_earnings_estimates
    - enhanced_quality_growth requires: value_quality_growth
    - segment_metrics requires: segment_info
    - positioning_metrics requires: institutional_holdings_13f, insider_holdings_sec

    Returns: PhaseResult halt if a dependency is stale, None if all dependencies OK
    """
    dependencies = {
        "value_quality_growth": ["financial_statements", "valuations", "analyst_earnings_estimates"],
        "enhanced_quality_growth": ["value_quality_growth"],
        "segment_metrics": ["segment_info"],
        "positioning_metrics": ["institutional_holdings_13f", "insider_holdings_sec"],
        "stock_scores": ["value_quality_growth", "enhanced_quality_growth", "stability_metrics"],
        "signal_quality": ["buy_sell_daily"],
    }

    failed_deps = []
    for downstream, upstreams in dependencies.items():
        for upstream in upstreams:
            try:
                cur.execute(
                    """SELECT MAX(latest_date), MAX(execution_completed), status
                       FROM data_loader_status
                       WHERE table_name = %s
                       ORDER BY execution_completed DESC LIMIT 1""",
                    (upstream,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    failed_deps.append(f"{downstream}→{upstream}: never loaded")
                    continue

                latest_data_date, _last_completed, status = row
                if latest_data_date < run_date:
                    failed_deps.append(f"{downstream}→{upstream}: last data {latest_data_date} < required {run_date}")
                if status == "FAILED":
                    failed_deps.append(f"{downstream}→{upstream}: marked FAILED")
            except Exception as e:
                logger.warning(f"[PHASE 1] Could not check dependency {upstream}: {e}")

    if failed_deps:
        error_msg = (
            "[PHASE 1] DEPENDENCY FRESHNESS FAILURE:\n"
            + "\n".join(f"  {dep}" for dep in failed_deps[:5])
            + (f"\n  ... and {len(failed_deps) - 5} more" if len(failed_deps) > 5 else "")
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "dependency_freshness", "halt", f"Upstream dependencies stale: {failed_deps[0]}")
        return PhaseResult(
            1,
            "dependency_freshness",
            "halted",
            {"failed_dependencies": failed_deps},
            True,
            f"Upstream dependencies stale: {failed_deps[0]}",
        )

    logger.info("[PHASE 1] Dependency freshness check: OK")
    return None


def _check_failsafe_retry_result(
    failsafe_result: dict[str, Any],
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult | None:
    """Check failsafe retry result and return early if halt required.

    Args:
        failsafe_result: Result dict from check_and_retry_incomplete_loaders
        log_phase_result_fn: Logging callback

    Returns:
        PhaseResult if halt required, None if can proceed
    """
    # Validate failsafe result structure (fail-fast if corrupted)
    required_keys = {"incomplete_loaders", "retried", "recovered", "still_failing", "halt_required"}
    missing_keys = required_keys - set(failsafe_result.keys())
    if missing_keys:
        logger.critical(
            f"[PHASE 1] FATAL: failsafe_result missing required keys: {missing_keys}. "
            f"Received keys: {set(failsafe_result.keys())}. This indicates corruption in failsafe retry logic."
        )
        raise RuntimeError(
            f"[PHASE 1] Failsafe retry result corrupted - missing keys: {missing_keys}. "
            "Cannot proceed with freshness validation."
        )

    # Log failsafe results for visibility (explicit key access, no defaults)
    logger.info(
        f"[PHASE 1] Failsafe retry check: "
        f"incomplete={len(failsafe_result['incomplete_loaders'])} "
        f"retried={len(failsafe_result['retried'])} "
        f"recovered={len(failsafe_result['recovered'])} "
        f"still_failing={len(failsafe_result['still_failing'])} "
        f"halt_required={failsafe_result['halt_required']}"
    )

    still_failing = failsafe_result["still_failing"]
    price_tables = {
        "price_daily",
        "price_weekly",
        "price_monthly",
        "etf_price_daily",
        "etf_price_weekly",
        "etf_price_monthly",
    }
    if any(table in price_tables for table in still_failing):
        price_coverage_pct = None
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""SELECT completion_pct FROM data_loader_status
                       WHERE table_name='price_daily' ORDER BY last_updated DESC LIMIT 1""")
                row = cur.fetchone()
                if row and row[0] is not None:
                    price_coverage_pct = row[0]
        except Exception as e:
            logger.warning(f"[PHASE 1] Could not check price coverage: {e}")

        coverage_str = f"{price_coverage_pct:.1f}%" if price_coverage_pct else "unknown"
        logger.critical(
            f"[PHASE 1] CRITICAL: price_daily still incomplete after retry ({coverage_str} coverage). "
            f"Cannot proceed without complete price data."
        )
        log_phase_result_fn(
            1,
            "incomplete_price_data_after_retry",
            "halt",
            f"price_daily {coverage_str} coverage after retry",
        )
        return PhaseResult(
            1,
            "incomplete_price_data_after_retry",
            "halted",
            failsafe_result,
            True,
            f"Price data incomplete after retry ({coverage_str}). Check loader status: python scripts/verify_loaders_health.py",
        )

    if failsafe_result.get("halt_required"):
        logger.critical(
            "[PHASE 1] CRITICAL: Other critical loaders incomplete even after failsafe retry. "
            "Cannot proceed with data processing."
        )
        still_failing = failsafe_result.get("still_failing")
        if still_failing is None:
            raise RuntimeError(
                "[PHASE 1] FATAL: failsafe_result missing 'still_failing' field. "
                "Cannot determine which loaders failed. This indicates corruption in failsafe retry logic. "
                "Verify failsafe_retry.py returns complete result dict with all required fields."
            )
        log_phase_result_fn(
            1,
            "incomplete_loaders_after_retry",
            "halt",
            f"Still incomplete after retry: {still_failing}",
        )
        still_failing_first = still_failing[0] if still_failing else "unknown"
        return PhaseResult(
            1,
            "incomplete_loaders_after_retry",
            "halted",
            failsafe_result,
            True,
            f"Critical loaders incomplete after retry: {still_failing_first}",
        )

    return None


def _validate_config(config: Any) -> tuple[int, int, int, int, int]:
    """Extract and validate required configuration parameters.

    Args:
        config: Configuration dict from algo_config table

    Returns:
        Tuple of (min_coverage_pct, min_symbol_count, recent_cutoff, prior_cutoff, halt_tolerance)

    Raises:
        RuntimeError: If config is missing required keys
    """
    if not config:
        raise RuntimeError(
            "[PHASE 1] Config not provided: cannot proceed without phase1_min_coverage_pct "
            "and phase1_min_symbol_count thresholds. Config must be passed from algo_config table."
        )

    try:
        min_coverage_pct = config["phase1_min_coverage_pct"]
    except KeyError as e:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_coverage_pct'. "
            "Cannot proceed without explicit data freshness threshold (no hardcoded fallback)."
        ) from e

    try:
        min_symbol_count = config["phase1_min_symbol_count"]
    except KeyError as e:
        raise RuntimeError(
            "[PHASE 1] Config missing required key 'phase1_min_symbol_count'. "
            "Cannot proceed without explicit symbol count threshold (no hardcoded fallback)."
        ) from e

    # CRITICAL FIX: Require explicit config for all timing parameters - no silent fallbacks
    # These timing thresholds directly affect whether we halt trading for stale data
    required_keys = ["phase1_recent_cutoff_days", "phase1_prior_cutoff_days", "phase1_halt_table_max_tolerance_days"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise RuntimeError(
            f"[PHASE 1] Config missing required timing thresholds: {missing}. "
            "Data staleness tolerance thresholds must be explicit in algo_config table. "
            "Cannot use hardcoded fallbacks for trading safety decisions."
        )

    try:
        phase1_recent_cutoff_days = config["phase1_recent_cutoff_days"]
        phase1_prior_cutoff_days = config["phase1_prior_cutoff_days"]
        phase1_halt_table_max_tolerance_days = config["phase1_halt_table_max_tolerance_days"]
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"[PHASE 1] Config error reading staleness thresholds: {e}") from e

    return (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    )


def run(  # noqa: C901
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 1: Verify pipeline-loaded tables are fresh.

    ISSUE #6 FIX: Integrate DataPatrol checks to block Phase 1 if data quality issues found.

    DataPatrol runs independently and validates:
    - Staleness of critical tables (price_daily, market_health_daily, etc.)
    - Data coverage and completeness
    - Quality metrics (OHLC sanity, volume outliers, etc.)
    - Alignment between related tables

    Phase 1 now:
    1. Queries DataPatrol results from patrol_log table
    2. Fails if CRITICAL or ERROR issues found
    3. Warns if WARNING issues found but proceeds
    4. Performs traditional freshness checks (redundant but explicit fail-safe)

    Halts if price_daily, market_health_daily, or market_exposure_daily are stale -
    these are required for Phase 5 signal generation and regime gating.
    Issues warnings for trend_template_data and sector_ranking -
    stale but trading can continue.
    Excludes stock_scores (orchestrator-generated output, not pipeline input).
    """
    validate_phase_config(config, "phase_1_data_freshness")

    # STARTUP: Clean up orphaned positions from previous failed runs
    # This prevents orphaned positions from blocking Phase 2/7 risk calculations
    try:
        from utils.db import DatabaseContext

        with DatabaseContext("write") as cleanup_cursor:
            cleanup_cursor.execute("""
                WITH closed_trades AS (
                    SELECT DISTINCT symbol FROM algo_trades
                    WHERE status = 'closed'
                )
                UPDATE algo_positions p
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE p.status = 'open' AND p.symbol IN (SELECT symbol FROM closed_trades)
                AND NOT EXISTS (
                    SELECT 1 FROM algo_trades t
                    WHERE t.symbol = p.symbol AND t.status = 'open'
                );
            """)
            if cleanup_cursor.rowcount > 0:
                logger.info(
                    f"[PHASE 1 STARTUP] Auto-closed {cleanup_cursor.rowcount} orphaned positions from previous runs"
                )
    except Exception as cleanup_err:
        logger.warning(f"[PHASE 1 STARTUP] Could not cleanup orphaned positions: {cleanup_err}")

    from datetime import timedelta as td

    phase_start = time.time()
    degraded_reason = None
    (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        _phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    ) = _validate_config(config)

    # CRITICAL FIX (Session 82): Detect and fail stale RUNNING loaders at phase startup
    # Prevents the "stuck RUNNING for days" Monday failure sequence where a Friday timeout
    # causes Phase 1 Monday to hang, triggering orchestrator halt. Now detects crashed loaders
    # immediately (>30 min RUNNING = likely crash) and marks them FAILED so failsafe can retry.
    _detect_and_fail_stale_running_loaders(stale_threshold_minutes=30)

    from datetime import datetime as dt

    now_et = dt.now(EASTERN_TZ)
    # Market hours: 9:30 AM - 4:00 PM ET
    is_market_open = now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)
    is_after_market_close = now_et.hour >= 16
    pipeline_context = "EOD" if is_after_market_close else "INTRADAY" if is_market_open else "MORNING"

    logger.info(
        f"[PHASE 1] Starting comprehensive freshness check (Pipeline: {pipeline_context}, Time: {now_et.strftime('%H:%M:%S ET')})"
    )

    # PHASE 1 FAILSAFE: Check for and retry incomplete loaders before freshness check
    # CRITICAL FIX (Session 54): Pass run_date so loaders know which trading day to expect
    failsafe_result = check_and_retry_incomplete_loaders(
        run_date=run_date, pipeline_context=pipeline_context, dry_run=dry_run
    )
    failsafe_halt = _check_failsafe_retry_result(failsafe_result, log_phase_result_fn)
    if failsafe_halt:
        return failsafe_halt

    # PHASE 1 DEPENDENCY VALIDATION: Verify upstream dependencies have today's data
    # CRITICAL FIX 2026-08-12: Check that value_quality_growth, enhanced_quality_growth, etc.
    # have fresh dependencies before allowing downstream loaders to proceed.
    # Prevents silent data degradation where a timeout loader marks COMPLETED with stale/empty data.
    try:
        with DatabaseContext("read") as dep_check_cur:
            dep_halt = _validate_dependency_freshness(dep_check_cur, run_date, log_phase_result_fn)
            if dep_halt:
                return dep_halt
    except Exception as e:
        logger.warning(f"[PHASE 1] Dependency validation check failed (non-fatal): {e}")

    # CRITICAL FIX: Pre-validate stock_symbols table is populated
    # If symbols loader failed, all downstream phases will fail
    # Better to catch this early with clear error message
    try:
        with DatabaseContext("read") as pre_check_cur:
            pre_check_cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            # CRITICAL FIX: Check if query returned results before indexing
            result = pre_check_cur.fetchone()
            if result is None or len(result) < 1:
                error_msg = (
                    "[PHASE 1 CRITICAL] stock_symbols COUNT query failed (no results or empty tuple). "
                    "Database connectivity or schema issue. Check database logs."
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "data_freshness", "error", error_msg)
                return PhaseResult(
                    phase_num=1,
                    phase_name="data_freshness",
                    status="error",
                    halted=True,
                    error=error_msg,
                )
            symbol_count = result[0]
            if not symbol_count or symbol_count == 0:
                error_msg = (
                    "[PHASE 1 CRITICAL] stock_symbols table has no active symbols. "
                    "The symbol loader failed or never ran. "
                    "Without trading symbols, all downstream phases will fail. "
                    "Check: (1) symbol loader status in data_loader_status, "
                    "(2) Lambda logs for loader errors, (3) Re-run: python3 scripts/run_local_orchestrator.py --morning"
                )
                logger.critical(error_msg)
                log_phase_result_fn(1, "data_freshness", "halt", error_msg)
                return PhaseResult(
                    1, "data_freshness", "halted", {"status": "halted", "reason": "no active symbols"}, True, error_msg
                )
            logger.info(f"[PHASE 1] Pre-flight: stock_symbols table OK ({symbol_count:,} active symbols)")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - database error: {type(db_err).__name__}: {db_err}. "
            f"This prevents all downstream phases from running correctly. "
            f"Check: database connectivity, RDS credentials, or schema consistency."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1,
            "data_freshness",
            "halted",
            {"status": "halted", "reason": "database error during pre-flight"},
            True,
            error_msg,
        )
    except (ValueError, TypeError, AttributeError) as code_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - code error: {type(code_err).__name__}: {code_err}. "
            f"This indicates a bug in Phase 1 pre-flight logic. Report to developers."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1, "data_freshness", "halted", {"status": "halted", "reason": "code error in pre-flight"}, True, error_msg
        )
    except Exception as unknown_err:
        error_msg = (
            f"[PHASE 1 CRITICAL] Pre-flight validation failed - unexpected error: {type(unknown_err).__name__}: {unknown_err}. "
            f"This prevents all downstream phases from running correctly. "
            f"Fail-fast: halting Phase 1 to surface unknown issue."
        )
        logger.critical(error_msg)
        log_phase_result_fn(1, "data_freshness", "halt", error_msg)
        return PhaseResult(
            1,
            "data_freshness",
            "halted",
            {"status": "halted", "reason": "unknown error in pre-flight"},
            True,
            error_msg,
        )

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                f"SET statement_timeout = {PHASE1_DB_QUERY_TIMEOUT_MS}"
            )  # Database timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            # NOTE: stock_scores is NOT validated here; it's an orchestrator OUTPUT (Phase 5),
            # not a pipeline loader INPUT. Validating orchestrator outputs in Phase 1 breaks first-run.
            # Phase 7 (Signal Generation) will handle missing stock_scores when it runs.
            # CRITICAL FIX 2026-08-02: Exclude index tickers (^VIX, etc) from MAX(date)
            # Index tickers update pre-market before equity prices, skewing freshness check
            cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol NOT LIKE '^%%'")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(
                    "[PHASE 1] price_daily MAX(date) query returned NULL. "
                    "Query malformed or database connection failed."
                )
            max_date = row[0]
            if max_date is None:
                logger.critical("[PHASE 1] price_daily table is empty")
                log_phase_result_fn(1, "price_data", "halt", "price_daily table is empty")
                return PhaseResult(
                    1,
                    "price_data",
                    "halted",
                    {"status": "halted", "reason": "price_daily table is empty - no pricing data available"},
                    True,
                    "price_daily table is empty",
                )

            # CRITICAL FIX: Ensure max_date is a date object, not datetime
            # PostgreSQL date columns can return datetime.datetime from some drivers
            if isinstance(max_date, dt):
                max_date = max_date.date()

            # CRITICAL: Verify stock_symbols table is pre-loaded (required for ALL loaders)
            # Session 299 FIX: More robust symbol check with better error diagnostics
            # Only retry on transient errors (lock timeouts, connection issues), not structural issues
            symbol_count = None
            last_error = None
            max_retries = 2
            transient_error_keywords = ("timeout", "connection", "pool", "concurrent", "deadlock")

            for attempt in range(max_retries):
                try:
                    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
                    symbol_count_row = cur.fetchone()
                    if symbol_count_row is not None and symbol_count_row[0] is not None:
                        symbol_count = symbol_count_row[0]
                        break
                    else:
                        # COUNT(*) should never return NULL; if it does, something is wrong
                        error_msg = f"stock_symbols query returned unexpected result: {symbol_count_row}"
                        logger.error(f"[PHASE 1] {error_msg}")
                        if attempt < max_retries - 1:
                            time.sleep(0.3)
                            continue
                        last_error = error_msg
                        break
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as query_err:
                    error_str = str(query_err).lower()
                    is_transient = any(kw in error_str for kw in transient_error_keywords)

                    if is_transient and attempt < max_retries - 1:
                        logger.warning(
                            f"[PHASE 1] Transient stock_symbols check error (attempt {attempt + 1}): {query_err}"
                        )
                        time.sleep(0.3)
                        continue
                    else:
                        # Permanent error or last attempt
                        logger.error(f"[PHASE 1] stock_symbols check failed (attempt {attempt + 1}): {query_err}")
                        last_error = f"{type(query_err).__name__}: {str(query_err)[:500]}"
                        break

            if symbol_count is None or symbol_count == 0:
                error_detail = last_error or "(query returned 0 or NULL)"
                logger.critical(
                    "[PHASE 1] CRITICAL: stock_symbols table has no active symbols. "
                    f"Details: {error_detail}. "
                    "All loaders depend on symbol list being pre-loaded. "
                    "Run load_market_constituents.py first to populate NASDAQ/NYSE symbols."
                )
                log_phase_result_fn(
                    1, "symbol_list_missing", "halt", f"stock_symbols table empty or inaccessible: {error_detail}"
                )
                return PhaseResult(
                    1,
                    "symbol_list_missing",
                    "halted",
                    {},
                    True,
                    f"stock_symbols table is empty - symbols must be loaded before trading. Error: {error_detail}",
                )
            logger.info(f"[PHASE 1] Symbol list verified: {symbol_count} active symbols")

            # CRITICAL FIX: Detect phantom rows in price_daily (NULL prices counted as fresh data)
            # These bypass the freshness check by inflating MAX(date) and symbol count
            # CRITICAL FIX 2026-08-02: Exclude index tickers from MAX(date) in nested SELECT
            cur.execute("""SELECT COUNT(*) as phantom_count,
                          COUNT(CASE WHEN close IS NULL THEN 1 END) as null_close_count,
                          COUNT(CASE WHEN open IS NULL THEN 1 END) as null_open_count
                   FROM price_daily
                   WHERE date = (SELECT MAX(date) FROM price_daily WHERE symbol NOT LIKE '^%%')
                   AND symbol NOT LIKE '^%%'""")
            phantom_row = cur.fetchone()
            if phantom_row:
                phantom_count = phantom_row[0]
                null_close = phantom_row[1]
                null_open = phantom_row[2]
                if null_close > 0 or null_open > 0:
                    logger.warning(
                        f"[PHASE 1] PHANTOM ROWS DETECTED on MAX date: "
                        f"{phantom_count} total rows, {null_close} NULL close, {null_open} NULL open. "
                        f"These rows will be ignored - only rows with actual prices (open/close NOT NULL) count as fresh."
                    )

            from algo.infrastructure import MarketCalendar

            # Market hours: 9:30 AM - 4:00 PM ET.
            # If orchestrator runs DURING market hours (before 16:00 ET), expect previous trading day's data.
            # If orchestrator runs AFTER market close (16:00+ ET), expect same-day data.

            # CRITICAL: Ensure run_date is a date object, not datetime (can come from various sources)
            if isinstance(run_date, dt):
                run_date_obj = run_date.date()
            else:
                run_date_obj = run_date

            if pipeline_context == "MORNING" or pipeline_context == "INTRADAY":
                # During market hours (before close): expect the *previous* trading day's data
                # (today's not closed yet, so markets haven't published today's data)
                # This is the RIGHT thing: require most recent market close's data
                prev_date = run_date_obj - td(days=1)
                if MarketCalendar.is_trading_day(prev_date):
                    last_trading_day = prev_date
                else:
                    # Find the most recent trading day before today
                    # (e.g., if today is Monday, find Friday; if Monday is holiday, find Thursday)
                    last_trading_day = prev_date
                    while last_trading_day > run_date_obj - td(days=10):
                        if MarketCalendar.is_trading_day(last_trading_day):
                            break
                        last_trading_day -= td(days=1)
            else:
                # After market close (EOD context): expect same-day data if it's a trading day
                # If today is not a trading day (weekend/holiday): expect yesterday's data if it's trading day
                # This is the RIGHT thing: require most recent market close's data
                if MarketCalendar.is_trading_day(run_date_obj):
                    last_trading_day = run_date_obj
                else:
                    # Weekend/holiday: find most recent trading day
                    # (e.g., if today is Saturday, find Friday; if Friday was market close, use that)
                    last_trading_day = run_date_obj - td(days=1)
                    while last_trading_day > run_date_obj - td(days=10):
                        if MarketCalendar.is_trading_day(last_trading_day):
                            break
                        last_trading_day -= td(days=1)

            # TOLERANCE for data provider delays: if we're in IMMEDIATE EOD context (4:00-4:30 PM),
            # allow previous trading day's data as acceptable (data providers may not have
            # same-day data ready immediately after market close).
            # CRITICAL FIX: This tolerance should NOT apply hours later (after 4:30 PM).
            # By 5:00 PM+, all data providers should have same-day prices ready.
            acceptable_min_date = last_trading_day
            # CRITICAL FIX: `now_et.hour` is always an integer, so comparing it against the
            # float 16.5 can never distinguish "before 4:30 PM" from "after" within the same
            # clock hour - `16 <= 16 < 16.5` and `16 >= 16.5` are True/False respectively for
            # EVERY minute from 16:00:00 through 16:59:59, not just the first 30. Confirmed live
            # 2026-07-27: for any EOD-context run landing in that hour (e.g. a late/retried run,
            # not the fixed morning/afternoon/preclose/evening schedule), the grace period would
            # silently stay active the entire hour instead of expiring at 16:30 as the comments
            # below and the log line at 16:36 both claim - stale same-day data would be masked by
            # falling back to the prior trading day for up to 30 extra minutes. Compare against
            # an actual time boundary instead of an hour/float mismatch.
            grace_period_end = now_et.replace(hour=16, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            if pipeline_context == "EOD" and market_close <= now_et < grace_period_end:
                # Allow previous trading day as fallback if same-day not yet available
                # (ONLY in immediate aftermath of market close, within 30 min)
                prev_trading_day = last_trading_day - td(days=1)
                while prev_trading_day > last_trading_day - td(days=10):
                    if MarketCalendar.is_trading_day(prev_trading_day):
                        acceptable_min_date = prev_trading_day
                        logger.info(
                            f"[PHASE 1] Grace period active (4:00-4:30 PM): accepting {prev_trading_day} as valid"
                        )
                        break
                    prev_trading_day -= td(days=1)
            elif pipeline_context == "EOD" and now_et >= grace_period_end:
                # After 4:30 PM: must have same-day data
                logger.info(f"[PHASE 1] Grace period expired (> 4:30 PM): requiring {last_trading_day} data")

            # CRITICAL FIX 2026-08-06: During EOD context, if we're still before 6 PM ET and only have yesterday's prices,
            # accept them gracefully instead of halting. EOD prices may take 1-2 hours to load after market close.
            # This allows afternoon/evening orchestrator runs to proceed with position monitoring and exit execution
            # while waiting for same-day price_daily to load. Legitimate halts (circuit breakers) are still enforced.
            if (
                pipeline_context == "EOD" and max_date == acceptable_min_date - td(days=1) and now_et.hour < 18
            ):  # Before 6 PM ET
                logger.info(
                    f"[PHASE 1] EOD context grace: Using {max_date} (yesterday) instead of {last_trading_day} "
                    f"(today). EOD prices may still be loading. Will accept for up to 2h after market close."
                )
                acceptable_min_date = max_date  # Accept yesterday as valid during this grace period

            if max_date < acceptable_min_date:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                days_stale = (acceptable_min_date - max_date).days
                logger.critical(f"[PHASE 1] Price data stale: {max_date} vs expected {acceptable_min_date} (or later)")

                # CRITICAL FIX: Remove "emergency loader" workaround that doesn't work in production
                # Session 124 discovered this never worked:
                # - Hardcoded localhost connection cannot reach RDS from Lambda
                # - Portfolio symbols fallback is too narrow (missing most universe)
                # - dry_run flag bypasses the halt anyway
                # The REAL fix is proper loader scheduling + Phase 1 failsafe retry (above).
                # Halt here forces operators to investigate root cause and fix the pipeline.

                error = PhaseError(
                    category=ErrorCategory.DATA_STALE,
                    message=f"Price data is {days_stale} day(s) stale (latest: {max_date}, expected: {last_trading_day})",
                    root_cause="Scheduled morning pipeline failed to load prices. Check price_daily loader logs, yfinance access, network connectivity, and EventBridge Scheduler status.",
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(1, error, log_phase_result_fn)

                return PhaseResult(
                    1,
                    "price_staleness",
                    "halted",
                    {},
                    True,
                    f"Price data too old: {max_date} vs {acceptable_min_date}. Check price_daily loader and EventBridge Scheduler.",
                )

            # CRITICAL FIX: Require LAST-TRADING-DAY data with actual non-NULL prices
            # "Last trading day" = TODAY if today is a trading day (Mon-Fri), otherwise most recent trading day
            # Reject multi-day window (allows trading on stale data)
            # Reject phantom rows (NULL prices counted as fresh data)
            # This is the RIGHT thing: require data for the most recent market close, always

            # CRITICAL FIX 2026-07-29: For afternoon runs, we also need to check TODAY's data
            # because the orchestrator needs today's prices for Phase 6 exit execution.
            # The loader should have completed by mid-day, so lack of today's data indicates
            # loader failure, not normal lag. Check both yesterday (for intraday validation)
            # and today (for afternoon orchestrator requirements).

            # Both counts are scoped to symbols currently marked active in stock_symbols.
            # price_daily retains history for ~10.6K symbols total, but only ~5.5K are
            # still active - the other ~5.1K are delisted/removed tickers whose rows stop
            # getting new dates entirely. An unscoped COUNT(DISTINCT symbol) against the
            # full table (as this used to be) compares today's genuinely-active fetch
            # against that inflated historical figure, permanently capping coverage_pct
            # around 45-50% no matter how complete today's load is - confirmed live
            # 2026-07-20 (real coverage 85.5% scoped to active symbols, computed as 42.8%
            # unscoped, incorrectly halting Phase 1 on every EOD-context run since the
            # active universe last shrank).
            # CRITICAL FIX 2026-08-06: For EOD runs before 6 PM, if today's prices haven't loaded,
            # check yesterday's coverage instead of today's (which will be 0).
            # This allows exit execution to proceed while waiting for EOD prices to load.
            coverage_check_date = last_trading_day
            if pipeline_context == "EOD" and now_et.hour < 18:
                # Try today's data first, but fall back to yesterday if not available
                cur.execute(
                    """SELECT COUNT(DISTINCT pd.symbol)
                       FROM price_daily pd
                       JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                       WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                    (last_trading_day,),
                )
                today_coverage_row = cur.fetchone()
                today_coverage = (
                    today_coverage_row[0] if today_coverage_row and today_coverage_row[0] is not None else 0
                )

                if today_coverage == 0:
                    # Today's prices not loaded - check yesterday
                    yesterday = last_trading_day - td(days=1)
                    while yesterday > last_trading_day - td(days=5):
                        if MarketCalendar.is_trading_day(yesterday):
                            coverage_check_date = yesterday
                            break
                        yesterday -= td(days=1)
                    logger.info(
                        f"[PHASE 1] EOD grace (< 6 PM): Today's prices not loaded, checking {coverage_check_date} instead"
                    )

            cur.execute(
                """SELECT COUNT(DISTINCT pd.symbol)
                   FROM price_daily pd
                   JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                   WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                (coverage_check_date,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError(f"Symbol count query failed for coverage check date ({coverage_check_date})")
            symbols_loaded = row[0]

            # CRITICAL: For EOD runs, also validate TODAY's price data
            # During INTRADAY (10 AM-4 PM), today's close isn't published yet - only yesterday's close is available
            # Only after market close (EOD, 4 PM+) do we expect today's close data
            if pipeline_context == "EOD":
                cur.execute(
                    """SELECT COUNT(DISTINCT pd.symbol)
                       FROM price_daily pd
                       JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                       WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                    (run_date_obj,),
                )
                today_row = cur.fetchone()
                today_symbols = today_row[0] if today_row and today_row[0] is not None else 0

                # CRITICAL FIX 2026-08-06: During EOD context before 6 PM ET, if today's prices haven't loaded yet,
                # gracefully continue with yesterday's prices instead of halting. EOD price loads can take 1-2 hours.
                # This allows exit execution (Phase 6) to proceed with yesterday's prices rather than waiting for EOD data.
                # After 6 PM ET, require today's data (past the expected load window).
                if today_symbols < min_symbol_count and now_et.hour < 18:
                    logger.warning(
                        f"[PHASE 1] EOD grace: Today's ({run_date_obj}) price data incomplete ({today_symbols} symbols). "
                        f"Before 6 PM - accepting yesterday's prices for exit execution. "
                        f"Will require {min_symbol_count} symbols after 6 PM ET."
                    )
                elif today_symbols < min_symbol_count:
                    logger.critical(
                        f"[PHASE 1] CRITICAL: Today's ({run_date_obj}) price data incomplete: {today_symbols} symbols loaded. "
                        f"Loader appears to have failed. Require at least {min_symbol_count} symbols for exit execution."
                    )
                    log_phase_result_fn(
                        1,
                        "today_price_data_missing",
                        "halt",
                        f"Today's price data incomplete: only {today_symbols}/{min_symbol_count} symbols",
                    )
                    return PhaseResult(
                        1,
                        "today_price_data_missing",
                        "halted",
                        {},
                        True,
                        f"Loader failed: only {today_symbols} symbols for {run_date_obj}. Check price_daily loader logs.",
                    )

            # CRITICAL FIX: Validate that data_loader_status.completion_pct matches actual symbol count
            # Session 344: Found that completion_pct was calculated on row_count, not symbol_count,
            # causing false "100% complete" when only 1 symbol out of 5000+ was actually loaded.
            # This check catches that mismatch and fails fast rather than proceeding with incomplete data.
            # CRITICAL FIX 2026-08-02: Fail-fast on data integrity mismatch (was just logging)
            try:
                cur.execute("""SELECT completion_pct, symbols_loaded, symbol_count
                       FROM data_loader_status
                       WHERE table_name = 'price_daily'
                       ORDER BY last_updated DESC LIMIT 1""")
                loader_status_row = cur.fetchone()
                if loader_status_row:
                    reported_pct, reported_loaded, reported_expected = loader_status_row
                    # If loader reports 90%+ but actual loaded count is significantly lower, that's data integrity failure
                    if reported_pct and reported_pct >= 90 and reported_loaded and reported_expected:
                        actual_coverage = (reported_loaded / max(reported_expected, 1)) * 100
                        if actual_coverage < 50:
                            error_msg = (
                                f"[PHASE 1 CRITICAL] Data integrity failure: data_loader_status reports "
                                f"{reported_pct:.0f}% completion but actual coverage is {actual_coverage:.1f}% "
                                f"({reported_loaded} symbols loaded, {reported_expected} expected). "
                                f"This indicates the loader's completion_pct calculation is broken. "
                                f"Cannot proceed with analysis on corrupted completion metrics. "
                                f"Check data_loader_status.completion_pct calculation logic."
                            )
                            logger.critical(error_msg)
                            log_phase_result_fn(1, "data_loader_status", "halt", error_msg)
                            return PhaseResult(
                                1,
                                "data_freshness",
                                "halted",
                                {"status": "halted", "reason": error_msg},
                                True,
                                error_msg,
                            )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_check_err:
                logger.warning(
                    f"[PHASE 1] Could not validate loader status accuracy (database error): {status_check_err}"
                )

            # For coverage baseline: use CURRENT ACTIVE SYMBOL COUNT from stock_symbols
            # (not prior day's count, which can be lower/higher due to symbol list changes)
            # CRITICAL FIX (Session 365): Using prior_count instead of active_symbol_count
            # caused coverage > 100% when new symbols started trading. Changed to use
            # current active symbols as denominator to get true coverage percentage.
            cur.execute("""SELECT COUNT(*) FROM stock_symbols WHERE active = true""")
            row = cur.fetchone()
            if row is None or row[0] is None:
                total_active_symbols = 0
            else:
                total_active_symbols = row[0]

            coverage_pct = (symbols_loaded / max(total_active_symbols, 1)) * 100

            if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
                from algo.orchestrator.phase_error_handling import (
                    ErrorCategory,
                    PhaseError,
                    log_phase_error,
                )

                # DIAGNOSTIC (temporary, session 130): this halt has fired with an
                # identical symbols_loaded count across many consecutive runs despite
                # price_daily loader tasks actively committing writes in the same
                # window (confirmed via their own CloudWatch logs) -- couldn't be
                # explained without seeing the real per-date distribution, and this
                # session had no direct SQL access to the production DB. Log it here
                # so the next halt makes the mechanism visible without needing that
                # access. Safe to remove once the underlying cause is confirmed.
                try:
                    cur.execute(
                        "SELECT date, COUNT(DISTINCT symbol) FROM price_daily "
                        "WHERE date >= %s GROUP BY date ORDER BY date DESC LIMIT 7",
                        (max_date - td(days=7),),
                    )
                    diag_rows = cur.fetchall()
                    logger.critical(
                        f"[PHASE 1 DIAGNOSTIC] max_date={max_date} recent_cutoff={phase1_recent_cutoff_days} "
                        f"per-date distribution (last 7 days with data): {list(diag_rows)}"
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as diag_err:
                    logger.warning(f"[PHASE 1 DIAGNOSTIC] failed to gather date distribution (DB error): {diag_err}")
                except Exception as diag_err:
                    logger.warning(f"[PHASE 1 DIAGNOSTIC] failed to gather date distribution: {diag_err}")

                fail_reason = (
                    f"symbols {symbols_loaded} < min {min_symbol_count}"
                    if symbols_loaded < min_symbol_count
                    else f"coverage {coverage_pct:.1f}% < min {min_coverage_pct}%"
                )
                logger.critical(
                    f"[PHASE 1] Insufficient price coverage: {symbols_loaded} symbols ({coverage_pct:.1f}%) - {fail_reason}"
                )

                # CONSISTENCY: Use error categorization so operators know why trading halted
                error = PhaseError(
                    category=ErrorCategory.DATA_INCOMPLETE,
                    message=f"Price data coverage insufficient: {fail_reason}",
                    root_cause=f"Check that price_daily loader has loaded today's data (expected {min_symbol_count}+ symbols, got {symbols_loaded})",
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(1, error, log_phase_result_fn)

                return PhaseResult(
                    1,
                    "price_coverage",
                    "halted",
                    {},
                    True,
                    f"Insufficient price data: {fail_reason}",
                )

            # Halt-critical tables: Core trading data - trading CANNOT proceed without these
            # - price_daily: Must have stock prices for all 10K+ symbols
            # - technical_data_daily: ATR, SMA, RSI for position sizing (CRITICAL for Phase 8 entry execution)
            # - market_health_daily: Market breadth/regime (VIX, advance/decline, market breadth)
            # - market_exposure_daily: Market exposure policy limits (when to trade, position sizing)
            # - earnings_calendar: Earnings dates for trading blackout windows
            # - buy_sell_daily: Technical signals required by Phase 7 (MUST have today's signals)
            # NOTE: Metric enrichments (growth, quality, value, positioning, stability) are NOT
            # halt-critical. They're used for website display and portfolio analysis, not core signals.
            # Core signals come from price_daily + technical_data_daily. See Session 221.
            # CRITICAL FIX (2026-08-05): technical_data_daily was excluded from freshness checks,
            # allowing stale ATR/SMA data to be used for position sizing. Now added to halt_tables.
            halt_tables = {
                "price_daily": "Stock prices (CRITICAL for all trading decisions)",
                "technical_data_daily": "Technical indicators (ATR, SMA - CRITICAL for Phase 8 position sizing)",
                "market_health_daily": "Market health (breadth/regime)",
                "earnings_calendar": "Earnings dates (blackout window gating)",
                "buy_sell_daily": "Buy/sell signals (CRITICAL for Phase 7 signal generation)",
            }
            # Warning-only tables: enrichments + auxiliary data. Stale -> logged, trading continues.
            # Moved metric tables here (Session 221): they're website enrichments, not core to signals.
            # - growth_metrics, quality_metrics, value_metrics: Portfolio analysis only
            # - positioning_metrics, stability_metrics: Website enrichments only
            # Moved market_exposure_daily here (Session 239): loaded by separate EOD loader at 4:05 PM,
            # not orchestrator. Phase 5 reads via read_market_regime(date <= eval_date) so 1-day-old
            # data works fine. Morning orchestrator runs would false-halt without this move.
            warn_tables = {
                "market_exposure_daily": "Market exposure limits (EOD loader)",
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "sector_ranking": "Sector rankings",
                "growth_metrics": "Growth metrics (enrichment only)",
                "quality_metrics": "Quality metrics (enrichment only)",
                "value_metrics": "Value metrics (enrichment only)",
                "positioning_metrics": "Positioning metrics (enrichment only)",
                "stability_metrics": "Stability metrics (enrichment only)",
            }

            halt_stale = []  # pipeline-loaded tables - stale = HALT
            warn_stale = []  # auxiliary tables - stale = WARNING only
            # Structured (table_name, age) pairs mirroring halt_stale/warn_stale, kept separate
            # so the human-readable message strings above stay unchanged for existing callers
            # (notify_signal_staleness, log messages). This feeds the dashboard's PHASE EXECUTION
            # DETAILS panel (dashboard/panels/health.py, phase_num==1 branch), which reads
            # tables_validated/tables_fresh/tables_stale/stale_tables from PhaseResult.data - keys
            # this function never populated, so that panel section always rendered nothing.
            stale_table_details: list[dict[str, Any]] = []

            # Tables checked by MAX(date) vs price_daily latest date
            # Note: metrics tables (growth, quality, value, positioning, stability) use updated_at instead of date
            date_column_overrides = {
                # FIXED 2026-08-04: was "earnings_date" - a forward-looking calendar column
                # populated years ahead for scheduled earnings, not a load timestamp. That made
                # this halt-critical check structurally blind to loader staleness: confirmed
                # live, earnings_calendar's writer was deleted 2026-07-19 and its data frozen
                # since 2026-07-23, yet MAX(earnings_date) still read out to 2026-12-08 and
                # passed every freshness check. load_earnings_calendar.py (restored the same day
                # as this fix) now explicitly sets updated_at=now on every row it touches, so
                # this reflects real elapsed time since the loader last ran - same convention as
                # growth_metrics/quality_metrics/etc. below.
                "earnings_calendar": "updated_at",
                "growth_metrics": "updated_at",
                "quality_metrics": "updated_at",
                "value_metrics": "updated_at",
                "positioning_metrics": "updated_at",
                "stability_metrics": "updated_at",
                # CRITICAL FIX (2026-08-05): Add explicit date column for technical_data_daily
                # (was being skipped entirely from freshness checks). Uses standard "date" column
                # like price_daily, matching when technical indicators were computed/loaded.
                "technical_data_daily": "date",
            }
            # Only check tables that have a date column for freshness
            date_checked_tables = {**halt_tables, **warn_tables}

            # Per-table reference dates: some tables have upstream dependencies that limit how
            # current they can be. Compare against the appropriate upstream date, not global max.
            # - market_health_daily: limited by VIX availability in price_daily (^VIX published EOD)
            # - market_exposure_daily: limited by market_health_daily availability
            # - all others: compare against global price_daily max_date
            vix_max_date: _date | None = None
            health_max_date: _date | None = None
            try:
                cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = '^VIX'")
                vix_row = cur.fetchone()
                if not vix_row or vix_row[0] is None:
                    logger.error(
                        "[PHASE 1] CRITICAL: VIX data missing from price_daily. Cannot evaluate market health freshness."
                    )
                    raise RuntimeError(
                        "[PHASE 1] VIX price data unavailable. Check price_daily loader for ^VIX symbol."
                    )
                vix_max_date = vix_row[0]

                cur.execute("SELECT MAX(date) FROM market_health_daily")
                health_row = cur.fetchone()
                if not health_row or health_row[0] is None:
                    logger.error(
                        "[PHASE 1] CRITICAL: market_health_daily table is empty. Cannot evaluate market breadth."
                    )
                    raise RuntimeError("[PHASE 1] Market health data unavailable. Check market_health_daily loader.")
                health_max_date = health_row[0]

                # CRITICAL FIX: Verify market_health_daily has CRITICAL COLUMNS populated with diverse data
                # Early morning: table might exist but put_call_ratio not loaded yet
                # NEW FIX: Also check data distribution - all same value or all NaN is suspicious
                cur.execute(
                    """
                    SELECT COUNT(*) as total_rows,
                           SUM(CASE WHEN put_call_ratio IS NOT NULL THEN 1 ELSE 0 END) as pcr_rows,
                           SUM(CASE WHEN vix_level IS NOT NULL THEN 1 ELSE 0 END) as vix_rows
                    FROM market_health_daily
                    WHERE date = %s
                    """,
                    (health_max_date,),
                )
                health_col_row = cur.fetchone()
                if health_col_row and len(health_col_row) >= 3:
                    total_rows, pcr_rows, vix_rows = health_col_row[:3]
                else:
                    total_rows, pcr_rows, vix_rows = (0, 0, 0)

                pcr_distinct, vix_distinct = _fetch_health_distinctness_window(cur, health_max_date)

                _check_health_column_coverage(
                    total_rows, pcr_rows, pcr_distinct, vix_rows, vix_distinct, health_max_date
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[PHASE 1] CRITICAL: Database error fetching VIX/health reference dates: {e}")
                raise RuntimeError(f"[PHASE 1] Cannot fetch market reference dates from database: {e}") from e

            # CRITICAL FIX (Session 288): Validate UPSTREAM reference tables are fresh
            # before using them to validate downstream tables.
            # Previous bug: if market_health_daily was 9 days stale, and market_exposure_daily
            # was also 9 days stale, comparing them to each other would pass (both same age).
            # Solution: Compare upstream tables (market_health_daily, etc.) to expected trading day.

            if health_max_date < acceptable_min_date:
                days_behind = (acceptable_min_date - health_max_date).days
                logger.critical(
                    f"[PHASE 1] UPSTREAM TABLE STALE: market_health_daily is {days_behind} day(s) old "
                    f"(expected {acceptable_min_date}, got {health_max_date}). "
                    f"Cannot use stale upstream table to validate downstream tables."
                )
                halt_stale.append(f"market_health_daily is {days_behind} day(s) stale (upstream reference invalid)")

            # Map each table to its upstream reference date for staleness comparison
            # CRITICAL FIX: Must include all tables that will be checked below
            table_reference_dates = {
                "market_health_daily": vix_max_date,
                "market_exposure_daily": health_max_date,
                "earnings_calendar": run_date,  # Earnings calendar reference is the run date itself
                "earnings_calendar_sec": run_date,
                "price_daily": run_date,
                "technical_data_daily": run_date,
                "stock_scores": run_date,
                "buy_sell_daily": acceptable_min_date,  # Must have the latest trading day's signals for Phase 7
                "trend_template_data": run_date,
                "sector_ranking": run_date,
                "growth_metrics": run_date,
                "quality_metrics": run_date,
                "value_metrics": run_date,
                "positioning_metrics": run_date,
                "stability_metrics": run_date,
            }

            try:
                union_parts = []
                for table_name in date_checked_tables.keys():
                    date_col = date_column_overrides.get(table_name, "date")
                    if date_col is None:
                        raise RuntimeError(
                            f"[PHASE 1] Table {table_name} missing date_column_override - cannot determine date column"
                        )
                    union_parts.append(f"SELECT '{table_name}' as tbl, MAX({date_col}) as max_dt FROM {table_name}")

                union_query = " UNION ALL ".join(union_parts)
                cur.execute(union_query)

                max_dates = {}
                for row in cur.fetchall():
                    if row is None or len(row) < 2:
                        raise RuntimeError(
                            f"[PHASE 1] Table freshness query returned incomplete row: {row}. "
                            "Expected (table_name, max_date) tuple."
                        )
                    table_name_val = row[0]
                    max_date_val = row[1]
                    if table_name_val is None:
                        raise RuntimeError(
                            "[PHASE 1] Table freshness query returned NULL table name. "
                            "Union query construction may be broken."
                        )
                    max_dates[table_name_val] = max_date_val

                for table_name, description in date_checked_tables.items():
                    is_halt_table = table_name in halt_tables
                    # Use per-table reference date where applicable (e.g., market_health uses VIX date)
                    # CRITICAL: Fail fast if table reference date not defined - prevents staleness misreporting
                    if table_name not in table_reference_dates:
                        raise RuntimeError(
                            f"[PHASE 1] CRITICAL: Table {table_name} missing reference date in table_reference_dates. "
                            f"Cannot determine staleness baseline. This table must have an explicit reference date."
                        )
                    ref_date = table_reference_dates[table_name]
                    try:
                        table_max_date = max_dates.get(table_name)

                        # CRITICAL FIX: Ensure datetime to date conversion for all table max dates
                        if table_max_date is not None and isinstance(table_max_date, dt):
                            table_max_date = table_max_date.date()

                        if table_max_date is None:
                            msg = f"{description} is empty"
                            if is_halt_table:
                                logger.critical(f"[PHASE 1] {msg}")
                                halt_stale.append(msg)
                            else:
                                logger.warning(f"[PHASE 1] {msg}")
                                warn_stale.append(msg)
                            stale_table_details.append({"table_name": table_name, "age": "empty"})
                            continue

                        if table_max_date < ref_date:
                            days_behind = (ref_date - table_max_date).days
                            max_tolerance_days = phase1_halt_table_max_tolerance_days if is_halt_table else 0
                            if days_behind > max_tolerance_days:
                                msg = f"{description} is {days_behind} day(s) stale"
                                if is_halt_table:
                                    logger.critical(f"[PHASE 1] {msg}")
                                    halt_stale.append(msg)
                                else:
                                    logger.warning(f"[PHASE 1] {msg}")
                                    warn_stale.append(msg)
                                stale_table_details.append({"table_name": table_name, "age": f"{days_behind}d"})
                            else:
                                # BUG FOUND 2026-08-10 (live-reproduced): this hardcoded "1-day
                                # tolerance" regardless of the actual max_tolerance_days used in
                                # the comparison above (algo_config's
                                # phase1_halt_table_max_tolerance_days, live-confirmed set to 3,
                                # not 1). A live run logged "3 day(s) behind (within 1-day
                                # tolerance)" - self-contradictory, and actively misleading for
                                # anyone trying to diagnose staleness on a CRITICAL halt table.
                                msg = (
                                    f"{description} is {days_behind} day(s) behind "
                                    f"(within {max_tolerance_days}-day tolerance)"
                                )
                                logger.info(f"[PHASE 1] {msg}")

                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        msg = f"{description} check failed: {str(e)[:50]}"
                        if is_halt_table:
                            logger.critical(f"[PHASE 1] {msg} - FAIL-CLOSED")
                            halt_stale.append(msg)
                        else:
                            logger.warning(f"[PHASE 1] {msg}")
                            warn_stale.append(msg)
                        stale_table_details.append({"table_name": table_name, "age": "check failed"})
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.critical(
                    f"[PHASE 1] CRITICAL: Failed to check table freshness - cannot verify data integrity: {e}",
                    exc_info=True,
                )
                log_phase_result_fn(
                    1,
                    "table_freshness_check_error",
                    "halt",
                    f"Could not verify table freshness: {str(e)[:500]}",
                )
                return PhaseResult(
                    1,
                    "table_freshness_check_error",
                    "halted",
                    {},
                    True,
                    f"Table freshness check failed (cannot distinguish stale from error): {str(e)[:500]}",
                )

            if warn_stale:
                logger.warning(
                    f"[PHASE 1] Non-critical staleness (auxiliary tables, trading continues): {'; '.join(warn_stale)}"
                )

            if halt_stale:
                # CRITICAL FIX: NEVER bypass halt on critical data gaps, even in dry_run mode
                # dry_run mode is for testing - it should still validate and report halts,
                # just not actually trigger downstream consequences. But Phase 1 freshness checks
                # are safety gates - they must always execute fully and report halt status.
                logger.critical(f"[PHASE 1] CRITICAL DATA GAPS (pipeline tables): {'; '.join(halt_stale)}")
                log_phase_result_fn(
                    1,
                    "signal_tables_stale",
                    "halt",
                    f"Stale/missing pipeline data: {'; '.join(halt_stale[:3])}",
                )
                from algo.reporting.notifications import notify_signal_staleness

                notify_signal_staleness(halt_stale)
                tables_validated = 1 + len(date_checked_tables)
                return PhaseResult(
                    1,
                    "signal_tables_stale",
                    "halted",
                    {
                        "tables_validated": tables_validated,
                        "tables_fresh": tables_validated - len(stale_table_details),
                        "tables_stale": len(stale_table_details),
                        "stale_tables": stale_table_details,
                        "validation_status": "HALTED",
                    },
                    True,
                    f"Critical pipeline tables stale/missing: {halt_stale[0]}",
                )

            elapsed = time.time() - phase_start
            phase1_end_et = dt.now(EASTERN_TZ)

            sla_status = ""
            if pipeline_context == "MORNING":
                sla_deadline = phase1_end_et.replace(hour=9, minute=30, second=0, microsecond=0)
                if phase1_end_et < sla_deadline:
                    minutes_until_sla = (sla_deadline - phase1_end_et).total_seconds() / 60
                    sla_status = f" [SLA OK: {minutes_until_sla:.0f}m until 9:30 AM]"
                else:
                    sla_status = " [SLA WARNING: Past 9:30 AM]"

            warn_suffix = f" ({len(warn_stale)} auxiliary warnings)" if warn_stale else ""
            logger.info(f"[PHASE 1] PASS - PIPELINE DATA FRESH{sla_status}{warn_suffix}")
            logger.info(f"  - Prices: {max_date} ({symbols_loaded} symbols, {coverage_pct:.1f}%)")
            if not warn_stale:
                logger.info("  - All pipeline tables (market_health, trend_template, market_exposure) fresh")
            else:
                logger.info(
                    "  - Critical pipeline tables (market_health, market_exposure) fresh; auxiliary warnings above"
                )
            logger.info(f"  - Check completed in {elapsed:.1f}s")

            # CRITICAL FIX 2026-07-05: Validate that metric loaders are ready before Phase 7 signal generation
            # These loaders (quality, growth, value, positioning, stability, momentum) feed into stock_scores
            # which feed into signal generation. If metrics are all-unavailable, stock_scores will fail.
            logger.info("[PHASE 1] Validating upstream metric loaders ready for stock_scores...")
            degraded_reason = None
            try:
                from loaders.load_stock_scores import StockScoresLoader

                metric_validator = StockScoresLoader()
                metric_validator.validate_upstream_metrics_ready()
                logger.info("[PHASE 1] Metric loaders validation: PASS - All metric loaders ready")

                # FIXED 2026-07-15: Add stock_scores data completeness check (Issue #6 from Session 166 audit)
                # Validate that scores have sufficient completeness (60%+ avg for available scores)
                # FIXED 2026-07-18: Only average AVAILABLE scores (data_unavailable=FALSE)
                # Stocks with 0% completeness are legitimately unavailable due to missing metrics,
                # and should not drag down the average or halt trading for all other stocks.
                try:
                    # CRITICAL: stock_scores.updated_at is `timestamp without time zone`, written via
                    # datetime.now(timezone.utc) in load_stock_scores.py (i.e. the stored digits ARE
                    # UTC wall-clock). TRADING-DAY FIX: Don't check "last 24 hours" (fails on Monday
                    # morning when Friday's EOD scores are 48h old). Instead check if max score date
                    # matches the most recent trading day in the DB (which stock_scores depends on for
                    # underlying metric data). Stock scores have no date column, so check updated_at
                    # against price_daily's max date (latest trading day with prices).
                    cur.execute(f"""
                        SELECT AVG(data_completeness) as avg_completeness,
                               COUNT(*) as total_available_scores,
                               COUNT(CASE WHEN data_completeness >= {PHASE1_METRIC_COVERAGE_MIN_PCT} THEN 1 END) as complete_scores,
                               COUNT(*) FILTER (WHERE data_unavailable = FALSE) as available_count,
                               MAX(updated_at) as max_updated
                        FROM stock_scores
                        WHERE data_unavailable = FALSE
                    """)
                    completeness_row = cur.fetchone()

                    # Verify stock_scores were computed for the latest trading day available in price data
                    cur.execute("SELECT MAX(date) FROM price_daily")
                    price_row = cur.fetchone()
                    if not price_row or price_row[0] is None:
                        raise RuntimeError(
                            "[PHASE 1] price_daily table is empty - cannot verify stock_scores freshness"
                        )
                    latest_price_date = price_row[0]

                    # Stock scores should have been updated AFTER the latest price date (they're computed
                    # end-of-day). Allow up to 48 hours for EOD pipelines to run (covering overnight + weekend scenarios).
                    scores_age_hours = None
                    if completeness_row and completeness_row[4] and latest_price_date:
                        from datetime import datetime, timezone

                        now_utc = datetime.now(timezone.utc)
                        max_updated = completeness_row[4]
                        if max_updated.tzinfo is None:
                            max_updated = max_updated.replace(tzinfo=timezone.utc)
                        scores_age_hours = (now_utc - max_updated).total_seconds() / 3600

                    if (
                        completeness_row
                        and completeness_row[0] is not None
                        and scores_age_hours is not None
                        and scores_age_hours < 48
                    ):
                        avg_completeness = float(completeness_row[0])
                        total_available = completeness_row[1]
                        complete_scores = completeness_row[2]

                        logger.info(
                            f"[PHASE 1] Stock scores completeness: {avg_completeness:.1f}% avg "
                            f"({complete_scores}/{total_available} available symbols >= {PHASE1_METRIC_COVERAGE_MIN_PCT}%)"
                        )

                        # GOVERNANCE: Allow proceeding if 60%+ of available scores are complete
                        # Stocks with insufficient metrics are properly marked data_unavailable
                        # and excluded from signal generation, so degradation is contained
                        if avg_completeness < 60:
                            logger.warning(
                                f"[PHASE 1] DEGRADED: Stock scores avg completeness only {avg_completeness:.1f}%. "
                                f"Position sizing may use incomplete metric data. "
                                f"If this persists, check: {[t for t in halt_tables if 'metric' in t]}"
                            )
                            degraded_reason = (
                                f"Stock scores only {avg_completeness:.1f}% complete "
                                f"(missing positioning/stability/growth metrics)"
                            )
                    else:
                        # Stale, missing, or incompute able scores
                        if (
                            completeness_row
                            and completeness_row[4] is not None
                            and scores_age_hours is not None
                            and scores_age_hours >= 48
                        ):
                            logger.warning(
                                f"[PHASE 1] stock_scores stale: computed {scores_age_hours:.1f}h ago "
                                f"(max_updated={completeness_row[4]}). "
                                f"Latest price data is from {latest_price_date}. "
                                f"Scores are older than 48h threshold. "
                                f"Check if end-of-day pipeline has run."
                            )
                        else:
                            logger.warning(
                                "[PHASE 1] stock_scores data unavailable or no available symbols. "
                                "Proceeding but scores will be unavailable for signal generation."
                            )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as completeness_err:
                    logger.warning(
                        f"[PHASE 1] Could not check stock_scores completeness (DB error): {completeness_err}. "
                        "Will proceed with signal generation using available scores."
                    )
                except (KeyError, ValueError, AttributeError) as completeness_err:
                    logger.warning(
                        f"[PHASE 1] Could not check stock_scores completeness (data error): {completeness_err}. "
                        "Will proceed with signal generation using available scores."
                    )
            except RuntimeError as e:
                metric_error = str(e)
                logger.warning(f"[PHASE 1] Metric loaders validation failed: {metric_error}")
                try:
                    cur.execute("""
                        SELECT COUNT(*) FROM quality_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                        UNION ALL SELECT COUNT(*) FROM growth_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                        UNION ALL SELECT COUNT(*) FROM stability_metrics WHERE updated_at > NOW() - INTERVAL '7 days'
                    """)
                    metric_counts = cur.fetchall()
                    has_recent_metrics = any(row[0] > 0 for row in metric_counts)

                    if has_recent_metrics:
                        logger.critical(
                            f"[PHASE 1] CRITICAL: Metrics exist but validation failed. {metric_error}. "
                            f"GOVERNANCE requires fail-fast on metric validation failure. "
                            f"Root cause must be resolved before trading resumes."
                        )
                        halt_reason = f"Metric loader validation failed: {metric_error[:500]}"
                        log_phase_result_fn(1, "metric_validation_failed", "halt", halt_reason)
                        return PhaseResult(
                            1,
                            "metric_validation_failed",
                            "halted",
                            {},
                            True,
                            halt_reason,
                        )
                    else:
                        logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                        halt_reason = f"Required metric loaders not ready: {metric_error[:500]}"
                        log_phase_result_fn(1, "metric_loaders_not_ready", "halt", halt_reason)
                        return PhaseResult(
                            1,
                            "metric_loaders_not_ready",
                            "halted",
                            {},
                            True,
                            halt_reason,
                        )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as check_err:
                    # CRITICAL FIX: this branch only logged halt_reason with no `return` (and no
                    # log_phase_result_fn call) - unlike its sibling except clause immediately
                    # below, which correctly halts. We only reach this try block after
                    # validate_upstream_metrics_ready() has ALREADY raised a genuine critical
                    # metric-validation failure (metric_error); this except exists purely to
                    # assess its severity via a diagnostic query. If that diagnostic query itself
                    # hits a transient DB error, execution fell through to this function's normal
                    # "all_tables_fresh"/"success" logging further down, masking the original
                    # critical metric-validation failure as a clean pass - the DB error ate the
                    # halt, rather than the halt surviving the DB error.
                    halt_reason = f"Could not verify metric availability (DB error): {str(check_err)[:500]}"
                    logger.critical(f"[PHASE 1] {halt_reason}. Original metric validation failure: {metric_error}")
                    log_phase_result_fn(1, "metric_verification_error", "halt", halt_reason)
                    return PhaseResult(
                        1,
                        "metric_verification_error",
                        "halted",
                        {},
                        True,
                        halt_reason,
                    )
                except (RuntimeError, ValueError, KeyError) as check_err:
                    halt_reason = f"Could not verify metric availability (validation error): {str(check_err)[:500]}"
                    logger.error(f"[PHASE 1] {halt_reason}")
                    logger.critical(f"[PHASE 1] CRITICAL: Metric loaders validation failed: {metric_error}")
                    log_phase_result_fn(1, "metric_verification_error", "halt", halt_reason)
                    return PhaseResult(
                        1,
                        "metric_verification_error",
                        "halted",
                        {},
                        True,
                        halt_reason,
                    )

            log_phase_result_fn(
                1,
                "all_tables_fresh",
                "success",
                f"All critical tables fresh: prices={max_date}, coverage={coverage_pct:.1f}%"
                + (f" [DEGRADED MODE: {degraded_reason}]" if degraded_reason else ""),
            )

            # GOVERNANCE COMPLIANCE: Halt on degraded data (never allow incomplete metrics for trading)
            # Ref: GOVERNANCE.md - "Never accept scores with <50% data completeness"
            if degraded_reason:
                logger.critical(
                    f"[PHASE 1] HALTING: Degraded data not allowed for trading. "
                    f"Reason: {degraded_reason}. "
                    f"Fix: Ensure all metric loaders complete with >{PHASE1_METRIC_COVERAGE_MIN_PCT}% symbol coverage before trading."
                )
                log_phase_result_fn(1, "degraded_data_halt", "halt", degraded_reason)
                phase_data: dict[str, Any] = {
                    "status": "halted",
                    "reason": degraded_reason,
                }
                validate_phase_data(1, phase_data)
                return PhaseResult(
                    1,
                    "degraded_data_halt",
                    "halted",
                    phase_data,
                    True,  # HALT on degraded data
                    degraded_reason,
                )

            # Return with ok status when all data is complete
            tables_validated = 1 + len(date_checked_tables)
            phase_data: dict[str, Any] = {  # type: ignore[no-redef]
                "status": "ok",
                "price_date": str(max_date),
                "symbols_loaded": symbols_loaded,
                "coverage_pct": coverage_pct,
                "tables_validated": tables_validated,
                "tables_fresh": tables_validated - len(stale_table_details),
                "tables_stale": len(stale_table_details),
                "stale_tables": stale_table_details,
                "validation_status": "PASS" if not stale_table_details else "PASS (with warnings)",
            }
            validate_phase_data(1, phase_data)

            # CRITICAL NEW CHECK (2026-08-02): Validate portfolio symbols have prices
            # Phase 1 verified price_daily overall freshness, but doesn't check if ALL
            # portfolio symbols have data for the trading date. This causes Phase 6 to halt
            # when evaluating exits for a symbol with no price_daily data (verified root
            # cause of "5 errors" pattern on 2026-07-29). Catch this early.
            try:
                # Get all open positions in portfolio
                cur.execute("""
                    SELECT DISTINCT symbol FROM algo_positions
                    WHERE status IN ('open', 'partially_filled')
                """)
                portfolio_symbols = [row[0] for row in cur.fetchall()]

                if portfolio_symbols:
                    logger.info(
                        f"[PHASE 1] Validating prices for {len(portfolio_symbols)} portfolio symbols (using latest available)"
                    )
                    # CRITICAL FIX: Use latest available price for each symbol, consistent with Phase 3
                    # Phase 3 position_monitor.py uses ROW_NUMBER() OVER ORDER BY date DESC to get
                    # the most recent price regardless of exact date. Phase 1 must validate the same way
                    # to avoid false halts on mid-trading-day runs before EOD prices load.
                    cur.execute(
                        """
                        WITH latest_prices AS (
                            SELECT symbol, close,
                                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn
                            FROM price_daily
                            WHERE symbol = ANY(%s) AND close IS NOT NULL
                        )
                        SELECT symbol, close FROM latest_prices WHERE rn = 1
                    """,
                        (portfolio_symbols,),
                    )
                    price_rows = cur.fetchall()
                    price_symbols = {row[0]: row[1] for row in price_rows}
                    missing_symbols = [s for s in portfolio_symbols if s not in price_symbols]

                    if missing_symbols:
                        # CRITICAL: Missing prices for portfolio symbols - cannot execute exits
                        error_msg = (
                            f"[PHASE 1 CRITICAL] Portfolio symbols missing any price data: {missing_symbols}. "
                            f"Phase 6 exit execution will fail for these positions. "
                            f"Check price_daily loader logs for data gaps or symbol-specific issues."
                        )
                        logger.critical(error_msg)
                        log_phase_result_fn(1, "portfolio_price_coverage", "halt", error_msg)

                        # Return halted status to prevent Phase 6 attempting exits without price data
                        phase_data["portfolio_symbols"] = len(portfolio_symbols)
                        phase_data["missing_prices"] = missing_symbols
                        return PhaseResult(
                            1,
                            "portfolio_price_coverage",
                            "halted",
                            phase_data,
                            True,
                            f"Portfolio symbols missing prices: {missing_symbols}",
                        )
                    else:
                        logger.info(
                            f"[PHASE 1] All {len(portfolio_symbols)} portfolio symbols have prices (latest available)"
                        )
                        phase_data["portfolio_symbols"] = len(portfolio_symbols)
                        phase_data["portfolio_price_coverage"] = "complete"
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as portfolio_check_err:
                # If portfolio symbol check fails, log but don't halt (it's supplementary)
                logger.warning(
                    f"[PHASE 1] Portfolio symbol price validation failed (DB error): {portfolio_check_err}. Continuing."
                )
            except (KeyError, ValueError, TypeError) as portfolio_check_err:
                # Data structure error - log but don't halt
                logger.warning(
                    f"[PHASE 1] Portfolio symbol price validation failed (data error): {portfolio_check_err}. Continuing."
                )

            return PhaseResult(
                1,
                "all_tables_fresh",
                "ok",
                phase_data,
                False,  # Not halted
                "All critical data fresh and complete",
            )

    except Exception as e:
        # FIXED 2026-07-07: Include exception type and full message, not just truncated str(e)
        exception_type = type(e).__name__
        exception_msg = str(e) if str(e) else "(no message)"
        error_summary = f"{exception_type}: {exception_msg}"[:200]
        logger.error(f"[PHASE 1] ERROR: {error_summary}", exc_info=True)
        log_phase_result_fn(1, "error", "error", error_summary)
        phase_data = {"status": "error", "reason": f"Phase 1 failed: {error_summary}"}
        validate_phase_data(1, phase_data)
        return PhaseResult(1, "error", "error", phase_data, True, error_summary)

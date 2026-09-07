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
from datetime import timedelta as _timedelta
from typing import Any

import psycopg2

from algo.infrastructure.constants import (
    PHASE1_DB_QUERY_TIMEOUT_MS,
    PHASE1_METRIC_COVERAGE_MIN_PCT,
)
from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase1_failsafe_retry import check_and_retry_incomplete_loaders
from algo.orchestrator.phase1_price_freshness import (
    apply_eod_yesterday_price_grace,
    check_price_coverage_halt,
    check_price_staleness_halt,
    compute_acceptable_min_date_with_grace,
    compute_coverage_pct,
    compute_last_trading_day,
    detect_phantom_price_rows,
    preflight_verify_stock_symbols_table,
    resolve_coverage_check_date_and_symbols_loaded,
    resolve_price_daily_max_date,
    verify_active_symbol_list,
    verify_loader_status_completion_integrity,
)
from algo.orchestrator.phase1_readiness_checks import (
    validate_portfolio_symbol_prices,
    validate_stock_scores_readiness,
)
from algo.orchestrator.phase1_table_freshness import (
    build_table_reference_dates,
    check_all_tables_freshness,
    check_upstream_health_staleness,
    handle_halt_stale_tables,
)
from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.status_manager import LoaderStatusManager
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


def _cleanup_stuck_database_sessions(max_idle_hours: int = 1) -> int:
    """Kill idle-in-transaction sessions stuck for >N hours.

    SESSION 105 ROOT CAUSE: Stuck idle-in-transaction sessions hold locks on
    data_loader_status table, causing all loader INSERTs to timeout after 30s.
    This cascades to Monday brittleness: Friday timeout → idle session holds lock →
    Saturday/Sunday session accumulates → Monday all loaders fail to INSERT progress.

    Solution: At Phase 1 startup, kill any idle-in-transaction session older than
    1 hour. These are almost certainly from crashed code paths that never returned
    the connection to the pool.

    Args:
        max_idle_hours: Kill sessions idle-in-transaction for longer than this (default 1h)

    Returns:
        Number of sessions killed
    """
    killed_count = 0
    try:
        with DatabaseContext("write") as cur:
            # Find stuck idle-in-transaction sessions
            cur.execute(f"""
                SELECT pid, usename, query_start
                FROM pg_stat_activity
                WHERE state = 'idle in transaction'
                    AND query_start IS NOT NULL
                    AND AGE(NOW(), query_start) > INTERVAL '{max_idle_hours} hours'
                    AND pid != pg_backend_pid()
                ORDER BY query_start ASC
            """)

            stuck_pids = cur.fetchall()
            if stuck_pids:
                logger.warning(
                    f"[PHASE 1 STARTUP] Found {len(stuck_pids)} idle-in-transaction sessions stuck for >{max_idle_hours}h. "
                    f"These are likely from crashed loaders. Terminating to clear data_loader_status locks..."
                )

            for row in stuck_pids:
                pid, user, query_start = row
                age = time.time() - query_start.timestamp() if query_start else 0
                hours_old = age / 3600
                try:
                    cur.execute(f"SELECT pg_terminate_backend({pid})")
                    result = cur.fetchone()
                    if result and result[0]:
                        logger.info(f"[PHASE 1 STARTUP] Killed PID {pid} (idle {hours_old:.1f}h, user={user})")
                        killed_count += 1
                    else:
                        logger.warning(f"[PHASE 1 STARTUP] Could not kill PID {pid} (not running?)")
                except Exception as term_err:
                    logger.warning(f"[PHASE 1 STARTUP] Error killing PID {pid}: {term_err}")

    except Exception as cleanup_err:
        logger.warning(f"[PHASE 1 STARTUP] Could not query/clean stuck sessions: {cleanup_err}")

    return killed_count


def _cleanup_orphaned_positions() -> None:
    """Auto-close orphaned algo_positions rows left over from previous failed runs.

    STARTUP: Clean up orphaned positions from previous failed runs
    This prevents orphaned positions from blocking Phase 2/7 risk calculations

    BUG FOUND 2026-08-25 (real-money-readiness goal session, full-file audit): the
    "no open trade for this symbol" check below used a hardcoded `t.status = 'open'`
    instead of TradeStatus.all_open() (open/filled/partially_filled/active/pending/
    paper_pending) - the exact same "hand-rolled subset missing FILLED/PARTIAL" bug
    class already found and fixed once in exit_engine.py's own exit-candidate query
    (see TradeStatus.all_open()'s own docstring for that history). In real live/auto
    mode, executor_entry_handler.py records a normally-filled order's algo_trades.status
    as 'filled'/'partially_filled', never the literal string 'open' - confirmed via
    `execution_mode == "auto" and order_status in ("filled", "partially_filled")`. So
    for ANY symbol that had ever been closed before (closed_trades CTE matches it) and
    was later re-entered and filled for real, this query's NOT EXISTS saw zero rows
    with status='open' (the real row was 'filled') and concluded the position was
    orphaned - silently marking a genuinely open, broker-held, real-money position as
    'closed' in our own database on every Phase 1 run (4-5x/day). This desyncs every
    downstream consumer that filters on algo_positions.status='open' (exit_engine.py's
    stop/target monitoring, position_sizer.py's risk-exposure accounting, dashboard) from
    a position the broker still actually holds - no crash, no error, just silent loss of
    tracking on a real position while stop-loss/target management for it stops running.
    Invisible in local dev testing because paper-mode trades are recorded with status
    literally 'open' (never 'filled') - see algo/trading/executor_entry_handler.py's
    execution_mode branching - so this only ever manifested in real live/auto trading.
    """
    try:
        from utils.db import DatabaseContext

        with DatabaseContext("write") as cleanup_cursor:
            cleanup_cursor.execute(
                """
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
                    WHERE t.symbol = p.symbol AND t.status = ANY(%s)
                );
                """,
                (list(TradeStatus.all_open()),),
            )
            if cleanup_cursor.rowcount > 0:
                logger.info(
                    f"[PHASE 1 STARTUP] Auto-closed {cleanup_cursor.rowcount} orphaned positions from previous runs"
                )
    except Exception as cleanup_err:
        logger.warning(f"[PHASE 1 STARTUP] Could not cleanup orphaned positions: {cleanup_err}")


def _run_startup_maintenance() -> None:
    """Run Phase 1 startup maintenance: stuck-session cleanup and orphaned-position cleanup.

    SESSION 105 FIX: Clean up stuck idle-in-transaction sessions before anything else
    These sessions hold locks on data_loader_status, causing all loader INSERTs to timeout
    This is THE ROOT CAUSE of Monday brittleness (Friday stuck session -> locks persist -> Monday cascade)
    """
    killed = _cleanup_stuck_database_sessions(max_idle_hours=1)
    if killed > 0:
        logger.critical(
            f"[PHASE 1 STARTUP] CRITICAL: Cleaned up {killed} stuck database sessions "
            f"that were blocking loader progress. This indicates a resource leak - "
            f"connections are not being returned to the pool properly. "
            f"Investigate code paths that open connections without proper cleanup."
        )

    _cleanup_orphaned_positions()


def _fetch_vix_and_health_reference_dates(cur: Any) -> tuple[_date, _date]:
    """Fetch VIX and market_health_daily reference dates, and validate health column coverage.

    Per-table reference dates: some tables have upstream dependencies that limit how
    current they can be. Compare against the appropriate upstream date, not global max.
    - market_health_daily: limited by VIX availability in price_daily (^VIX published EOD)
    - market_exposure_daily: limited by market_health_daily availability
    - all others: compare against global price_daily max_date
    """
    vix_max_date: _date | None = None
    health_max_date: _date | None = None
    try:
        cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = '^VIX'")
        vix_row = cur.fetchone()
        if not vix_row or vix_row[0] is None:
            logger.error(
                "[PHASE 1] CRITICAL: VIX data missing from price_daily. Cannot evaluate market health freshness."
            )
            raise RuntimeError("[PHASE 1] VIX price data unavailable. Check price_daily loader for ^VIX symbol.")
        vix_max_date = vix_row[0]

        cur.execute("SELECT MAX(date) FROM market_health_daily")
        health_row = cur.fetchone()
        if not health_row or health_row[0] is None:
            logger.error("[PHASE 1] CRITICAL: market_health_daily table is empty. Cannot evaluate market breadth.")
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

        _check_health_column_coverage(total_rows, pcr_rows, pcr_distinct, vix_rows, vix_distinct, health_max_date)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 1] CRITICAL: Database error fetching VIX/health reference dates: {e}")
        raise RuntimeError(f"[PHASE 1] Cannot fetch market reference dates from database: {e}") from e

    return vix_max_date, health_max_date


def _verify_required_date_coverage_or_fallback(
    cur: Any, last_trading_day: _date, symbol_count: int, run_date_obj: _date, max_date: _date
) -> _date:
    """Verify last_trading_day actually has symbol coverage; fall back to best recent date if not.

    SESSION 89 FIX: Verify we have ACTUAL data for the required date, not just MAX(date) >= required
    Prevents Monday trading on Friday's data reprocessed with new timestamp
    Check that last_trading_day (or acceptable_min_date) actually has symbol coverage

    Returns the (possibly reassigned) max_date.
    """
    from datetime import timedelta as td

    cur.execute(
        """SELECT COUNT(DISTINCT symbol) FROM price_daily
           WHERE date = %s AND close IS NOT NULL AND open IS NOT NULL""",
        (last_trading_day,),
    )
    required_date_row = cur.fetchone()
    required_date_coverage = required_date_row[0] if required_date_row and required_date_row[0] is not None else 0
    if required_date_coverage < (symbol_count * 0.5):  # At least 50% coverage on required date
        logger.warning(
            f"[PHASE 1] SESSION 89 FIX: Required date {last_trading_day} has only "
            f"{required_date_coverage} symbols ({required_date_coverage / (symbol_count or 1) * 100:.1f}%). "
            f"MAX(date) is {max_date}. Possible stale data reprocessing. Using {max_date} instead."
        )
        # Fall back to whatever RECENT date has the most data. Bounded to the last 30
        # days (BUG FOUND, goal session, Phase 1 deep-review pass): this query had no
        # date filter at all - it picked whichever date in the ENTIRE history of
        # price_daily had the most distinct symbols with non-null OHLC. Since the active
        # trading universe shrinks over time via delistings, an old date can legitimately
        # out-count today's partial/in-progress load, so an unbounded query could pick a
        # date months or years stale. Traced where the reassigned `max_date` is used
        # afterward: only cosmetic reporting (log lines, the returned `price_date` field)
        # - Phase 1's own primary staleness halt already used the correctly-computed
        # date earlier in this function, and Phase 8 independently re-verifies price
        # freshness with its own bounded query before any entry - so this specific gap
        # was not a live path to trading on stale data. Bounding it anyway as
        # defense-in-depth so a future caller of this reassigned value (or an operator
        # reading the dashboard's reported price_date) can't be misled by an
        # arbitrarily-old date.
        cur.execute(
            """SELECT date, COUNT(DISTINCT symbol) as coverage
               FROM price_daily
               WHERE close IS NOT NULL AND open IS NOT NULL AND date >= %s
               GROUP BY date ORDER BY coverage DESC LIMIT 1""",
            (run_date_obj - td(days=30),),
        )
        fallback_row = cur.fetchone()
        if fallback_row:
            max_date = fallback_row[0]
            logger.warning(f"[PHASE 1] Falling back to {max_date} with {fallback_row[1]} symbols")

    return max_date


def _check_eod_today_price_completeness(
    cur: Any,
    pipeline_context: str,
    now_et: Any,
    run_date_obj: _date,
    min_symbol_count: int,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult | None:
    """For EOD runs, also validate TODAY's price data (needed for Phase 6 exit execution).

    CRITICAL: For EOD runs, also validate TODAY's price data
    During INTRADAY (10 AM-4 PM), today's close isn't published yet - only yesterday's close is available
    Only after market close (EOD, 4 PM+) do we expect today's close data
    """
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

    return None


def _detect_and_fail_stale_running_loaders(
    stale_threshold_minutes: int = 60, progress_threshold_pct: float = 0.1
) -> list[str]:
    """Detect RUNNING or NOT_STARTED loaders stuck for >N minutes and auto-fail them.

    CRITICAL FIX (Session 82): Fixes the "stuck RUNNING for days" Monday failure sequence:
    - Friday: Loader times out → marked RUNNING, process dies
    - Saturday/Sunday: Stuck RUNNING, no monitoring
    - Monday: Phase 1 hangs waiting for RUNNING loader
    - Result: orchestrator halt, manual operator backfill

    IMPROVED (Session 89): Reduced timeout from 30 min to 5 min to prevent Monday morning
    orchestrator hangs on crashed loaders from Friday.

    SESSION 94 FIX: Used 2 min, but this was too aggressive - many loaders take 2+ minutes
    just initializing (fetching symbol lists, starting parallel workers). Legitimate loaders
    would be wrongly marked FAILED before they started work.

    SESSION 108 FIX: Increased to 10 minutes, but this was STILL TOO AGGRESSIVE for
    long-running loaders like company_info_sec (540 min), financial_statements (540 min).
    These can take 30-60+ minutes in initialization before first progress update.

    SESSION 109 FIX: Changed from time-only to progress-aware detection:
    - Increased baseline timeout to 60 minutes
    - Only fail loaders if BOTH conditions met:
      (1) last_updated > 60 min ago (no status update for 60 min)
      (2) completion_pct <= 0.1% (no progress being made)
    - Loaders making progress (>0.1%) are working, never fail them
    This allows slow-initializing loaders to start before being marked failed.

    SESSION 106 FIX: Also detect loaders stuck NOT_STARTED after >N minutes. If a subprocess
    crashes before calling mark_running(), status stays NOT_STARTED. Failsafe retry won't retry
    loaders in NOT_STARTED (only retries FAILED/INCOMPLETE), so stuck NOT_STARTED loaders never
    get marked for retry unless detected here.

    This function runs at Phase 1 startup to detect crashed loaders that were never
    properly marked FAILED. A loader stuck RUNNING or NOT_STARTED for >N min with zero
    progress almost certainly crashed (no active process checking in on it or making progress).

    Args:
        stale_threshold_minutes: Mark as FAILED if last_updated is older than this (default 60)
        progress_threshold_pct: Only fail if completion_pct <= this (default 0.1%, Session 109)

    Returns:
        List of table names that were recovered (marked FAILED)
    """
    recovered = []
    try:
        with DatabaseContext("read") as cur:
            # SESSION 109: Check for both RUNNING and NOT_STARTED loaders stuck for >threshold_minutes
            # BUT ONLY if completion_pct is still at 0% (no progress made at all)
            # Loaders making progress (>0.1%) are working, don't fail them even if initialization takes time
            cur.execute(
                f"""
                SELECT table_name, last_updated, status, completion_pct
                FROM data_loader_status
                WHERE (status = 'RUNNING' OR status = 'NOT_STARTED')
                  AND last_updated < CURRENT_TIMESTAMP - INTERVAL '{stale_threshold_minutes} minutes'
                  AND (completion_pct IS NULL OR completion_pct <= %s)
                ORDER BY last_updated ASC
            """,
                (progress_threshold_pct,),
            )
            stale_loaders = cur.fetchall()

            for row in stale_loaders:
                table_name, last_updated, status, completion_pct = row
                progress_info = f"completion={completion_pct}%" if completion_pct else "completion=unknown"
                error_msg = (
                    f"[PHASE 1 STARTUP] Auto-failed stale {status} loader "
                    f"({progress_info}, stuck for {stale_threshold_minutes}+ min since {last_updated}). "
                    f"Likely crashed with no process alive. Will retry via failsafe."
                )
                logger.warning(f"[PHASE 1 STARTUP] {table_name}: {error_msg}")
                try:
                    LoaderStatusManager(table_name).mark_failed(error_msg)
                    recovered.append(table_name)
                except Exception as mark_err:
                    logger.error(f"[PHASE 1 STARTUP] Could not mark {table_name} as FAILED: {mark_err}")

            if recovered:
                logger.info(
                    f"[PHASE 1 STARTUP] Recovered {len(recovered)} stale RUNNING/NOT_STARTED loader(s): {', '.join(set(recovered))}. "
                    f"Will retry via failsafe mechanism."
                )
    except Exception as e:
        logger.warning(
            f"[PHASE 1 STARTUP] Could not detect stale RUNNING/NOT_STARTED loaders (non-fatal): {e}. "
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
    - value_metrics requires: annual_income_statement, annual_balance_sheet, sec_valuations
      (produced by: load_financial_statements.py, load_sec_valuations.py)
    - sec_segment_metrics requires: sec_segment_info (loader: load_sec_segment_info.py)
    - positioning_metrics requires: institutional_holdings_13f
    - stock_scores requires: value_metrics, stability_metrics

    Returns: PhaseResult halt if a dependency is stale, None if all dependencies OK
    """
    dependencies = {
        # value_metrics produced by load_value_quality_growth_metrics.py
        # Requires financial statement data from load_financial_statements.py
        "value_metrics": ["annual_income_statement", "annual_balance_sheet", "sec_valuations"],
        # sec_segment_metrics produced by load_sec_segment_metrics.py
        "sec_segment_metrics": ["sec_segment_info"],
        # positioning_metrics requires institutional holdings
        "positioning_metrics": ["institutional_holdings_13f"],
        # stock_scores requires computed metrics
        "stock_scores": ["value_metrics", "stability_metrics"],
    }

    failed_deps = []
    for downstream, upstreams in dependencies.items():
        for upstream in upstreams:
            try:
                # CRITICAL FIX (Session 96): Check actual data MAX(date) instead of
                # data_loader_status.latest_date which is a stale cache field
                # Session 96 verified: sec_valuations had latest_date=2026-08-11 but actual
                # data MAX(computed_at)=2026-08-12, causing false "stale" halts despite fresh data
                actual_data_date = None
                if upstream == "sec_valuations":
                    # sec_valuations uses computed_at, not date
                    cur.execute("SELECT MAX(computed_at)::date FROM sec_valuations")
                elif upstream == "earnings_calendar":
                    # earnings_calendar uses updated_at, not date
                    cur.execute("SELECT MAX(updated_at)::date FROM earnings_calendar")
                elif upstream in (
                    "stock_scores",
                    "annual_income_statement",
                    "annual_balance_sheet",
                    "sec_segment_info",
                    "institutional_holdings_13f",
                    "stability_metrics",
                    "value_metrics",
                ):
                    # FIX (live-confirmed 2026-08-17): the `else` branch below unconditionally
                    # queried MAX(date), but none of these 6 SEC/financial/metrics tables have
                    # a `date` column at all (only `updated_at` - confirmed live via
                    # information_schema) - every real orchestrator run hit
                    # psycopg2.errors.UndefinedColumn on the very first one
                    # (annual_income_statement) and, because the aborted transaction was never
                    # rolled back (see except-block fix below), that ALSO cascaded
                    # InFailedSqlTransaction onto every other dependency check sharing this
                    # cursor, for the entire lifetime of this check. Nothing in `failed_deps`
                    # ever recorded this - the whole "CRITICAL DEPENDENCIES" safety check this
                    # function exists for was silently a no-op on every single run. value_metrics
                    # does have a `date` column too, but `updated_at` (when the row was actually
                    # loaded) matches this function's "was this dependency fresh" purpose - and
                    # the sibling table_reference_dates/date_column_overrides check further down
                    # this file already uses updated_at for these exact tables.
                    cur.execute(f"SELECT MAX(updated_at)::date FROM {upstream}")
                else:
                    # Remaining tables use a real date column
                    cur.execute(f"SELECT MAX(date) FROM {upstream}")

                result = cur.fetchone()
                if not result or not result[0]:
                    failed_deps.append(f"{downstream}→{upstream}: never loaded")
                    continue

                actual_data_date = result[0]
                if actual_data_date < run_date:
                    failed_deps.append(f"{downstream}→{upstream}: last data {actual_data_date} < required {run_date}")

                # Also check loader status for failures
                cur.execute(
                    "SELECT status FROM data_loader_status WHERE table_name = %s",
                    (upstream,),
                )
                status_row = cur.fetchone()
                if status_row:
                    status = status_row[0]
                    if status in ("FAILED", "TIMEOUT"):
                        failed_deps.append(f"{downstream}→{upstream}: marked {status}")
            except Exception as e:
                logger.warning(f"[PHASE 1] Could not check dependency {upstream}: {e}")
                # FIX (live-confirmed 2026-08-17): without this, a single failed query (e.g.
                # the UndefinedColumn bug fixed above) leaves the shared connection in Postgres's
                # "current transaction is aborted" state, so every subsequent dependency check
                # in this same loop - unrelated tables entirely - also fails with
                # InFailedSqlTransaction instead of getting a real answer. Same connection-
                # poisoning bug class as the load-bearing "rollback() in close() before
                # returning to pool" rule, just mid-loop instead of at connection-close time.
                try:
                    cur.connection.rollback()
                except Exception as rollback_err:
                    logger.warning(f"[PHASE 1] Rollback after failed dependency check also failed: {rollback_err}")

    if failed_deps:
        # FIX 2026-08-18 (loader-health review): this function returned a full HALT
        # (halted=True, status="halted") for every dependency in `dependencies` above -
        # value_metrics, sec_segment_metrics, positioning_metrics, stock_scores - but this
        # module's own header docstring is explicit: "Metric loaders (growth, quality,
        # value, positioning, stability) are ENRICHMENT ONLY... Stale metrics = WARNING
        # only, trading continues" - and stock_scores is separately documented as
        # generated on-the-fly by Phase 5 from price_daily, not a hard dependency at all.
        # None of price_daily/technical_data_daily/buy_sell_daily (the genuinely
        # halt-worthy tables per that same docstring) are even checked by this function.
        # Live-confirmed 2026-08-18: a real morning run halted entirely on
        # value_metrics->sec_valuations being one trading day behind (structurally
        # unavoidable pre-close, since sec_valuations values the latest CLOSED price and
        # today's close doesn't exist yet during morning/intraday hours) - directly
        # contradicting this file's own "trading continues" policy for exactly this class
        # of dependency. Downgraded to a warning (log + continue), matching every other
        # enrichment-metric staleness check in this same file - never blocks Phase 1 for
        # data that was never meant to gate trading in the first place.
        warning_msg = (
            "[PHASE 1] DEPENDENCY FRESHNESS WARNING (enrichment-only, trading continues):\n"
            + "\n".join(f"  {dep}" for dep in failed_deps[:5])
            + (f"\n  ... and {len(failed_deps) - 5} more" if len(failed_deps) > 5 else "")
        )
        logger.warning(warning_msg)
        log_phase_result_fn(
            1, "dependency_freshness", "warning", f"Upstream dependencies stale (non-blocking): {failed_deps[0]}"
        )
        return None

    logger.info("[PHASE 1] Dependency freshness check: OK")
    return None


def _check_data_patrol_results(cur: Any, log_phase_result_fn: Callable[..., Any]) -> PhaseResult | None:
    """Gate Phase 1 on the most recent DataPatrol run's findings.

    FIX (2026-09-07, goal: XBRL/tie-out data-confidence audit): this module's own docstring
    ("ISSUE #6 FIX: Integrate DataPatrol checks to block Phase 1 if data quality issues
    found... Fails if CRITICAL or ERROR issues found") and terraform/modules/pipeline/main.tf's
    DataPatrol step comment ("Orchestrator Phase 1 reads data_patrol_log; CRITICAL findings
    block trading") both describe this exact behavior - but no code anywhere in
    algo/orchestrator/ or algo/orchestration/ ever actually queried data_patrol_log. Confirmed
    by grep across the whole tree: the only readers were the dashboard/API endpoints
    (lambda/api/routes/algo_handlers/monitoring.py, market/data_quality.py). Live-confirmed
    against the local dev DB the same session this was found: the latest patrol run had 4
    CRITICAL staleness findings (price_daily, technical_data_daily, buy_sell_daily,
    trend_template_data) that Phase 1 would have silently ignored. The tie_out.py balance-sheet/
    EPS/cashflow identity checks and the new XBRL-concept/statistical-anomaly checkers all write
    to this same table - all of it was advisory-only in practice despite the documented intent.

    Deliberately conservative on the fail-open half of that terraform comment ("if patrol
    itself errors, pipeline continues... Phase 1 passes vacuously"): only escalates to a
    warning, not a halt, when no recent patrol run is found, rather than hard-blocking Phase 1
    - this codebase has a documented history of stale-data freshness gates causing real
    false-positive halts (see _validate_dependency_freshness's 2026-08-18 downgrade above), and
    it's unconfirmed whether every local/dev orchestrator invocation runs DataPatrol first.
    Halting on missing patrol data is a reasonable next step once that's confirmed safe.

    Returns: PhaseResult halt if the latest patrol run has CRITICAL or ERROR findings,
    None otherwise (including "no patrol data at all", which only logs a warning).
    """
    patrol_freshness_hours = (
        8  # generous: pipeline runs ~4x/day per CLAUDE.md's morning/afternoon/preclose/evening phases
    )
    try:
        cur.execute("SELECT patrol_run_id, created_at FROM data_patrol_log ORDER BY created_at DESC LIMIT 1")
        latest = cur.fetchone()
        if not latest:
            logger.warning(
                "[PHASE 1] DataPatrol WARNING: data_patrol_log has no rows at all - cannot verify data quality."
            )
            log_phase_result_fn(1, "data_patrol_check", "warning", "data_patrol_log empty - patrol may never have run")
            return None

        latest_run_id, latest_created_at = latest
        cur.execute("SELECT NOW() - %s", (latest_created_at,))
        age = cur.fetchone()[0]
        if age > _timedelta(hours=patrol_freshness_hours):
            logger.warning(
                f"[PHASE 1] DataPatrol WARNING: most recent patrol run ({latest_created_at}) is "
                f"{age} old, past the {patrol_freshness_hours}h freshness window - cannot verify "
                "current data quality. Not halting (see this function's docstring)."
            )
            log_phase_result_fn(1, "data_patrol_check", "warning", f"latest patrol run stale: {age} old")
            return None

        cur.execute(
            """
            SELECT check_name, target_table, message
            FROM data_patrol_log
            WHERE patrol_run_id = %s AND severity IN ('critical', 'error')
            ORDER BY check_name
            """,
            (latest_run_id,),
        )
        blocking = cur.fetchall()
        if blocking:
            findings = [f"{name} ({table}): {msg}" for name, table, msg in blocking]
            summary = "; ".join(findings[:5]) + (f" ... and {len(findings) - 5} more" if len(findings) > 5 else "")
            logger.error(f"[PHASE 1] DataPatrol CRITICAL/ERROR findings block trading: {summary}")
            log_phase_result_fn(
                1, "data_patrol_check", "halt", f"DataPatrol found {len(findings)} blocking issue(s): {summary}"
            )
            return PhaseResult(
                1,
                "data_patrol_check",
                "halted",
                {"patrol_run_id": latest_run_id, "findings": findings},
                True,
                f"DataPatrol found {len(findings)} CRITICAL/ERROR data-quality issue(s) in the latest run "
                f"({latest_run_id}): {summary}. Halting rather than trade on unverified data.",
            )
    except Exception as e:
        # Same fail-safe posture as _validate_dependency_freshness's exception handler: don't
        # let a transient query problem here masquerade as "no issues found".
        logger.warning(f"[PHASE 1] Could not check DataPatrol results: {e}")
        try:
            cur.connection.rollback()
        except Exception as rollback_err:
            logger.warning(f"[PHASE 1] Rollback after failed DataPatrol check also failed: {rollback_err}")
        return None

    logger.info("[PHASE 1] DataPatrol check: OK (no CRITICAL/ERROR findings in latest run)")
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


def _compute_pipeline_context(now_et: Any) -> tuple[bool, bool, str, Any]:
    """Returns (is_market_open, is_after_market_close, pipeline_context, market_close_time).

    BUG FIX 2026-08-24 (goal session: real-money accuracy audit): is_market_open was
    `now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)` - an hour check with NO
    upper bound (true for every hour from 9:30 AM to midnight, every single day) and NO
    trading-day check at all. On any weekend or market holiday, this stayed True from 9:30 AM
    to 4 PM (misclassifying pipeline_context as INTRADAY - implying live trading - on a day
    the market never opened), then True the rest of the day too, masked only by
    is_after_market_close's separate hour>=16 check forcing "EOD" after 4 PM regardless.
    is_after_market_close itself had a second, narrower bug: no early-close awareness. NYSE/
    NASDAQ early closes (day before July 4th, day after Thanksgiving, Christmas Eve) close at
    1:00 PM ET, not 4:00 PM - MarketCalendar already correctly special-cases this (see that
    module's own comment: "this was previously wrong by 2 hours", the same bug class already
    found and fixed there once, and again independently for phase8_entry_execution.py's own
    market-hours guard - see test_phase8_market_hours_early_close.py), but this copy never
    got the same fix - is_after_market_close stayed False for the 3 hours between the real
    1 PM close and this check's hardcoded 4 PM cutoff. Delegate to MarketCalendar (single
    source of truth for trading-day/early-close logic elsewhere in this codebase) instead of
    re-deriving from now_et.hour/minute.
    """
    from datetime import time as _time

    from algo.infrastructure import MarketCalendar

    market_close_time = _time(13, 0) if MarketCalendar.is_early_close(now_et.date()) else _time(16, 0)
    is_market_open = MarketCalendar.is_market_open(now_et)
    is_after_market_close = now_et.time() >= market_close_time
    pipeline_context = "EOD" if is_after_market_close else "INTRADAY" if is_market_open else "MORNING"
    return is_market_open, is_after_market_close, pipeline_context, market_close_time


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


def run(  # noqa: C901 -- inherently a long sequential gate (11 early-return halt checks
    # across price/table/readiness sub-checks); each step now delegates to a named helper
    # in this module or phase1_price_freshness.py/phase1_table_freshness.py/
    # phase1_readiness_checks.py, so the remaining complexity is the halt/continue sequencing
    # itself, not undifferentiated inline logic.
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

    _run_startup_maintenance()

    phase_start = time.time()
    (
        min_coverage_pct,
        min_symbol_count,
        phase1_recent_cutoff_days,
        _phase1_prior_cutoff_days,
        phase1_halt_table_max_tolerance_days,
    ) = _validate_config(config)

    # CRITICAL FIX (Session 82, improved Session 89/94/109): Detect and fail stale RUNNING loaders at phase startup
    # Prevents the "stuck RUNNING for days" Monday failure sequence where a Friday timeout
    # causes Phase 1 Monday to hang, triggering orchestrator halt.
    # SESSION 109 FIX: Changed from time-only (10 min) to progress-aware detection.
    # 60-minute baseline allows slow-initializing loaders (company_info_sec, financial_statements)
    # to start making progress. Only fail if still at 0% after 60 min = truly crashed.
    _detect_and_fail_stale_running_loaders(stale_threshold_minutes=60, progress_threshold_pct=0.1)  # Session 109

    from datetime import datetime as dt

    now_et = dt.now(EASTERN_TZ)
    _is_market_open, _is_after_market_close, pipeline_context, market_close_time = _compute_pipeline_context(now_et)

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
        # REAL-MONEY-READINESS FIX (2026-09-05 audit): this was the one fail-open exception
        # handler in an otherwise consistently fail-closed file - an unexpected error here
        # (e.g. a transient DB issue) used to be logged as "non-fatal" and execution
        # continued straight into the freshness checks below, exactly the "silent data
        # degradation" this dependency check exists to prevent (see the CRITICAL FIX
        # 2026-08-12 comment above). Now halts like every other Phase 1 failure mode.
        logger.error(f"[PHASE 1] Dependency validation check failed unexpectedly: {e}", exc_info=True)
        log_phase_result_fn(
            1,
            "dependency_freshness_check_error",
            "halt",
            f"dependency freshness validation raised unexpectedly: {e}",
        )
        return PhaseResult(
            1,
            "dependency_freshness_check_error",
            "halted",
            {},
            True,
            f"Dependency freshness validation failed unexpectedly: {type(e).__name__}: {e}. "
            "Cannot verify upstream data is fresh - halting rather than risk silent degradation.",
        )

    # DATA PATROL GATE (2026-09-07 fix - see _check_data_patrol_results docstring): the most
    # recent DataPatrol run's tie-out/staleness/XBRL/statistical-anomaly findings now actually
    # block trading on CRITICAL/ERROR, closing a gap where this was documented but never wired.
    try:
        with DatabaseContext("read") as patrol_check_cur:
            patrol_halt = _check_data_patrol_results(patrol_check_cur, log_phase_result_fn)
            if patrol_halt:
                return patrol_halt
    except Exception as e:
        logger.warning(f"[PHASE 1] DataPatrol gate raised unexpectedly, continuing (non-blocking): {e}", exc_info=True)

    preflight_halt = preflight_verify_stock_symbols_table(log_phase_result_fn)
    if preflight_halt:
        return preflight_halt

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                f"SET statement_timeout = {PHASE1_DB_QUERY_TIMEOUT_MS}"
            )  # Database timeout for multi-table checks

            # Find reference date from price_daily (most reliable source)
            max_date, halt_result = resolve_price_daily_max_date(cur, log_phase_result_fn)
            if halt_result:
                return halt_result
            assert max_date is not None  # guaranteed by resolve_price_daily_max_date's contract above

            # CRITICAL: Verify stock_symbols table is pre-loaded (required for ALL loaders)
            symbol_count, halt_result = verify_active_symbol_list(cur, log_phase_result_fn)
            if halt_result:
                return halt_result
            assert symbol_count is not None  # guaranteed by verify_active_symbol_list's contract above

            detect_phantom_price_rows(cur)

            # Market hours: 9:30 AM - 4:00 PM ET.
            # If orchestrator runs DURING market hours (before 16:00 ET), expect previous trading day's data.
            # If orchestrator runs AFTER market close (16:00+ ET), expect same-day data.

            # CRITICAL: Ensure run_date is a date object, not datetime (can come from various sources)
            if isinstance(run_date, dt):
                run_date_obj = run_date.date()
            else:
                run_date_obj = run_date

            last_trading_day = compute_last_trading_day(run_date_obj, pipeline_context)

            acceptable_min_date = compute_acceptable_min_date_with_grace(
                now_et, market_close_time, pipeline_context, last_trading_day
            )

            # CRITICAL FIX 2026-08-06: During EOD context, if we're still before 6 PM ET and only have yesterday's prices,
            # accept them gracefully instead of halting. EOD prices may take 1-2 hours to load after market close.
            acceptable_min_date = apply_eod_yesterday_price_grace(
                pipeline_context, max_date, acceptable_min_date, now_et, last_trading_day
            )

            staleness_halt = check_price_staleness_halt(
                max_date, acceptable_min_date, last_trading_day, log_phase_result_fn
            )
            if staleness_halt:
                return staleness_halt

            # CRITICAL FIX: Require LAST-TRADING-DAY data with actual non-NULL prices, verified via
            # actual symbol coverage (not just MAX(date) >= required) - bounded fallback if stale.
            max_date = _verify_required_date_coverage_or_fallback(
                cur, last_trading_day, symbol_count, run_date_obj, max_date
            )

            _coverage_check_date, symbols_loaded = resolve_coverage_check_date_and_symbols_loaded(
                cur, pipeline_context, now_et, last_trading_day
            )

            eod_today_halt = _check_eod_today_price_completeness(
                cur, pipeline_context, now_et, run_date_obj, min_symbol_count, log_phase_result_fn
            )
            if eod_today_halt:
                return eod_today_halt

            loader_integrity_halt = verify_loader_status_completion_integrity(cur, log_phase_result_fn)
            if loader_integrity_halt:
                return loader_integrity_halt

            coverage_pct, _total_active_symbols = compute_coverage_pct(cur, symbols_loaded)

            coverage_halt = check_price_coverage_halt(
                cur,
                symbols_loaded,
                coverage_pct,
                min_symbol_count,
                min_coverage_pct,
                max_date,
                phase1_recent_cutoff_days,
                log_phase_result_fn,
            )
            if coverage_halt:
                return coverage_halt

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
            # SESSION 116 FIX: Added financial_statements and company_info_sec for visibility.
            # Previously: Only checked as indirect dependencies (via value_metrics/metrics).
            # Now: Direct freshness check warns if stale, allowing early detection.
            warn_tables = {
                "market_exposure_daily": "Market exposure limits (EOD loader)",
                "trend_template_data": "Trend template (Minervini/Weinstein)",
                "sector_ranking": "Sector rankings",
                # NOTE: "financial_statements" is a pipeline/loader name (load_financial_statements.py),
                # not a real table - it writes to annual_income_statement, annual_balance_sheet,
                # annual_cash_flow, quarterly_income_statement, quarterly_balance_sheet,
                # quarterly_cash_flow (see loaders/loader_registry.py). Checking a nonexistent
                # "financial_statements" relation raised "relation does not exist" and halted
                # trading (confirmed live 2026-08-16). Using annual_income_statement as the
                # representative table - it and its siblings are written together per symbol.
                "annual_income_statement": "Financial statement data (SESSION 116 FIX: for visibility)",
                "company_info_sec": "Company SEC information (SESSION 116 FIX: for visibility)",
                "growth_metrics": "Growth metrics (enrichment only)",
                "quality_metrics": "Quality metrics (enrichment only)",
                "value_metrics": "Value metrics (enrichment only)",
                "positioning_metrics": "Positioning metrics (enrichment only)",
                "stability_metrics": "Stability metrics (enrichment only)",
            }
            # Only check tables that have a date column for freshness
            date_checked_tables = {**halt_tables, **warn_tables}

            vix_max_date, health_max_date = _fetch_vix_and_health_reference_dates(cur)

            # CRITICAL FIX (Session 288): Validate UPSTREAM reference tables are fresh
            # before using them to validate downstream tables.
            halt_stale: list[str] = []  # pipeline-loaded tables - stale = HALT
            halt_stale.extend(check_upstream_health_staleness(health_max_date, acceptable_min_date))

            table_reference_dates = build_table_reference_dates(
                vix_max_date, health_max_date, run_date, acceptable_min_date
            )

            warn_stale, stale_table_details, freshness_check_halt = check_all_tables_freshness(
                cur,
                date_checked_tables,
                halt_tables,
                table_reference_dates,
                phase1_halt_table_max_tolerance_days,
                halt_stale,
                log_phase_result_fn,
            )
            if freshness_check_halt:
                return freshness_check_halt

            halt_stale_result = handle_halt_stale_tables(
                halt_stale, date_checked_tables, stale_table_details, log_phase_result_fn
            )
            if halt_stale_result:
                return halt_stale_result

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

            degraded_reason, readiness_halt = validate_stock_scores_readiness(cur, halt_tables, log_phase_result_fn)
            if readiness_halt:
                return readiness_halt

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
            phase_data = {
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
            portfolio_halt = validate_portfolio_symbol_prices(cur, phase_data, log_phase_result_fn)
            if portfolio_halt:
                return portfolio_halt

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

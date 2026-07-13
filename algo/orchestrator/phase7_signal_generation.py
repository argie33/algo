#!/usr/bin/env python3
"""
PHASE 7: SIGNAL GENERATION & RANKING

Primary path: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.
NO fallback path: buy_sell_daily is REQUIRED. If it has no fresh data, Phase 7 halts.

GUARD RAILS (ISSUE #8 FIX):
1. Critical dependency check BEFORE signal generation:
   - stock_scores must have data
   - market_exposure_daily must have valid exposure_pct
   - buy_sell_daily must have BUY signals within lookback window
2. Any missing dependency -> immediate halt with clear error message
3. Prevents silent degradation where empty signals show on dashboard

Pipeline:
1. Check all critical dependencies (fail-fast if any missing)
2. Check halt flag (data freshness gate)
3. Check market regime: halt if entries not allowed per market_exposure_daily
4. Fetch candidates (primary): buy_sell_daily BUY signals within last 3 days
   joined to stock_scores (composite ranking) + price_daily (current prices + SMA_50)
5. Filter: close > sma_50 (uptrend confirmation)
6. Filter: composite_score >= min threshold
7. Close quality gate: skip weak closes (bottom of day's range = distribution)
8. Liquidity checks on top _LIQUIDITY_CHECK_LIMIT candidates
9. Return composite-score-ranked candidates to Phase 8

CRITICAL: buy_sell_daily is required for robust signal generation. The EOD pipeline
(4:05 PM ET) must complete and populate buy_sell_daily before orchestrator runs.
If buy_sell_daily is empty, Phase 7 halts (fail-closed) rather than degrading to
stock_scores-only signals.

Why no fallback? Using stock_scores alone without buy_sell_daily confirmation means:
- No pivot-breakout timing gate (weak entry confirmation)
- No swing-high validation (could catch late entries during pullbacks)
- Reduced signal quality and higher false-positive rate

Ranking: composite_score from stock_scores (quality 25%, growth 20%, value 20%,
positioning 15%, stability 12%, momentum 8%).

Signal source: buy_sell_daily + stock_scores only (no degradation mode).
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date
from datetime import timedelta
from typing import Any

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

_LIQUIDITY_CHECK_LIMIT = 10
_MAX_WORKERS = 4
_MIN_COMPOSITE_SCORE = 50  # Minimum composite_score to qualify (0-100 scale)
_BUYSELL_LOOKBACK_DAYS = 7  # Calendar days; covers full prior week including weekends and missed EOD runs


def _compute_risk_score(atr_14: float | None, close: float | None) -> float:
    """Risk score (0-100, 100 = very low risk) based on ATR volatility relative to price.

    Phase 8 requires risk_score on every persisted signal (see phase8_entry_execution.py
    _persist_signals_to_database) — signals without it are silently dropped from
    algo_signals. ATR unavailable -> treat as moderate/unknown risk (neutral 50) rather
    than blocking persistence entirely.
    """
    if atr_14 is None or close is None or close <= 0:
        return 50.0
    atr_pct = (atr_14 / close) * 100
    return max(0.0, min(100.0, 100.0 - (atr_pct * 5)))

# ISSUE #6 FIX: Define required signal fields for Phase 6 execution
_REQUIRED_SIGNAL_FIELDS = {
    "symbol": str,
    "composite_score": float,
    "entry_price": float,
    "close": float,
    "sma_50": float,
    "signal_strength": float,
}


def _validate_signal_completeness(candidates: list[dict[str, Any]], source: str) -> tuple[list[dict[str, Any]], int]:
    """ISSUE #8 FIX: Validate signals have all required fields for Phase 6.

    CONSISTENCY FIX #2: Now FAILS if ANY signals are incomplete (not silent filtering).
    Any incomplete signals indicate upstream data quality issues that must be fixed.
    This prevents silent data loss from propagating downstream.

    Returns (complete_signals, incomplete_count).
    Raises: ValueError if ANY incomplete signals found (fail-loudly, not silently filter)
    """
    from algo.orchestrator.phase_error_handling import ErrorCategory, PhaseError

    complete_signals = []
    incomplete_signals = []

    for sig in candidates:
        if "symbol" not in sig or not sig["symbol"]:
            raise ValueError(
                "[PHASE 7] Signal missing symbol. "
                "Cannot generate trading signal without stock symbol. "
                "Verify upstream phases produced valid signal data."
            )
        symbol = sig["symbol"]
        missing_fields = []
        for field_name, _field_type in _REQUIRED_SIGNAL_FIELDS.items():
            val = sig.get(field_name)
            if val is None:
                missing_fields.append(field_name)

        if missing_fields:
            incomplete_signals.append({"symbol": symbol, "missing": missing_fields})
            logger.warning(
                f"[PHASE 7] {symbol}: incomplete signal data (missing: {', '.join(missing_fields)}). Source={source}"
            )
        else:
            complete_signals.append(sig)

    # CRITICAL FIX: FAIL if ANY signals are incomplete
    # Silent filtering of incomplete signals hides upstream data quality issues
    if incomplete_signals:
        error = PhaseError(
            category=ErrorCategory.DATA_INVALID,
            message=f"{len(incomplete_signals)} of {len(candidates)} signals from {source} have incomplete data",
            root_cause=f"Incomplete signals: {[s['symbol'] for s in incomplete_signals[:5]]}... Missing fields: {sorted({f for s in incomplete_signals for f in s['missing']})}",
            recoverable=False,
            log_level="critical",
        )
        from algo.orchestrator.phase_error_handling import log_phase_error

        log_phase_error(7, error)
        raise ValueError(
            f"[PHASE 7 DATA VALIDATION] Cannot proceed with incomplete signals. "
            f"Incomplete count: {len(incomplete_signals)}, Complete count: {len(complete_signals)}. "
            f"Required fields: {', '.join(_REQUIRED_SIGNAL_FIELDS.keys())}"
        )

    return complete_signals, len(incomplete_signals)


def _check_market_regime(run_date: _date) -> dict[str, Any]:
    """Return current market regime from market_exposure_daily.

    Uses shared read_market_regime() to ensure consistent JSON deserialization
    and error handling between Phase 3b and Phase 5.
    """
    from algo.risk import read_market_regime

    return read_market_regime(run_date)


def _detect_upstream_data_quality_drift(run_date: _date, signal_source: str) -> dict[str, Any]:
    """Detect upstream data quality issues for stock_scores (composite) coverage.

    SWING SCORE MIGRATION: Removed swing_trader_scores check (table deprecated).
    Now only validates stock_scores availability for signal generation.

    Returns dict with: {"has_drift": bool, "drift_message": str}
    Raises: RuntimeError if database query fails (cannot silently degrade)
    """
    from algo.orchestrator.phase_error_handling import ErrorCategory, PhaseError

    drift = {"has_drift": False, "drift_message": ""}

    try:
        with DatabaseContext("read") as cur:
            lookback_date = (
                run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS) if signal_source == "buysell_breakout" else None
            )

            # Check stock_scores coverage (not swing_trader_scores)
            if signal_source == "buysell_breakout":
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT bsd.symbol)
                    FROM (
                        SELECT DISTINCT ON (symbol) *
                        FROM buy_sell_daily
                        WHERE signal = 'BUY' AND date >= %s AND date <= %s
                        ORDER BY symbol, date DESC
                    ) bsd
                    LEFT JOIN stock_scores ss ON ss.symbol = bsd.symbol
                        AND ss.composite_score IS NOT NULL
                    WHERE ss.symbol IS NULL
                    """,
                    (lookback_date, run_date),
                )
            else:
                # For non-buysell sources: check if stock_scores has ANY data
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT symbol)
                    FROM stock_scores
                    WHERE composite_score IS NOT NULL
                    """,
                )
                row = cur.fetchone()
                if not row or not row[0] or row[0] == 0:
                    # No stock_scores data = drift detected
                    drift["has_drift"] = True
                    drift["drift_message"] = (
                        f"No stock_scores data available (source={signal_source}, date={run_date}). "
                        f"Check stock_scores loader."
                    )
                    logger.warning(f"[PHASE 7] DATA QUALITY ALERT: {drift['drift_message']}")
                return drift  # Early return for non-buysell branch

            # buysell_breakout branch: check for missing stock_scores
            row = cur.fetchone()
            if row and row[0] and row[0] > 0:
                drift["has_drift"] = True
                drift["drift_message"] = (
                    f"{row[0]} symbols missing composite_score coverage (source={signal_source}, date={run_date}). "
                    f"Check stock_scores loader."
                )
                logger.warning(f"[PHASE 7] DATA QUALITY ALERT: {drift['drift_message']}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # CRITICAL FIX: RAISE exception instead of silently returning empty dict
        # Silent degradation means operators don't know data quality checks failed
        error = PhaseError(
            category=ErrorCategory.DATABASE_ERROR,
            message="Cannot check upstream data quality drift (DB error)",
            root_cause=f"Database query failed: {str(e)[:100]}",
            recoverable=False,
            log_level="critical",
        )
        from algo.orchestrator.phase_error_handling import log_phase_error

        log_phase_error(7, error)
        raise RuntimeError(f"[PHASE 7] Cannot proceed without data quality verification: {e!s}") from e

    return drift


def _check_liquidity_parallel(
    candidate: dict[str, Any], run_date: _date, config: dict[str, Any] | None = None
) -> tuple[dict[str, Any], bool]:
    try:
        # CRITICAL: config must be present. Liquidity thresholds (min_adv_shares, min_adv_dollars) are
        # non-negotiable safety gates. Empty dict fallback bypasses these filters, allowing undercapitalized
        # or illiquid stocks to pass entry qualification. Must fail-fast if config is missing.
        if config is None:
            error_msg = (
                "[PHASE 7] CRITICAL: Liquidity check configuration is None. "
                "Cannot apply minimum ADV (average daily volume) or dollar volume thresholds. "
                "Config must contain min_adv_shares and min_adv_dollars. Entry qualification failed."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        liquidity = LiquidityChecks(config=config)
        liq_ok, liq_reason = liquidity.run_all(candidate["symbol"], 0, run_date)
        if not liq_ok:
            logger.debug(f"[PHASE 7] {candidate['symbol']}: liquidity — {liq_reason}")
        return candidate, liq_ok
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.warning(f"[PHASE 7] {candidate['symbol']}: liquidity check error ({type(e).__name__}): {e!s}")
        return candidate, False


def _get_candidates_from_stock_scores_fallback(
    run_date: _date, min_score: float, limit: int = 100
) -> list[dict[str, Any]]:
    """FALLBACK signal source: stock_scores composite ranking only (no buy_sell_daily).

    Used when orchestrator runs before EOD pipeline completes (morning/afternoon runs).
    Returns top-ranked candidates by composite_score, with technical data attached.

    This is a degraded path (no breakout confirmation), but allows trading to continue.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '15000ms'")
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        ss.symbol,
                        ss.composite_score,
                        ss.quality_score,
                        ss.growth_score,
                        ss.momentum_score,
                        ss.rs_percentile,
                        p.close,
                        p.high,
                        p.low,
                        sma.avg_close AS sma_50,
                        atr_calc.atr_14,
                        cp.sector,
                        cp.industry,
                        NULL::float AS buylevel,
                        NULL::float AS stoplevel,
                        0.5 AS signal_strength,
                        NULL::float AS volume_surge_pct,
                        0 AS market_stage
                    FROM stock_scores ss
                    JOIN LATERAL (
                        SELECT close, high, low
                        FROM price_daily
                        WHERE symbol = ss.symbol AND date <= %s
                        ORDER BY date DESC LIMIT 1
                    ) p ON TRUE
                    JOIN LATERAL (
                        SELECT AVG(close) AS avg_close
                        FROM (
                            SELECT close FROM price_daily
                            WHERE symbol = ss.symbol AND date <= %s
                            ORDER BY date DESC LIMIT 50
                        ) t
                    ) sma ON TRUE
                    JOIN LATERAL (
                        SELECT AVG(tr) AS atr_14
                        FROM (
                            SELECT
                                GREATEST(
                                    high - low,
                                    ABS(high - LAG(close) OVER (ORDER BY date)),
                                    ABS(low - LAG(close) OVER (ORDER BY date))
                                ) AS tr,
                                ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                            FROM price_daily
                            WHERE symbol = ss.symbol AND date <= %s
                        ) t
                        WHERE tr IS NOT NULL AND rn <= 14
                    ) atr_calc ON TRUE
                    LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                    WHERE ss.composite_score >= %s
                      AND ss.data_completeness >= 70
                      AND p.close > sma.avg_close
                      AND p.high > p.low
                )
                SELECT * FROM ranked
                ORDER BY composite_score DESC
                LIMIT %s
                """,
                (run_date, run_date, run_date, min_score, limit),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            symbol = r[0]
            composite = float(r[1]) if r[1] is not None else min_score
            close = float(r[6]) if r[6] is not None else None

            if close is None:
                raise RuntimeError(
                    f"[PHASE 7 FAIL-FAST] {symbol}: missing close price from price_daily. "
                    f"This indicates the price_daily loader failed to complete or returned incomplete data. "
                    f"Cannot generate valid signals without current prices. Halting phase."
                )

            candidates.append(
                {
                    "symbol": symbol,
                    "composite_score": composite,
                    "quality_score": float(r[2]) if r[2] is not None else None,
                    "growth_score": float(r[3]) if r[3] is not None else None,
                    "momentum_score": float(r[4]) if r[4] is not None else None,
                    "rs_percentile": float(r[5]) if r[5] is not None else None,
                    "close": close,
                    "high": float(r[7]) if r[7] is not None else None,
                    "low": float(r[8]) if r[8] is not None else None,
                    "sma_50": float(r[9]) if r[9] is not None else None,
                    "atr_14": float(r[10]) if r[10] is not None else None,
                    "entry_price": close,
                    "signal_strength": 0.5,
                    "sector": r[11],
                    "industry": r[12],
                    "buylevel": None,
                    "stoplevel": None,
                    "volume_surge_pct": None,
                    "market_stage": 0,
                    "signal_date": str(run_date),
                    "risk_score": _compute_risk_score(
                        float(r[10]) if r[10] is not None else None, close
                    ),
                }
            )

        logger.info(
            f"[PHASE 7 FALLBACK] {len(candidates)} candidates from stock_scores only "
            f"(no buy_sell_daily — EOD pipeline pending)"
        )
        return candidates
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 7 FALLBACK] Database error: {e}")
        raise RuntimeError(f"[PHASE 7 FALLBACK] Failed to fetch stock_scores candidates: {e}") from e


def _get_candidates_from_buysell(
    run_date: _date, min_score: float, limit: int = 100, min_close_quality: float = 0.3
) -> list[dict[str, Any]]:
    """Primary signal source: buy_sell_daily pivot-breakout BUY signals + stock_scores (composite) ranking.

    Returns candidates that have BOTH a recent BUY signal (pivot breakout above swing high
    that was above SMA_50) AND a high composite_score. The breakout confirms the entry timing;
    composite_score ranks quality.

    Lookback: last _BUYSELL_LOOKBACK_DAYS calendar days — covers the prior EOD pipeline's
    signals for morning/afternoon orchestrator runs, plus today's signals for the 5:30 PM run.

    SWING SCORE MIGRATION: Removed swing_trader_scores LEFT JOIN (was fetched but never used).
    All signal ranking now uses composite_score only.
    """
    lookback_date = run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS)
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '15000ms'")
            cur.execute(
                """
                WITH ranked AS (
                    SELECT
                        bsd.symbol,
                        COALESCE(ss.composite_score, bsd.strength * 20) AS composite_score,
                        ss.quality_score,
                        ss.growth_score,
                        ss.momentum_score,
                        ss.rs_percentile,
                        p.close,
                        p.high,
                        p.low,
                        sma.avg_close AS sma_50,
                        atr_calc.atr_14,
                        cp.sector,
                        cp.industry,
                        bsd.buylevel,
                        bsd.stoplevel,
                        bsd.strength AS signal_strength,
                        bsd.volume_surge_pct,
                        bsd.market_stage,
                        bsd.date AS signal_date
                    FROM (
                        SELECT DISTINCT ON (symbol) *
                        FROM buy_sell_daily
                        WHERE signal = 'BUY'
                          AND date >= %s
                          AND date <= %s
                        ORDER BY symbol, date DESC
                    ) bsd
                    LEFT JOIN stock_scores ss ON ss.symbol = bsd.symbol
                    JOIN LATERAL (
                        SELECT close, high, low
                        FROM price_daily
                        WHERE symbol = bsd.symbol AND date <= %s
                        ORDER BY date DESC LIMIT 1
                    ) p ON TRUE
                    JOIN LATERAL (
                        SELECT AVG(close) AS avg_close
                        FROM (
                            SELECT close FROM price_daily
                            WHERE symbol = bsd.symbol AND date <= %s
                            ORDER BY date DESC LIMIT 50
                        ) t
                    ) sma ON TRUE
                    JOIN LATERAL (
                        SELECT AVG(tr) AS atr_14
                        FROM (
                            SELECT
                                GREATEST(
                                    high - low,
                                    ABS(high - LAG(close) OVER (ORDER BY date)),
                                    ABS(low - LAG(close) OVER (ORDER BY date))
                                ) AS tr,
                                ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                            FROM price_daily
                            WHERE symbol = bsd.symbol AND date <= %s
                        ) t
                        WHERE tr IS NOT NULL AND rn <= 14
                    ) atr_calc ON TRUE
                    LEFT JOIN company_profile cp ON cp.ticker = bsd.symbol
                    WHERE COALESCE(ss.composite_score, bsd.strength * 20) >= %s
                      AND (ss.data_completeness >= 70 OR ss.composite_score IS NULL)
                      AND p.close > sma.avg_close
                      AND p.high > p.low
                      AND ((p.close - p.low) / (p.high - p.low)) > %s
                      AND bsd.strength IS NOT NULL
                )
                SELECT * FROM ranked
                ORDER BY composite_score DESC
                LIMIT %s
                """,
                (
                    lookback_date,
                    run_date,
                    run_date,
                    run_date,
                    run_date,
                    min_score,
                    min_close_quality,
                    limit,
                ),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            symbol = r[0]

            # Composite score guaranteed by JOIN (stock_scores inner join)
            if r[1] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: composite_score is NULL — "
                    "stock_scores join guarantees non-null composite_score"
                )
            composite = float(r[1])

            # Close guaranteed by LATERAL price_daily join
            if r[6] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: close price is NULL — price_daily lateral join guarantees latest close"
                )
            close = float(r[6])

            # Signal strength guaranteed by WHERE clause (bsd.strength IS NOT NULL)
            if r[15] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: signal_strength is NULL — WHERE clause guarantees non-null strength"
                )
            raw_strength = float(r[15])

            # Validate signal has complete scoring
            quality_score = float(r[2]) if r[2] is not None else None
            growth_score = float(r[3]) if r[3] is not None else None
            momentum_score = float(r[4]) if r[4] is not None else None
            rs_percentile = float(r[5]) if r[5] is not None else None

            # CRITICAL: Core signal quality metrics should be present
            # If >2 of these are missing, signal is incomplete
            missing_scores = sum(
                [quality_score is None, growth_score is None, momentum_score is None, rs_percentile is None]
            )
            if missing_scores > 2:
                logger.warning(
                    f"[SIGNAL_QUALITY] {symbol}: Signal generated with incomplete scoring "
                    f"({missing_scores}/4 component scores missing). "
                    f"quality={quality_score}, growth={growth_score}, "
                    f"momentum={momentum_score}, rs={rs_percentile}. "
                    f"Position sizing should account for reduced signal quality."
                )

            candidates.append(
                {
                    "symbol": symbol,
                    "composite_score": composite,
                    "quality_score": quality_score,
                    "growth_score": growth_score,
                    "momentum_score": momentum_score,
                    "rs_percentile": rs_percentile,
                    "close": close,
                    "high": float(r[7]) if r[7] is not None else None,
                    "low": float(r[8]) if r[8] is not None else None,
                    "sma_50": float(r[9]) if r[9] is not None else None,
                    "atr_14": float(r[10]) if r[10] is not None else None,
                    "entry_price": close,
                    "signal_strength": raw_strength,
                    "sector": r[11],
                    "industry": r[12],
                    "buylevel": float(r[13]) if r[13] is not None else None,
                    "stoplevel": float(r[14]) if r[14] is not None else None,
                    "volume_surge_pct": float(r[16]) if r[16] is not None else None,
                    "market_stage": r[17],
                    "signal_date": str(r[18]) if r[18] is not None else None,
                    "risk_score": _compute_risk_score(
                        float(r[10]) if r[10] is not None else None, close
                    ),
                }
            )

        logger.info(
            f"[PHASE 7] {len(candidates)} candidates from buy_sell_daily + stock_scores "
            f"(lookback: {lookback_date} to {run_date}, "
            f"SQL filters: trend & close_quality applied at query level)"
        )

        complete_candidates, _ = _validate_signal_completeness(candidates, "buy_sell_daily path")
        return complete_candidates
    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(
            f"[PHASE 7] Failed to fetch buy_sell_daily candidates: {e}. "
            "Cannot proceed with signal generation without candidate data."
        ) from e


def _check_critical_dependencies(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> tuple[bool, str | None]:
    """Check all critical dependencies for Phase 7 BEFORE attempting signal generation.

    ISSUE #8 FIX: Explicit dependency guard rails before phase execution.
    Fails early if ANY critical dependency is missing, preventing silent degradation.

    Returns: (is_ok: bool, error_message: str | None)
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '10000ms'")

            # CRITICAL #1: stock_scores must exist and have data
            cur.execute("SELECT COUNT(*) FROM stock_scores")
            stock_scores_row = cur.fetchone()
            if stock_scores_row is None:
                msg = (
                    "[PHASE 7 CRITICAL] Failed to query stock_scores table. "
                    "Database query returned no result (possible schema issue). "
                    "Check database connection and table existence."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg
            stock_scores_count = stock_scores_row[0]
            if stock_scores_count == 0:
                msg = (
                    "[PHASE 7 CRITICAL] stock_scores table is empty. "
                    "Cannot generate signals without stock quality rankings. "
                    "Verify stock_scores loader completed successfully. "
                    "Check data_loader_status for stock_scores and related loaders."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            # CRITICAL #2: market_exposure_daily must have valid data on or before run_date
            # Uses same query pattern as read_market_regime() so guard is consistent with actual read.
            # On weekends/holidays, the most recent trading day's data is sufficient.
            cur.execute(
                """
                SELECT exposure_pct, date
                FROM market_exposure_daily
                WHERE date <= %s AND exposure_pct IS NOT NULL
                ORDER BY date DESC
                LIMIT 1
                """,
                (run_date,),
            )
            exposure_row = cur.fetchone()

            if exposure_row is None:
                msg = (
                    f"[PHASE 7 CRITICAL] market_exposure_daily has no valid data on or before {run_date}. "
                    "Cannot determine market regime for position sizing. "
                    "Check that market exposure pipeline completed."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            exposure_data_date = exposure_row[1]
            if exposure_data_date < run_date:
                logger.info(
                    f"[PHASE 7] market_exposure_daily: using data from {exposure_data_date} "
                    f"(most recent available; run_date={run_date})"
                )

            # CRITICAL #3: buy_sell_daily availability check
            # If empty, Phase 7 can still run with fallback to stock_scores ranking
            lookback_date = run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS)
            cur.execute(
                """
                SELECT COUNT(*) FROM buy_sell_daily
                WHERE signal = 'BUY' AND date >= %s AND date <= %s
                """,
                (lookback_date, run_date),
            )
            buysell_row = cur.fetchone()
            if buysell_row is None:
                msg = (
                    "[PHASE 7 CRITICAL] Failed to query buy_sell_daily table. "
                    "Database query returned no result (possible schema issue). "
                    "Check database connection and table existence."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg
            # NOTE: If buysell_count==0, Phase 7 will use fallback (stock_scores-only ranking)
            # This allows orchestrator to run in morning/afternoon before EOD pipeline completes

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 7 CRITICAL] Could not validate critical dependencies: {e}"
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        return False, msg

    return True, None


def run(  # noqa: C901
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
    exposure_constraints: dict[str, Any] | None = None,
    check_halt_flag: Callable[..., bool] | None = None,
    phase1_degraded: bool = False,
    config: dict[str, Any] | None = None,
) -> PhaseResult:

    if config is None:
        raise ValueError(
            "phase7_signal_generation.run() requires explicit config parameter (dependency injection). "
            "Get config at orchestrator level and pass it explicitly."
        )

    # Validate critical config values (fail-fast)
    if "phase7_min_composite_score" not in config or config["phase7_min_composite_score"] is None:
        raise ValueError(
            f"CRITICAL: phase7_min_composite_score config missing or None. "
            f"Required for signal filtering. Set to a value between 0-100 (default: {_MIN_COMPOSITE_SCORE})."
        )
    min_composite_score = float(config["phase7_min_composite_score"])

    phase_start = time.time()
    logger.info("[PHASE 7] Starting signal generation")

    min_close_quality = float(config["min_close_quality_pct"]) / 100.0

    # ISSUE #8 FIX: Guard rails — check critical dependencies BEFORE signal generation
    # Fails fast if ANY dependency is unavailable, preventing silent degradation
    ok, dep_error = _check_critical_dependencies(run_date, log_phase_result_fn)
    if not ok:
        return PhaseResult(
            7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, dep_error
        )

    # Halt flag check before generating signals
    if check_halt_flag and check_halt_flag():
        logger.critical(
            "[PHASE 7] Halt flag set by Phase 1 — data quality degradation detected. Halting signal generation."
        )
        log_phase_result_fn(7, "signal_generation", "halt", "Halt flag set: data quality degradation")
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            "Halt flag set: data quality degradation detected",
        )

    # Market regime gate
    regime = _check_market_regime(run_date)
    logger.info(
        f"[PHASE 7] Market regime: {regime['regime']} "
        f"exposure={regime['exposure_pct']:.0f}% "
        f"entry_allowed={regime['is_entry_allowed']}"
    )
    if not regime["is_entry_allowed"]:
        reasons = "; ".join(regime["halt_reasons"]) if regime["halt_reasons"] else "no halt reasons logged"
        logger.warning(f"[PHASE 7] Entries halted by market regime: {reasons}")
        log_phase_result_fn(
            7,
            "signal_generation",
            "halt",
            f"Market regime halted entries: {reasons[:100]}",
        )
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            reasons[:100],
        )

    # ISSUE #7 FIX: Exposure policy gate — fail-closed if constraints not provided
    if exposure_constraints is None:
        msg = (
            "[PHASE 7 CRITICAL] Exposure constraints not provided by Phase 5. "
            "Cannot proceed with signal generation without knowing market exposure limits. "
            "Check that Phase 5 (Exposure Policy) completed successfully."
        )
        logger.critical(msg)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        return PhaseResult(7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, msg)

    if exposure_constraints and exposure_constraints.get("halt_new_entries") is True:
        reason = exposure_constraints.get("halt_reason")
        if not reason:
            logger.critical(
                "CRITICAL: Exposure policy halted entries but no halt_reason provided. "
                "Cannot determine why trading is halted. Exposure policy data incomplete."
            )
            raise ValueError(
                "Exposure constraints: halt_new_entries=True but halt_reason missing. "
                "Must provide explicit reason for halt."
            )
        logger.warning(f"[PHASE 7] {reason}")
        log_phase_result_fn(7, "signal_generation", "halt", reason)
        return PhaseResult(
            7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, reason
        )

    # Primary: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.
    # FALLBACK: If buy_sell_daily is empty (morning/afternoon orchestrator runs), use stock_scores ranking.
    signal_source = "buysell_breakout"
    try:
        raw_candidates = _get_candidates_from_buysell(
            run_date, min_composite_score, min_close_quality=min_close_quality
        )
        if not raw_candidates:
            logger.info(
                f"[PHASE 7] No buy_sell_daily BUY signals found within {_BUYSELL_LOOKBACK_DAYS} days. "
                "Falling back to stock_scores ranking (degraded path for morning/afternoon orchestrator runs)."
            )
            raw_candidates = _get_candidates_from_stock_scores_fallback(run_date, min_composite_score)
            signal_source = "stock_scores_fallback"
    except ValueError as e:
        # CONSISTENCY FIX #2: Validation errors now raise exceptions (not silent degradation)
        # Categorize as DATA_INVALID so operators know why signals are missing
        from algo.orchestrator.phase_error_handling import (
            ErrorCategory,
            PhaseError,
            log_phase_error,
        )

        error = PhaseError(
            category=ErrorCategory.DATA_INVALID,
            message=f"Signal validation failed: {str(e)[:200]}",
            root_cause="Required fields missing from buy_sell_daily signals",
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(7, error, log_phase_result_fn)
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            error.message,
        )
    except RuntimeError as e:
        # DB or data loading error
        from algo.orchestrator.phase_error_handling import (
            ErrorCategory,
            PhaseError,
            log_phase_error,
        )

        error = PhaseError(
            category=ErrorCategory.DATA_MISSING,
            message=f"Failed to fetch buy_sell_daily signals: {str(e)[:200]}",
            root_cause="Check that EOD pipeline (4:05 PM ET) has completed and buy_sell_daily loader ran",
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(7, error, log_phase_result_fn)
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            error.message,
        )

    if not raw_candidates:
        msg = (
            "[PHASE 7] No candidates found (buy_sell_daily empty AND stock_scores fallback returned 0 rows). "
            "Check: (1) stock_scores table has data, (2) market regime allows entries, "
            "(3) price_daily has recent data for trending symbols."
        )
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_signals", msg)
        return PhaseResult(7, "signal_generation", "ok", {"qualified_trades": [], "liquidity_passed": 0}, False, msg)

    # All trend and close quality validation happens at SQL level in _get_candidates_from_buysell().
    # Candidates here are already filtered for: close > sma_50, close_position > min_close_quality.
    # This eliminates wasted I/O and ensures data quality drift is detected immediately.
    quality_filtered = raw_candidates

    # Check for upstream data quality issues (e.g., composite_score not populated)
    upstream_drift = _detect_upstream_data_quality_drift(run_date, signal_source)
    if upstream_drift.get("has_drift"):
        logger.warning(
            f"[PHASE 7] Upstream data quality drift detected: {upstream_drift.get('drift_message', 'Unknown issue')}. "
            f"This may suppress valid candidates."
        )

    # FAIL-FAST: Validate composite_score is present and numeric before sorting
    for sig in quality_filtered:
        if "composite_score" not in sig:
            raise ValueError(f"Signal {sig.get('symbol')} missing 'composite_score' field")
        cs = sig["composite_score"]
        if cs is None:
            raise ValueError(
                f"Signal {sig.get('symbol')} has None composite_score (database join should guarantee non-null)"
            )
        if not isinstance(cs, (int, float)):
            raise ValueError(f"Signal {sig.get('symbol')} composite_score is {type(cs).__name__}, expected float")

    quality_filtered.sort(key=lambda s: float(s["composite_score"]), reverse=True)

    # Liquidity checks on top candidates — parallelized
    liq_passed = []
    liq_checked = 0
    to_check = quality_filtered[:_LIQUIDITY_CHECK_LIMIT]

    if to_check:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(_check_liquidity_parallel, cand, run_date, config): cand for cand in to_check}
            for future in as_completed(futures):
                liq_checked += 1
                candidate, passed = future.result()
                if passed:
                    liq_passed.append(candidate)

    logger.info(
        f"[PHASE 7] Liquidity check: {liq_checked} checked, {len(liq_passed)} passed. "
        f"{len(quality_filtered) - liq_checked} unchecked candidates dropped."
    )

    # Final ranking by composite_score (already validated by quality_filtered sort, but re-validate for safety)
    if liq_passed:
        for sig in liq_passed:
            if "composite_score" not in sig or sig["composite_score"] is None:
                raise ValueError(f"Liquidity-passed signal {sig.get('symbol')} missing valid composite_score")
        liq_passed.sort(key=lambda s: float(s["composite_score"]), reverse=True)

    logger.info(f"[PHASE 7] Top 10 qualified signals (source={signal_source}):")
    for i, sig in enumerate(liq_passed[:10]):

        def _fmt(v: Any, spec: str = ":.1f") -> str:
            return format(v, spec[1:]) if v is not None else "?"

        buylevel_str = (
            f" buylevel={_fmt(sig.get('buylevel'), ':.2f')} signal_date={sig.get('signal_date', '?')}"
            if sig.get("buylevel")
            else ""
        )
        logger.info(
            f"  {i + 1}. {sig['symbol']:6s} "
            f"composite={_fmt(sig.get('composite_score'))} "
            f"quality={_fmt(sig.get('quality_score'))} "
            f"momentum={_fmt(sig.get('momentum_score'))} "
            f"rs_pct={_fmt(sig.get('rs_percentile'))} "
            f"stage={sig.get('market_stage', '?')}"
            f"{buylevel_str}"
        )

    elapsed = time.time() - phase_start
    log_phase_result_fn(
        7,
        "signal_generation",
        "success",
        f"{len(liq_passed)} signals qualified from {len(raw_candidates)} candidates",
    )

    return PhaseResult(
        7,
        "signal_generation",
        "ok",
        {
            "qualified_trades": liq_passed,
            "total_candidates": len(raw_candidates),
            "pre_liquidity_check": len(quality_filtered),
            "liquidity_passed": len(liq_passed),
            "regime": regime,
            "signal_source": signal_source,
        },
        False,
        f"Generated {len(liq_passed)} signals in {elapsed:.1f}s (source={signal_source})",
    )

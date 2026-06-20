#!/usr/bin/env python3
"""
PHASE 5: SIGNAL GENERATION

Primary path: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.
NO fallback path: buy_sell_daily is REQUIRED. If it has no fresh data, Phase 5 halts.

Pipeline:
1. Check halt flag (data freshness gate)
2. Check market regime: halt if entries not allowed per market_exposure_daily
3. Fetch candidates (primary): buy_sell_daily BUY signals within last 3 days
   joined to stock_scores (composite ranking) + price_daily (current prices + SMA_50)
4. Filter: close > sma_50 (uptrend confirmation)
5. Filter: composite_score >= min threshold
6. Close quality gate: skip weak closes (bottom of day's range = distribution)
7. Liquidity checks on top _LIQUIDITY_CHECK_LIMIT candidates
8. Return composite-score-ranked candidates to Phase 6

CRITICAL: buy_sell_daily is required for robust signal generation. The EOD pipeline
(4:05 PM ET) must complete and populate buy_sell_daily before orchestrator runs.
If buy_sell_daily is empty, Phase 5 halts (fail-closed) rather than degrading to
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

import psycopg2

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from config.thresholds import ThresholdConfig
from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)

_LIQUIDITY_CHECK_LIMIT = 10
_MAX_WORKERS = 4
_MIN_COMPOSITE_SCORE = 50  # Minimum composite_score to qualify (0-100 scale)
_BUYSELL_LOOKBACK_DAYS = 3  # Calendar days; covers 2 trading days including weekends

# ISSUE #6 FIX: Define required signal fields for Phase 6 execution
_REQUIRED_SIGNAL_FIELDS = {
    "symbol": str,
    "composite_score": float,
    "entry_price": float,
    "close": float,
    "sma_50": float,
    "signal_strength": float,
}


def _validate_signal_completeness(candidates: list[dict], source: str) -> tuple[list[dict], int]:
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
        symbol = sig.get("symbol", "UNKNOWN")
        missing_fields = []
        for field_name, _field_type in _REQUIRED_SIGNAL_FIELDS.items():
            val = sig.get(field_name)
            if val is None:
                missing_fields.append(field_name)

        if missing_fields:
            incomplete_signals.append({"symbol": symbol, "missing": missing_fields})
            logger.warning(
                f"[PHASE 5] {symbol}: incomplete signal data (missing: {', '.join(missing_fields)}). Source={source}"
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

        log_phase_error(5, error)
        raise ValueError(
            f"[PHASE 5 DATA VALIDATION] Cannot proceed with incomplete signals. "
            f"Incomplete count: {len(incomplete_signals)}, Complete count: {len(complete_signals)}. "
            f"Required fields: {', '.join(_REQUIRED_SIGNAL_FIELDS.keys())}"
        )

    return complete_signals, len(incomplete_signals)


def _check_market_regime(run_date: _date) -> dict:
    """Return current market regime from market_exposure_daily.

    Uses shared read_market_regime() to ensure consistent JSON deserialization
    and error handling between Phase 3b and Phase 5.
    """
    from algo.risk import read_market_regime

    return read_market_regime(run_date)


def _detect_upstream_data_quality_drift(run_date: _date, signal_source: str) -> dict:
    """Detect upstream data quality issues by comparing expected vs. actual swing_trader_scores coverage.

    CRITICAL FIX #2: Now RAISES exception on DB error instead of silently returning empty dict.
    Silent degradation was hiding failures that cascade downstream.

    Returns dict with: {"swing_scores_missing": count_by_symbol, "has_drift": bool, "drift_symbols": list}
    Raises: RuntimeError if database query fails (cannot silently degrade)
    """
    from algo.orchestrator.phase_error_handling import ErrorCategory, PhaseError

    drift = {"swing_scores_missing": 0, "has_drift": False, "drift_symbols": []}

    try:
        with DatabaseContext("read") as cur:
            lookback_date = (
                run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS) if signal_source == "buysell_breakout" else None
            )

            if signal_source == "buysell_breakout":
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT bsd.symbol)
                    FROM (
                        SELECT DISTINCT ON (symbol) *
                        FROM buy_sell_daily
                        WHERE signal_type = 'BUY' AND date >= %s AND date <= %s
                        ORDER BY symbol, date DESC
                    ) bsd
                    LEFT JOIN swing_trader_scores sts ON sts.symbol = bsd.symbol
                        AND sts.date <= %s AND sts.score IS NOT NULL
                    WHERE sts.symbol IS NULL
                    """,
                    (lookback_date, run_date, run_date),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT ss.symbol)
                    FROM stock_scores ss
                    LEFT JOIN swing_trader_scores sts ON sts.symbol = ss.symbol
                        AND sts.date <= %s AND sts.score IS NOT NULL
                    WHERE sts.symbol IS NULL LIMIT 1
                    """,
                    (run_date,),
                )

            row = cur.fetchone()
            if row and row[0] and row[0] > 0:
                drift["swing_scores_missing"] = int(row[0])
                drift["has_drift"] = True
                logger.warning(
                    f"[PHASE 5] DATA QUALITY ALERT: {row[0]} symbols missing swing_trader_scores "
                    f"(source={signal_source}, date={run_date}). Check swing_trader_scores loader."
                )
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

        log_phase_error(5, error)
        raise RuntimeError(f"[PHASE 5] Cannot proceed without data quality verification: {e!s}") from e

    return drift


def _check_liquidity_parallel(candidate: dict, run_date: _date) -> tuple[dict, bool]:
    """Check liquidity for a single candidate. Returns (candidate, passed)."""
    try:
        liquidity = LiquidityChecks(config={})
        liq_ok, liq_reason = liquidity.run_all(candidate["symbol"], 0, run_date)
        if not liq_ok:
            logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity — {liq_reason}")
        return candidate, liq_ok
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.warning(f"[PHASE 5] {candidate['symbol']}: liquidity check error ({type(e).__name__}): {e!s}")
        return candidate, False


def _get_candidates_from_buysell(
    run_date: _date, min_score: float, limit: int = 100, min_close_quality: float = 0.3
) -> list[dict]:
    """Primary signal source: buy_sell_daily pivot-breakout BUY signals + stock_scores ranking + swing_trader_scores.

    Returns candidates that have BOTH a recent BUY signal (pivot breakout above swing high
    that was above SMA_50) AND a high composite_score. The breakout confirms the entry timing;
    composite_score ranks quality; swing_trader_scores provides multi-component validation.

    Lookback: last _BUYSELL_LOOKBACK_DAYS calendar days — covers the prior EOD pipeline's
    signals for morning/afternoon orchestrator runs, plus today's signals for the 5:30 PM run.

    ISSUE #3 FIX: All validation filters (swing_score, trend, close quality) moved to SQL WHERE clauses
    for efficiency and to detect upstream data quality drift immediately.
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
                        bsd.buylevel,
                        bsd.stoplevel,
                        bsd.strength AS signal_strength,
                        bsd.volume_surge_pct,
                        bsd.market_stage,
                        bsd.date AS signal_date,
                        sts.score AS swing_score,
                        sts.components AS swing_components
                    FROM (
                        SELECT DISTINCT ON (symbol) *
                        FROM buy_sell_daily
                        WHERE signal_type = 'BUY'
                          AND date >= %s
                          AND date <= %s
                        ORDER BY symbol, date DESC
                    ) bsd
                    JOIN stock_scores ss ON ss.symbol = bsd.symbol
                    INNER JOIN swing_trader_scores sts ON sts.symbol = bsd.symbol
                        AND sts.date <= %s AND sts.score IS NOT NULL
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
                    WHERE ss.composite_score >= %s
                      AND p.close > sma.avg_close
                      AND p.high > p.low
                      AND ((p.close - p.low) / (p.high - p.low)) > %s
                      AND bsd.strength IS NOT NULL
                )
                SELECT * FROM ranked
                ORDER BY swing_score DESC, composite_score DESC
                LIMIT %s
                """,
                (lookback_date, run_date, run_date, run_date, run_date, run_date, min_score, min_close_quality, limit),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            close = float(r[6]) if r[6] is not None else None
            composite = float(r[1]) if r[1] is not None else None
            raw_strength = float(r[15]) if r[15] is not None else None
            swing_score = float(r[19]) if r[19] is not None else 0.0
            swing_components = r[20] if r[20] is not None else None
            candidates.append(
                {
                    "symbol": r[0],
                    "composite_score": composite,
                    "quality_score": float(r[2]) if r[2] is not None else None,
                    "growth_score": float(r[3]) if r[3] is not None else None,
                    "momentum_score": float(r[4]) if r[4] is not None else None,
                    "rs_percentile": float(r[5]) if r[5] is not None else None,
                    "swing_score": swing_score,
                    "swing_components": swing_components,
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
                }
            )

        swing_score_positive = sum(1 for c in candidates if c["swing_score"] > 0)
        logger.info(
            f"[PHASE 5] {len(candidates)} candidates from buy_sell_daily + stock_scores + swing_trader_scores "
            f"(swing_scores: {swing_score_positive}, lookback: {lookback_date} to {run_date}, "
            f"SQL filters: trend & close_quality applied at query level)"
        )

        complete_candidates, incomplete_count = _validate_signal_completeness(candidates, "buy_sell_daily path")

        if incomplete_count > 0:
            logger.warning(
                f"[PHASE 5 DATA LOSS ALERT] {incomplete_count} incomplete signals FILTERED OUT from {len(candidates)} candidates. "
                f"Complete signals delivered to Phase 6: {len(complete_candidates)}. "
                f"Data loss: {incomplete_count / max(1, len(candidates)) * 100:.0f}% of input signals discarded."
            )

        return complete_candidates
    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(
            f"[PHASE 5] Failed to fetch buy_sell_daily candidates: {e}. "
            "Cannot proceed with signal generation without candidate data."
        ) from e


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: dict | None = None,
    check_halt_flag: Callable | None = None,
    phase1_degraded: bool = False,
    config=None,
) -> PhaseResult:

    if config is None:
        raise ValueError(
            "phase5_signal_generation.run() requires explicit config parameter (dependency injection). "
            "Get config at orchestrator level and pass it explicitly."
        )

    phase_start = time.time()
    logger.info("[PHASE 5] Starting signal generation")

    min_close_quality = ThresholdConfig.min_close_quality_pct() / 100.0
    min_composite_score = (
        config.get("phase5_min_composite_score", _MIN_COMPOSITE_SCORE) if config else _MIN_COMPOSITE_SCORE
    )

    # CRITICAL: Validate upstream dependencies before signal generation
    # These checks prevent cascading failures when upstream data is incomplete
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '10000ms'")

            # Validate stock_scores table exists and has data
            cur.execute("SELECT COUNT(*) FROM stock_scores")
            stock_scores_row = cur.fetchone()
            stock_scores_count = stock_scores_row[0] if stock_scores_row else 0
            if stock_scores_count == 0:
                msg = (
                    "[PHASE 5 CRITICAL] stock_scores table is empty. "
                    "Cannot generate signals without stock quality rankings. "
                    "Verify stock_scores loader completed successfully. "
                    "Check data_loader_status for stock_scores and related loaders."
                )
                logger.critical(msg)
                log_phase_result_fn(5, "signal_generation", "halt", msg)
                return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

            # Validate market_exposure_daily has fresh data with valid exposure_pct
            cur.execute(
                """
                SELECT COUNT(*), COUNT(CASE WHEN exposure_pct IS NOT NULL THEN 1 END)
                FROM market_exposure_daily
                WHERE date = %s
                """,
                (run_date,),
            )
            exposure_row = cur.fetchone()
            exposure_count = exposure_row[0] if exposure_row else 0
            exposure_valid = exposure_row[1] if exposure_row and len(exposure_row) > 1 else 0

            if exposure_count == 0:
                msg = (
                    f"[PHASE 5 CRITICAL] market_exposure_daily has no data for {run_date}. "
                    "Cannot determine market regime for position sizing. "
                    "Check that market exposure pipeline completed."
                )
                logger.critical(msg)
                log_phase_result_fn(5, "signal_generation", "halt", msg)
                return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

            if exposure_valid == 0:
                msg = (
                    f"[PHASE 5 CRITICAL] market_exposure_daily for {run_date} has NULL exposure_pct. "
                    "Cannot size positions without valid market exposure data. "
                    "Check exposure computation pipeline."
                )
                logger.critical(msg)
                log_phase_result_fn(5, "signal_generation", "halt", msg)
                return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 5 CRITICAL] Could not validate upstream dependencies: {e}"
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(5, "signal_generation", "halt", msg)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

    # Halt flag check before generating signals
    if check_halt_flag and check_halt_flag():
        logger.critical(
            "[PHASE 5] Halt flag set by Phase 1 — data quality degradation detected. Halting signal generation."
        )
        log_phase_result_fn(5, "signal_generation", "halt", "Halt flag set: data quality degradation")
        return PhaseResult(
            5,
            "signal_generation",
            "halted",
            {"qualified_trades": []},
            True,
            "Halt flag set: data quality degradation detected",
        )

    # Market regime gate
    regime = _check_market_regime(run_date)
    logger.info(
        f"[PHASE 5] Market regime: {regime['regime']} "
        f"exposure={regime['exposure_pct']:.0f}% "
        f"entry_allowed={regime['is_entry_allowed']}"
    )
    if not regime["is_entry_allowed"]:
        reasons = "; ".join(regime["halt_reasons"]) if regime["halt_reasons"] else "no halt reasons logged"
        logger.warning(f"[PHASE 5] Entries halted by market regime: {reasons}")
        log_phase_result_fn(5, "signal_generation", "halt", f"Market regime halted entries: {reasons[:100]}")
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, reasons[:100])

    # ISSUE #7 FIX: Exposure policy gate — fail-closed if constraints not provided
    if exposure_constraints is None:
        msg = (
            "[PHASE 5 CRITICAL] Exposure constraints not provided by Phase 3b. "
            "Cannot proceed with signal generation without knowing market exposure limits. "
            "Check that Phase 3b (Exposure Policy) completed successfully."
        )
        logger.critical(msg)
        log_phase_result_fn(5, "signal_generation", "halt", msg)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

    if exposure_constraints and exposure_constraints.get("halt_new_entries"):
        reason = exposure_constraints.get("halt_reason", "Exposure policy halted new entries")
        logger.warning(f"[PHASE 5] {reason}")
        log_phase_result_fn(5, "signal_generation", "halt", reason)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, reason)

    # Primary: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.
    # buy_sell_daily is REQUIRED (loaded by EOD pipeline at 4:05 PM ET before orchestrator runs).
    # Fail explicitly if unavailable — don't silently degrade to stock_scores.
    try:
        raw_candidates = _get_candidates_from_buysell(
            run_date, min_composite_score, min_close_quality=min_close_quality
        )
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
        log_phase_error(5, error, log_phase_result_fn)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, error.message)
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
        log_phase_error(5, error, log_phase_result_fn)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, error.message)

    if not raw_candidates:
        msg = (
            f"[PHASE 5 CRITICAL] No buy_sell_daily BUY signals found within last {_BUYSELL_LOOKBACK_DAYS} "
            "calendar days. Phase 5 requires buy_sell_daily breakout signals as primary gate. "
            "Check that EOD pipeline (4:05 PM ET) has completed and buy_sell_daily loader ran successfully."
        )
        logger.critical(msg)
        log_phase_result_fn(5, "signal_generation", "halt", msg)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

    signal_source = "buysell_breakout"

    if not raw_candidates:
        msg = f"No candidates (source={signal_source}) for {run_date} with composite_score >= {min_composite_score}"
        logger.warning(f"[PHASE 5] {msg}")
        log_phase_result_fn(5, "signal_generation", "halt", msg)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

    # ISSUE #3 FIX: All trend and close quality validation now happens at SQL level in _get_candidates_from_buysell().
    # Candidates here are already filtered for: close > sma_50, close_position > min_close_quality, swing_score IS NOT NULL.
    # This eliminates wasted I/O and ensures silent data quality drift is detected immediately.
    quality_filtered = raw_candidates

    # Check for upstream data quality issues (e.g., swing_trader_scores not populated)
    upstream_drift = _detect_upstream_data_quality_drift(run_date, signal_source)
    if upstream_drift.get("has_drift"):
        logger.warning(
            f"[PHASE 5] Upstream data quality drift detected: {upstream_drift['swing_scores_missing']} symbols "
            f"missing swing_trader_scores. This may suppress valid candidates."
        )

    # Sort by composite_score descending
    quality_filtered.sort(key=lambda s: s.get("composite_score", 0), reverse=True)

    # Liquidity checks on top candidates — parallelized
    liq_passed = []
    liq_checked = 0
    to_check = quality_filtered[:_LIQUIDITY_CHECK_LIMIT]

    if to_check:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {executor.submit(_check_liquidity_parallel, cand, run_date): cand for cand in to_check}
            for future in as_completed(futures):
                liq_checked += 1
                candidate, passed = future.result()
                if passed:
                    liq_passed.append(candidate)

    logger.info(
        f"[PHASE 5] Liquidity check: {liq_checked} checked, {len(liq_passed)} passed. "
        f"{len(quality_filtered) - liq_checked} unchecked candidates dropped."
    )

    # Final ranking by composite_score
    liq_passed.sort(key=lambda s: s.get("composite_score", 0), reverse=True)

    logger.info(f"[PHASE 5] Top 10 qualified signals (source={signal_source}):")
    for i, sig in enumerate(liq_passed[:10]):

        def _fmt(v, spec=":.1f"):
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
        5,
        "signal_generation",
        "success",
        f"{len(liq_passed)} signals qualified from {len(raw_candidates)} candidates",
    )

    return PhaseResult(
        5,
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

#!/usr/bin/env python3
"""PHASE 7: SIGNAL GENERATION & RANKING - Find best trading candidates.

Primary responsibility: Generate buy signals from technical setup and rank by quality.

Primary signal source: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.

HALT FLAG PROPAGATION (AUDIT ISSUE #7):
When halt flag is set (from Phase 2 circuit breaker or data freshness gate):
- Phase 7 returns empty qualified_trades list
- Phase 8 gracefully handles this (no entries to execute)
- Halt status logged but not fatal to orchestration
Prevents unguarded entries even when circuit breaker is active.

ANOMALY DETECTION: buy_sell_daily signal count is monitored. If the most recent trading
day has unexpectedly ZERO signals (historical median ~400-800), Phase 7 halts with
clear error about upstream data quality issues (likely technical_data_daily failure).

GUARD RAILS (AUDIT ISSUE #8 FIX):
1. Critical dependency check BEFORE signal generation:
   - stock_scores must have data (prevents universe limitation issues)
   - market_exposure_daily must have valid exposure_pct (exposure policy enforcement)
   - buy_sell_daily must have BUY signals within lookback window (no stale signals)
2. Any missing dependency -> immediate halt with clear error message
3. Anomaly detection: If recent buy_sell_daily counts drop to 0, halt (upstream loader failure)
4. Prevents silent degradation where empty signals show on dashboard
5. Signal quality validation: All signals must have composite_score from stock_scores ranking

Pipeline:
1. Check all critical dependencies (fail-fast if any missing)
2. Anomaly detection: verify buy_sell_daily signal count is not suspiciously low
3. Check halt flag (data freshness gate)
4. Check market regime: halt if entries not allowed per market_exposure_daily
5. Fetch candidates (primary): buy_sell_daily BUY signals INNER JOIN to stock_scores
   (composite ranking required - no fallback to computed scores). Only signals with
   stock_scores coverage + data_completeness >= 70 are eligible.
6. Filter: close > sma_50 (uptrend confirmation)
7. Filter: composite_score >= min threshold (30)
8. Close quality gate: skip weak closes (bottom of day's range = distribution)
9. Liquidity checks on top LIQUIDITY_CHECK_LIMIT candidates (ranked by composite_score
   descending - see note below)
10. Return composite_score-ranked candidates to Phase 8 (Phase 8 re-sorts the same field for
    its own concentration-limited capital allocation - one consistent ranking end-to-end)

CRITICAL: buy_sell_daily is required for robust signal generation. The EOD pipeline
(4:05 PM ET) must complete and populate buy_sell_daily (which depends on technical_data_daily).
If buy_sell_daily unexpectedly has zero signals, Phase 7 halts (fail-closed) to surface
upstream data quality issues rather than silently degrading.

UNIVERSE LIMITATION (Session 247, Session 365+):
Only ~4,700 of ~10,600 trading symbols (NASDAQ, NYSE, AMEX) have sufficient metric coverage
for stock_scores ranking. This means Phase 7 can ONLY generate signals for this subset.
Why? stock_scores requires INNER JOIN on:
- quality_metrics (ROE, margins, ratios)
- growth_metrics (revenue/EPS growth)
- value_metrics (P/E, P/B, etc.)
- positioning_metrics (insider, institutional ownership)
- stability_metrics (beta, volatility)

Symbols without ANY of these metrics are silently excluded from signal generation.
Impact: 55% of tradable universe never receives signals, even if buy_sell_daily has
qualifying technical setup. To expand coverage: improve metric loaders (SEC parsing,
yfinance reliability). For now, signals constrained to well-covered tiers.

Why no fallback to computed scores? Using COALESCE(composite_score, strength*50) would:
- Create silent data quality degradation (when stock_scores missing for a symbol)
- Hide universe gap issues (which symbols lack score coverage)
- Allow low-quality signals when metrics are incomplete
- Violate fail-fast principle (explicit data_unavailable required)

INSTEAD: INNER JOIN requires stock_scores coverage. Signals are only generated for
symbols with full quality/growth/value/positioning/stability metrics available.

Ranking: composite_score descending (RESTORED 2026-08-27, real-money-readiness review).
History: this was composite_score-ranked originally; Session 377 switched the sort key to
signal_quality_score (SQS - RSI/MACD/Minervini/Weinstein-based) on the hypothesis that
technical quality predicts 1-5 day price action better than composite_score's fundamental
pillars, targeting a 33%->50%+ win-rate improvement. That hypothesis was empirically tested
against real live buy_sell_daily signals on 2026-08-26 and found to be false: SQS showed
~zero-to-negative correlation with forward returns (non-monotonic quintiles, top quintile
WORST in the 10-day cut) and live BUY signals averaged negative forward returns while SPY
was flat-to-up (see signal_quality_score_pooled_check_no_predictive_power_found_20260825 /
algo/research/signal_quality_score_validation.py). Compounding this, run_backtest.py's
touted 1.42 Sharpe ranked candidates the same SQS-first way, so it was never independent
confirmation the ranking worked - it shared the same untested assumption live trading did.
Switched back to composite_score 2026-08-27: composite_score's pillars (quality/growth/
value/positioning/risk/momentum - "stability" renamed to "risk" 2026-08-26, migration 1235)
each carry their own multi-year Fama-MacBeth validation, unlike SQS's hand-set
COMPONENT_MAXES which have never been shown to predict returns. signal_quality_score is
still computed and still gates entries via Phase 8's separate min_signal_quality_score
floor (an independent quality bar, not a ranking mechanism) - only the SORT KEY changed.

NOTE for anyone re-testing this later: run_backtest.py intentionally still ranks by
signal_quality_score, NOT composite_score - see that module's docstring. This is not an
oversight; stock_scores (and therefore composite_score) has no historical date dimension
(a symbol's composite_score there is always TODAY's snapshot), so using it to rank a
backtest's historical BUY signals would be look-ahead-biased. A point-in-time
stock_scores_history table exists (migration 1221) but only has snapshots from 2026-08-24
onward - too shallow to backtest composite_score-ranking validly yet. Once it accumulates
enough history, run_backtest.py should be updated to join stock_scores_history by
(symbol, score_date) and rank by composite_score there, to actually validate this live
change rather than assume it.

Signal source: buy_sell_daily + stock_scores INNER JOIN (EXPLICIT - no degradation mode).
"""

import logging
import math
import time
from collections.abc import Callable
from datetime import date as _date
from datetime import timedelta
from typing import Any

import psycopg2

from algo.orchestrator.config_validator import get_config_float, validate_phase_config
from algo.orchestrator.phase7_candidate_builder import _build_candidates_from_rows, _persist_signal_quality_scores
from algo.orchestrator.phase7_run_steps import (
    _apply_post_fetch_quality_filters,
    _check_exposure_constraints_gate,
    _check_halt_flag_gate,
    _check_market_regime_gate,
    _compute_signal_quality_scores_for_run,
    _fetch_and_handle_candidates,
    _filter_inactive_symbols,
    _finalize_ranking_and_log,
    _run_liquidity_checks,
)
from algo.orchestrator.phase_data_contract import ExposureConstraints, validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.orchestrator.validation_thresholds import BUY_SELL_DAILY_ANOMALY_THRESHOLD
from algo.risk import LiquidityChecks
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

_BUYSELL_LOOKBACK_DAYS = 1  # Use TODAY's signals + yesterday's if today unavailable (EOD pipeline runs 4:05 PM)


def _calculate_dynamic_anomaly_threshold() -> int:
    """Calculate signal anomaly threshold from historical 30-day median.

    Adapts to universe size: if your universe is smaller, median is lower,
    threshold scales accordingly. Prevents false positives from hardcoded constants.

    Returns: threshold = median_30d / 3 (catches signals dropped to 33% of normal)
    """
    try:
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            # Query signal counts for last 30 trading days (only BUY signals per Phase 7 design)
            cur.execute("""
                WITH recent_signals AS (
                    SELECT date, COUNT(*) as signal_count
                    FROM buy_sell_daily
                    WHERE signal_type = 'BUY'
                    AND date >= CURRENT_DATE - INTERVAL '45 days'  -- 45 calendar days to cover 30 trading days
                    GROUP BY date
                    ORDER BY date DESC
                    LIMIT 30
                )
                SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signal_count) as median_signals
                FROM recent_signals
                WHERE signal_count > 0
            """)

            result = cur.fetchone()
            if result and result[0] is not None:
                median_signals = float(result[0])
                # UPDATE 2026-08-19: floor lowered from 100 - the 45-day lookback window still
                # mixes stale pre-fix days (re-fire-inflated, see bc0047231) with correct
                # post-fix days (~80-250/day), so median_30d stays elevated during the
                # transition and a 100 floor would keep tripping on legitimate quiet days once
                # it clears. See BUY_SELL_DAILY_ANOMALY_THRESHOLD in validation_thresholds.py.
                threshold = max(40, int(median_signals / 3))  # At least 40, catch drops to 1/3 of median
                logger.info(
                    f"[PHASE 7] Dynamic anomaly threshold: {threshold} (median_30d={median_signals:.0f}/3). "
                    f"Will halt if signals drop below {threshold} on any day."
                )
                return threshold
            else:
                logger.warning(
                    f"[PHASE 7] Could not calculate dynamic threshold (insufficient historical data). "
                    f"Using fallback: {BUY_SELL_DAILY_ANOMALY_THRESHOLD}"
                )
                return BUY_SELL_DAILY_ANOMALY_THRESHOLD
    except Exception as e:
        logger.warning(
            f"[PHASE 7] Error calculating dynamic anomaly threshold: {e}. "
            f"Using fallback: {BUY_SELL_DAILY_ANOMALY_THRESHOLD}"
        )
        return BUY_SELL_DAILY_ANOMALY_THRESHOLD


def _buysell_lookback_start_date(run_date: _date) -> _date:
    """Earliest date to include when querying buy_sell_daily BUY signals.

    Trading-day-aware equivalent of "yesterday": the most recent trading day
    strictly before run_date. A flat `run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS)`
    calendar subtraction misses the prior trading day's signals whenever run_date
    follows a weekend or holiday - e.g. a Monday's -1 day lands on Sunday, excluding
    Friday's real EOD-generated BUY signals entirely. Confirmed live 2026-07-27: a
    Monday morning dry run found 0 candidates via the calendar-day window despite 301
    real BUY signals sitting in buy_sell_daily for the prior trading day (2026-07-24),
    all outside the [Sunday, Monday] range the old calculation produced.
    """
    from algo.infrastructure import MarketCalendar

    prev_trading_day = MarketCalendar.get_previous_trading_day(run_date - timedelta(days=1))
    return prev_trading_day or run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS)


def _compute_risk_score(atr_14: float | None, close: float | None) -> float:
    """Risk score (0-100, 100 = very low risk) based on ATR volatility relative to price.

    CRITICAL: Fails fast if ATR or close unavailable (never silent 50.0 default).
    Risk scoring is fundamental to position sizing - using neutral defaults when data
    is missing violates fail-fast principle. Either data exists or scoring halts.

    AUDIT FIX (Session 276): Added explicit volatility gate - rejects stocks with
    ATR > 18% of close (extreme volatility). Prevents under-capitalized positions
    in highly volatile stocks. Prior: formula would produce risk_score=0 but still
    allow entry. Now: explicitly halts with clear error message.
    """
    if atr_14 is None:
        raise ValueError(
            "ATR(14) data unavailable for risk scoring. Cannot proceed with signal generation. "
            "Check that technical indicators loader completed successfully."
        )
    if close is None or close <= 0:
        raise ValueError(
            f"Close price invalid or unavailable ({close!r}) for risk scoring. Cannot proceed with signal generation."
        )
    # BUG FOUND 2026-08-10 (via fuzzing with pathological inputs): a NaN atr_14 or close
    # silently produced risk_score=100.0 - the BEST possible score, not a neutral or failed
    # one - because `max(0.0, min(100.0, 100.0 - (nan * 5)))` washes NaN out via Python's
    # min()/max() short-circuit comparison behavior (`nan < 100.0` is False, so min() keeps
    # 100.0). This directly violates this function's own stated contract two lines above
    # ("never silent 50.0 default... Either data exists or scoring halts") - silently
    # returning the MOST FAVORABLE score for corrupted volatility data is worse than the
    # neutral-default failure mode the docstring explicitly warns against, since it actively
    # misrepresents an unknown-risk stock as the lowest-risk one available, directly
    # feeding Phase 7's signal ranking. Same bug class already found and fixed this session
    # in position_sizer.py, financial.py, phase8_entry_execution.py, exit_engine.py, and
    # order_manager.py. Also reject negative ATR here (physically invalid - technical
    # indicators must never be negative) rather than silently scoring it as excellent too.
    if math.isnan(atr_14) or math.isinf(atr_14) or atr_14 < 0:
        raise ValueError(f"ATR(14)={atr_14!r} is invalid (must be a finite number >= 0) for risk scoring.")
    if math.isnan(close) or math.isinf(close):
        raise ValueError(f"Close price {close!r} is invalid (must be a finite number) for risk scoring.")
    atr_pct = (atr_14 / close) * 100

    # AUDIT FIX: Explicit extreme volatility gate (reject if ATR > 18% of close)
    # This proactively filters high-volatility stocks that create position sizing challenges
    if atr_pct > 18.0:
        raise ValueError(
            f"ATR={atr_pct:.1f}% exceeds maximum volatility gate (18% of close). "
            f"Stock is too volatile for reliable position sizing. "
            f"Minimum stop loss would exceed acceptable risk parameters."
        )

    return max(0.0, min(100.0, 100.0 - (atr_pct * 5)))


def _fetch_institutional_ownership_for_scoring(symbol: str) -> float | None:
    """Fetch institutional_ownership_pct for live signal quality scoring.

    Isolated in its own DatabaseContext (own connection/transaction) rather than
    reusing the candidate loop's shared cursor, so any failure here can never abort
    that shared transaction for the remaining candidates in the loop (see
    connection_pool_transaction_abort_cascade in project memory). Mirrors
    loaders/load_signal_quality_scores.py::_fetch_positioning_data's same
    treat-as-optional-enrichment approach. Returns None on any failure - missing
    institutional ownership data is common (OTC, preferred, warrant securities) and
    must degrade the composite score gracefully, not block signal generation.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT institutional_ownership_pct FROM positioning_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except Exception as e:
        logger.debug(f"[PHASE 7] {symbol}: institutional_ownership unavailable for scoring: {e}")
    return None


def _fetch_vcp_strength_for_scoring(symbol: str, signal_date: str) -> float | None:
    """Fetch vcp_strength for live signal quality scoring.

    Same isolation rationale as _fetch_institutional_ownership_for_scoring above.
    Returns None on any failure, including a missing vcp_patterns table/row - VCP
    pattern data is an optional enrichment component, not a required one.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT vcp_strength FROM vcp_patterns WHERE symbol = %s AND date = %s",
                (symbol, signal_date),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
    except Exception as e:
        logger.debug(f"[PHASE 7] {symbol}: vcp_strength unavailable for scoring: {e}")
    return None


# ISSUE #6 FIX: Define required signal fields for Phase 7 execution
# Note: market_stage is optional (used only for logging, defaults to "unknown" if missing).
# All other fields are critical for signal validation and execution.
_REQUIRED_SIGNAL_FIELDS = {
    "symbol": str,
    "composite_score": float,
    "entry_price": float,
    "close": float,
    "sma_50": float,
    "signal_strength": float,
    "signal_quality_score": float,
    "signal_date": str,
    "trend_template_score": float,
    "base_quality": str,
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
            lookback_date = _buysell_lookback_start_date(run_date) if signal_source == "buysell_breakout" else None

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
            root_cause=f"Database query failed: {str(e)[:500]}",
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
            logger.debug(f"[PHASE 7] {candidate['symbol']}: liquidity - {liq_reason}")
        return candidate, liq_ok
    except (ValueError, ZeroDivisionError, TypeError) as e:
        # FAIL-FAST: Exceptions during liquidity checks indicate real errors, not just failed thresholds
        # Silently returning False masks configuration errors, missing data, or calculation bugs
        error_msg = (
            f"[PHASE 7 FAIL-FAST] Liquidity check error for {candidate['symbol']}: {type(e).__name__}: {e}. "
            f"Cannot proceed with signal evaluation when liquidity validation fails. "
            f"Check: (1) LiquidityChecks configuration, (2) price/volume data availability, (3) calculation logic."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e


def _score_candidates_inline(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute signal quality scores (composite_sqs & trend_template_score) for candidates.

    ARCHITECTURE FIX (Session 376): Batch loader fails for live signals. Compute inline instead.

    Kept in this module (not moved to algo/orchestrator/phase7_candidate_builder.py alongside
    the other _get_candidates_from_buysell helpers) because it calls
    compute_signal_quality_components() - tests/unit/test_signal_quality_score_single_source_of_truth_20260820.py
    inspects phase7_signal_generation.py's own module source and requires >= 2 occurrences of
    that call (this function is one; the orphaned-signal backfill scorer in
    _backfill_orphaned_signal_scores() below is the other).

    Mutates each candidate dict in place (sets signal_quality_score/trend_template_score/
    base_quality) and returns the (possibly filtered) candidates list - candidates whose score
    could not be computed are dropped here, matching the original inline behavior.
    """
    from loaders.signal_quality_scorer import compute_signal_quality_components

    with DatabaseContext("read") as cur_sqs:
        for candidate in candidates:
            symbol = candidate["symbol"]
            try:
                # Fetch technical data for this signal (CRITICAL FIX: use correct table for each metric)
                # RSI, MACD are in technical_data_daily; minervini, weinstein are in trend_template_data
                # CRITICAL FIX (Session 384): Use candidate's signal_date, not run_date. Morning runs happen
                # before EOD pipeline completes, so today's technical data doesn't exist yet. Signal came from
                # yesterday, so query technical data from yesterday's date.
                signal_date = candidate.get("signal_date")
                if not signal_date:
                    # FAIL-FAST: signal_date is required to look up technical data
                    # A signal without a date is a data quality issue - we don't know which day
                    # to look up indicators from. This indicates buy_sell_daily has a NULL date,
                    # which violates data integrity.
                    raise ValueError(
                        f"[PHASE 7 CRITICAL] {symbol}: signal_date missing or None. "
                        f"Cannot determine which date's technical data to use for quality scoring. "
                        f"This indicates buy_sell_daily has a NULL date field (data integrity issue). "
                        f"Fail-fast: check buy_sell_daily loader and ensure all signals have valid dates."
                    )
                cur_sqs.execute(
                    """
                    WITH price_window AS (
                        SELECT date, close,
                               MAX(high) OVER (
                                   ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                               ) AS high_52w
                        FROM price_daily
                        WHERE symbol = %s AND date <= %s
                    )
                    SELECT
                        t.rsi, t.macd, t.macd_signal,
                        COALESCE(tr1.minervini_trend_score, tr2.minervini_trend_score) as minervini,
                        COALESCE(tr1.weinstein_stage, tr2.weinstein_stage) as weinstein,
                        CASE WHEN pw.high_52w > 0
                             THEN (pw.close - pw.high_52w) / pw.high_52w * 100
                             ELSE NULL END AS percent_from_52w_high
                    FROM technical_data_daily t
                    LEFT JOIN trend_template_data tr1 ON tr1.symbol = t.symbol AND tr1.date = t.date
                    LEFT JOIN trend_template_data tr2 ON tr2.symbol = t.symbol AND tr2.date = t.date - INTERVAL '1 day'
                    LEFT JOIN price_window pw ON pw.date = t.date
                    WHERE t.symbol = %s AND t.date = %s
                    """,
                    (symbol, signal_date, symbol, signal_date),
                )
                tech_row = cur_sqs.fetchone()

                if not tech_row:
                    # FAIL-FAST: Technical data for signal_date is required for quality scoring
                    # If a signal exists for signal_date but technical_data_daily is missing,
                    # this indicates a loader order issue (signals generated before technical data loaded)
                    # or a data gap. Either way, we cannot reliably score the signal.
                    raise ValueError(
                        f"[PHASE 7 CRITICAL] {symbol}: No technical data found for signal_date {signal_date}. "
                        f"Cannot compute signal quality score without RSI, MACD, and trend template data. "
                        f"This indicates: (1) technical_data_daily loader incomplete for {signal_date}, "
                        f"(2) loader order issue (signals generated before technical data), or "
                        f"(3) signal date out of sync with technical data. "
                        f"Check: (1) technical_data_daily loader status for {signal_date}, "
                        f"(2) signal_date field in buy_sell_daily for {symbol}, "
                        f"(3) Phase 7 run timing vs technical loader completion."
                    )

                rsi, macd, macd_signal, minervini, weinstein, pct_from_52w_high = tech_row

                # CRITICAL FIX: psycopg2 returns numeric columns as Decimal type
                # Convert to float BEFORE passing to scorer (scorer uses pd.isna and float comparisons)
                # Decimal + float operations or Decimal subtraction can fail
                rsi = float(rsi) if rsi is not None else None
                macd = float(macd) if macd is not None else None
                macd_signal = float(macd_signal) if macd_signal is not None else None
                minervini = float(minervini) if minervini is not None else None
                weinstein = int(weinstein) if weinstein is not None else None
                pct_from_52w_high = float(pct_from_52w_high) if pct_from_52w_high is not None else None

                # CRITICAL FIX: Check for missing trend_template_data after fallback attempt
                # Queries today's trend_template_data first; if missing, falls back to yesterday's via COALESCE
                # If BOTH today and yesterday are missing, signal quality scores degrade (lose 15-25 points)
                # Allow degraded signals to pass through - halt only if BOTH sources missing is too strict
                # Morning runs often have same-day signals before trend data loads (EOD pipeline runs 4:05 PM)
                if minervini is None or weinstein is None:
                    logger.warning(
                        f"[PHASE 7] {symbol}: Degraded trend template data for {signal_date}. "
                        f"Minervini={minervini}, Weinstein={weinstein}. "
                        f"Using fallback data or missing entirely. Signal quality scores reduced (lose 15-25 points). "
                        f"Allowing signal to pass with quality degradation. Check trend_template_data loader schedule."
                    )
                    # Set sensible defaults to allow signal to pass with quality degradation
                    minervini = minervini or 2.0  # Conservative estimate
                    weinstein = weinstein or 1  # Conservative estimate

                # Compute scores via the single shared formula (loaders/signal_quality_scorer.py::
                # compute_signal_quality_components) - the SAME function the batch/EOD loader
                # (loaders/load_signal_quality_scores.py) uses. Previously this inline path summed
                # only 3 of the 7 designed components (base+volume+trend, raw sum clamped at 100)
                # while its own comment falsely claimed "same as batch loader" - the batch loader's
                # tested, weighted-sum-over-available-maxes formula never actually reached
                # buy_sell_daily.signal_quality_score/Phase 8's entry gate because this inline write
                # ran first and unconditionally. Fixed 2026-08-20: both paths now call the same
                # function, so the score that gates real trade entries can't silently diverge from
                # the documented/tested weighting again.
                institutional_ownership = _fetch_institutional_ownership_for_scoring(symbol)
                vcp_strength = _fetch_vcp_strength_for_scoring(symbol, signal_date)

                scores = compute_signal_quality_components(
                    signal_type="BUY",
                    rsi=rsi,
                    macd=macd,
                    macd_signal=macd_signal,
                    minervini_score=minervini,
                    weinstein_stage=weinstein,
                    percent_from_52w_high=pct_from_52w_high,
                    institutional_ownership=institutional_ownership,
                    vcp_strength=vcp_strength,
                )
                base_score = scores["base_quality_score"]
                trend_score = scores["trend_template_score"]
                composite_sqs = scores["composite_sqs"]

                candidate["signal_quality_score"] = composite_sqs
                candidate["trend_template_score"] = trend_score

                # CRITICAL FIX: Compute base_quality classification from base_score
                # base_quality is a string classification (strong/moderate/weak) that categorizes
                # signal quality for dashboard/reporting. Previously always NULL.
                if base_score >= 60:
                    candidate["base_quality"] = "strong"
                elif base_score >= 35:
                    candidate["base_quality"] = "moderate"
                else:
                    candidate["base_quality"] = "weak"

                logger.debug(
                    f"[PHASE 7 SCORING] {symbol}: "
                    f"sqs={composite_sqs} trend={trend_score} base_quality={candidate['base_quality']} "
                    f"data_completeness={scores['data_completeness']} "
                    f"base_type={candidate.get('base_type')}"
                )

            except Exception as score_e:
                # CRITICAL: Log full exception details so operators know what went wrong
                logger.warning(
                    f"[PHASE 7] {symbol}: Failed to compute signal quality score (skipping this candidate). "
                    f"Signal date: {signal_date}. "
                    f"Error: {type(score_e).__name__}: {score_e}"
                )
                # CRITICAL FIX: Set score to None instead of halting entire phase
                # One symbol's calculation error should not block signal generation for all other symbols
                candidate["signal_quality_score"] = None
                candidate["trend_template_score"] = None
                candidate["base_quality"] = None

        missing_scores = sum(1 for c in candidates if c.get("signal_quality_score") is None)
        if missing_scores > 0:
            missing_symbols = [c.get("symbol") for c in candidates if c.get("signal_quality_score") is None]
            logger.info(
                f"[PHASE 7] {missing_scores}/{len(candidates)} candidates missing signal quality scores "
                f"(insufficient technical data). Symbols: {missing_symbols[:10]}. Filtering out..."
            )
            # CRITICAL FIX (Session 391): REJECT candidates with None signal_quality_score IMMEDIATELY
            # (not later in Phase 8 quality gate as previous comment claimed).
            # Candidates without scores should never reach downstream phases where they cause confusing
            # "signal has None quality_score" errors. Filter them out right here.
            candidates = [c for c in candidates if c.get("signal_quality_score") is not None]
            if not candidates:
                msg = (
                    "[PHASE 7 CRITICAL] All buy_sell_daily candidates filtered out due to missing signal_quality_score. "
                    "This indicates: (1) Score computation failed in Phase 7 scorer initialization, "
                    "(2) All signal_quality_scores in buy_sell_daily are unexpectedly NULL, or "
                    "(3) Signal source has no records. Check: (1) signal quality scorer logs, "
                    "(2) buy_sell_daily scoring status, (3) upstream loader completion."
                )
                logger.critical(msg)
                raise RuntimeError(msg)
            logger.info(f"[PHASE 7] After filtering: {len(candidates)} candidates remain")

    return candidates


def _get_candidates_from_buysell(
    run_date: _date, min_score: float, limit: int = 100, min_close_quality: float = 0.3
) -> list[dict[str, Any]]:
    """Primary signal source: buy_sell_daily pivot-breakout BUY signals + stock_scores (composite) ranking.

    Returns candidates that have BOTH a recent BUY signal (pivot breakout above swing high
    that was above SMA_50) AND a high composite_score. The breakout confirms the entry timing;
    composite_score ranks quality.

    Lookback: the prior trading day (weekend/holiday-aware) - covers the prior EOD pipeline's
    signals for morning/afternoon orchestrator runs, plus today's signals for the 5:30 PM run.

    SWING SCORE MIGRATION: Removed swing_trader_scores LEFT JOIN (was fetched but never used).
    All signal ranking now uses composite_score only.

    FIX: Use configured min_completeness_score threshold instead of hardcoded 70 (Session 2026-08-02).
    Hardcoded threshold was blocking signals for 65%+ of universe when config specified 35.
    """
    from algo.infrastructure.config import AlgoConfig

    config_obj = AlgoConfig()
    min_completeness_threshold = config_obj.get("min_completeness_score", default=70)

    lookback_date = _buysell_lookback_start_date(run_date)
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
                        bsd.base_type
                    FROM (
                        SELECT DISTINCT ON (symbol) *
                        FROM buy_sell_daily
                        WHERE signal = 'BUY'
                          AND date >= %s
                          AND date <= %s
                        ORDER BY symbol, date DESC
                    ) bsd
                    INNER JOIN stock_scores ss ON ss.symbol = bsd.symbol AND ss.composite_score IS NOT NULL
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
                    LEFT JOIN company_profile cp ON cp.symbol = bsd.symbol
                    WHERE ss.composite_score >= %s
                      AND ss.data_completeness >= %s
                      AND (ss.data_unavailable = false OR ss.data_unavailable IS NULL)
                      AND p.close > sma.avg_close
                      AND p.high > p.low
                      AND ((p.close - p.low) / (p.high - p.low)) > %s
                      AND bsd.strength IS NOT NULL
                      AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
                      AND bsd.symbol NOT IN (SELECT symbol FROM algo_positions WHERE status = 'open')
                )
                -- BUG FOUND 2026-09-01 (/goal session, fringe-case sweep): ordering by
                -- composite_score alone with no tiebreaker means the exact set of symbols
                -- selected at the LIMIT boundary is non-deterministic across otherwise-
                -- identical runs whenever two candidates tie (composite_score is a rounded
                -- percentile-derived value across a universe of thousands - ties at the
                -- margin are plausible, not a corner case). rs_percentile (already selected
                -- above) is a real secondary ranking signal, not an arbitrary tiebreaker -
                -- among equally-scored candidates, prefer the one with stronger relative
                -- strength. NULLS LAST since a NULL rs_percentile candidate gets filtered
                -- out downstream anyway (see the Python-side skip further down this
                -- function) and must not rank ahead of a real candidate on a tie. `symbol
                -- ASC` as a final tiebreaker guarantees total determinism even if
                -- rs_percentile also ties.
                SELECT * FROM ranked
                ORDER BY composite_score DESC, rs_percentile DESC NULLS LAST, symbol ASC
                LIMIT %s
                """,
                (
                    lookback_date,
                    run_date,
                    run_date,
                    run_date,
                    run_date,
                    min_score,
                    min_completeness_threshold,
                    min_close_quality,
                    limit,
                ),
            )
            rows = cur.fetchall()

        candidates = _build_candidates_from_rows(rows)

        logger.info(
            f"[PHASE 7] {len(candidates)} candidates from buy_sell_daily + stock_scores "
            f"(lookback: {lookback_date} to {run_date}, "
            f"SQL filters: trend & close_quality applied at query level)"
        )

        if candidates:
            candidates = _score_candidates_inline(candidates)
            _persist_signal_quality_scores(candidates)

        complete_candidates, _ = _validate_signal_completeness(candidates, "buy_sell_daily path")
        return complete_candidates
    except (ValueError, ZeroDivisionError, TypeError) as e:
        raise RuntimeError(
            f"[PHASE 7] Failed to fetch buy_sell_daily candidates: {e}. "
            "Cannot proceed with signal generation without candidate data."
        ) from e


def _check_per_day_signal_counts(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> tuple[bool, str | None]:
    """ISSUE #7 FIX: Validate signal counts for EACH trading day individually.

    Prevents accepting degraded data where one day has insufficient signals (e.g., 100 signals)
    while another day has enough (e.g., 300), masking the underlying data quality issue.

    Returns: (is_ok: bool, error_message: str | None)
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '10000ms'")
            lookback_start = _buysell_lookback_start_date(run_date)

            # Get signal count for each trading day in lookback window
            cur.execute(
                """
                SELECT date, COUNT(*) as signal_count
                FROM buy_sell_daily
                WHERE signal = 'BUY' AND date >= %s AND date <= %s
                GROUP BY date
                ORDER BY date DESC
                """,
                (lookback_start, run_date),
            )
            daily_counts = cur.fetchall()

            if not daily_counts:
                return True, None  # No signals at all is caught by other checks

            # Check each day individually (threshold to catch gaps)
            # UPDATE 2026-08-19: lowered from 200 - that floor (and the "300-1000+ per day"
            # baseline it was set against) predates commit bc0047231 (2026-08-18), which fixed
            # buy_sell_daily re-firing the same BUY/SELL every day a stock stayed beyond its
            # pivot instead of only on the crossover day (live-audited at 73%/64% re-fires of
            # that day's BUY/SELL rows). True per-day counts are now correctly lower
            # (~80-250/day; 8/18 post-fix: 105 BUY/210 total) - 200 would halt on every normal
            # day going forward. See BUY_SELL_DAILY_ANOMALY_THRESHOLD in validation_thresholds.py.
            per_day_signal_floor = 40
            for day_row in daily_counts:
                signal_date = day_row[0]
                day_signal_count = day_row[1]

                if day_signal_count < per_day_signal_floor:  # Per-day threshold
                    msg = (
                        f"[PHASE 7 CRITICAL HALT] buy_sell_daily for {signal_date} has only {day_signal_count} signals "
                        f"(< per-day threshold of {per_day_signal_floor}). This indicates a data quality gap for that specific day. "
                        f"Historical normal (post edge-trigger-fix): ~80-250 signals per day. "
                        f"Check: (1) technical_data_daily status for {signal_date}, "
                        f"(2) buy_sell_daily loader execution for {signal_date}, "
                        f"(3) price_daily completeness. DO NOT accept degraded data per individual day."
                    )
                    logger.critical(msg)
                    log_phase_result_fn(7, "signal_generation", "halt", msg)
                    return False, msg

            return True, None
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 7 CRITICAL] Could not validate per-day signal counts: {e}"
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        return False, msg


def _check_critical_dependencies(run_date: _date, log_phase_result_fn: Callable[..., Any]) -> tuple[bool, str | None]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
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

            # CRITICAL #1.5: stock_scores loader's OWN status must not be FAILED, nor RUNNING
            # within a live window. stock_scores is rebuilt from scratch each day (delete + re-insert,
            # not an upsert - confirmed live 2026-08-10: table holds exactly one date's worth of rows,
            # count == distinct symbol count). The CRITICAL #1 check above only verifies the table is
            # non-empty, which is trivially true even seconds into a rebuild once the first few rows
            # land - it cannot detect a PARTIAL rebuild in progress. Live-reproduced 2026-08-10:
            # stock_scores execution_started 20:26:30, execution_completed 21:52:10; at 21:37:45 and
            # 21:42:53 only 13/4917 symbols had composite_score populated. Two Phase 7 runs during that
            # window found too few qualifying candidates and logged "[PHASE 7] No BUY signals found in
            # lookback window" - a misleading message (520 real BUY signals existed in buy_sell_daily
            # that run) that reads as a market/signal-quality problem when the actual cause was
            # stock_scores mid-rebuild. Mirrors the buy_sell_daily loader-status gate above (#2.5).
            cur.execute(
                """
                SELECT status, error_message, EXTRACT(EPOCH FROM (NOW() - execution_started))
                FROM data_loader_status WHERE table_name = 'stock_scores'
                """
            )
            scores_loader_status_row = cur.fetchone()
            if scores_loader_status_row:
                scores_status, scores_error, scores_age_secs = scores_loader_status_row
                scores_is_live_running = (
                    scores_status == "RUNNING" and scores_age_secs is not None and scores_age_secs < 7200
                )
                if scores_status in ("FAILED", "TIMEOUT") or scores_is_live_running:
                    msg = (
                        f"[PHASE 7 CRITICAL HALT] stock_scores loader's own status is "
                        f"'{scores_status}' (error: {scores_error or 'none'}). stock_scores is rebuilt "
                        f"from scratch daily - composite_score coverage may be partial or mid-write. "
                        f"DO NOT proceed until the loader reaches COMPLETED status. "
                        f"Check data_loader_status for stock_scores."
                    )
                    logger.critical(msg)
                    log_phase_result_fn(7, "signal_generation", "halt", msg)
                    return False, msg

            # CRITICAL #2: market_exposure_daily must have valid data on or before run_date
            # Uses same query pattern as read_market_regime() so guard is consistent with actual read.
            # On weekends/holidays, the most recent trading day's data is sufficient.
            # GOVERNANCE: Must check data_unavailable flag before using exposure data
            cur.execute(
                """
                SELECT exposure_pct, date, data_unavailable, reason
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

            _exposure_pct, exposure_data_date, data_unavailable, reason = (
                exposure_row[0],
                exposure_row[1],
                exposure_row[2],
                exposure_row[3],
            )
            # GOVERNANCE ENFORCEMENT: Fail if data marked unavailable
            if data_unavailable:
                msg = (
                    f"[PHASE 7 CRITICAL] market_exposure_daily marked unavailable (reason: {reason or 'unknown'}). "
                    "Cannot generate signals without valid market exposure assessment."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg
            if exposure_data_date < run_date:
                logger.info(
                    f"[PHASE 7] market_exposure_daily: using data from {exposure_data_date} "
                    f"(most recent available; run_date={run_date})"
                )

            # CRITICAL #2.5: buy_sell_daily loader's OWN status must not be FAILED, nor
            # RUNNING within a live window. The anomaly-floor check below (CRITICAL #3/#4)
            # only catches large statistical drops in signal COUNT - it cannot detect a
            # moderate partial write (e.g. a loader killed 60% through a run, still landing
            # above the floor) nor a genuine read/write race where Phase 7 queries the table
            # while the loader is still mid-insert. Checking the loader's own terminal status
            # directly closes that gap. Live-reproduced 2026-08-10: buy_sell_daily's subprocess
            # was killed (exit 143) mid-run, left status=FAILED with only 121/4623 signals
            # written - the count-based anomaly floor (189) happened to catch that particular
            # case, but a less severe partial write could slip through on count alone.
            # RUNNING is only treated as a live race within a 2h window - an older RUNNING row
            # is more likely an orphaned/stuck status from a past crash (see
            # reap_stale_running_loaders()) than actual concurrent writing, so it falls through
            # to the count-based checks below instead of halting forever until reaped.
            cur.execute(
                """
                SELECT status, error_message, EXTRACT(EPOCH FROM (NOW() - execution_started))
                FROM data_loader_status WHERE table_name = 'buy_sell_daily'
                """
            )
            loader_status_row = cur.fetchone()
            if loader_status_row:
                loader_status, loader_error, loader_age_secs = loader_status_row
                is_live_running = loader_status == "RUNNING" and loader_age_secs is not None and loader_age_secs < 7200
                if loader_status in ("FAILED", "TIMEOUT") or is_live_running:
                    msg = (
                        f"[PHASE 7 CRITICAL HALT] buy_sell_daily loader's own status is "
                        f"'{loader_status}' (error: {loader_error or 'none'}). Signal data may be "
                        f"partial, stale, or mid-write - do not trust the raw signal count. "
                        f"DO NOT proceed until the loader reaches COMPLETED status. "
                        f"Check data_loader_status for buy_sell_daily."
                    )
                    logger.critical(msg)
                    log_phase_result_fn(7, "signal_generation", "halt", msg)
                    return False, msg

            # CRITICAL #3: buy_sell_daily DATA FRESHNESS check (not just existence check)
            # Halts if the most recent trading day has NO signals (indicates upstream failure like technical_data_daily crash)
            # First, find the most recent trading day
            from algo.infrastructure import MarketCalendar

            most_recent_trading_day = run_date
            iterations = 0
            while most_recent_trading_day > run_date - timedelta(days=10) and iterations < 10:
                if MarketCalendar.is_trading_day(most_recent_trading_day):
                    break
                most_recent_trading_day -= timedelta(days=1)
                iterations += 1

            # Check how many BUY signals are on the most recent trading day
            cur.execute(
                """
                SELECT MAX(date) as max_date, COUNT(*) as signal_count
                FROM buy_sell_daily
                WHERE signal = 'BUY' AND date <= %s
                """,
                (run_date,),
            )
            latest_row = cur.fetchone()
            if latest_row is None:
                msg = (
                    "[PHASE 7 CRITICAL] Failed to query buy_sell_daily table. "
                    "Database query returned no result (possible schema issue). "
                    "Check database connection and table existence."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            latest_buysell_date = latest_row[0]
            latest_buysell_count = latest_row[1]

            # DATA FRESHNESS CHECK: Most recent buy_sell_daily entry should be from the most recent trading day
            # If it's older, upstream loaders failed (most likely technical_data_daily)
            if latest_buysell_date is None:
                msg = (
                    "[PHASE 7 CRITICAL HALT] buy_sell_daily table is EMPTY (no records found). "
                    "This indicates buy_sell_daily loader has never run or all data was deleted. "
                    "Check: (1) buy_sell_daily loader execution status, "
                    "(2) data_loader_status table for buy_sell_daily, "
                    "(3) CloudWatch logs for pipeline errors."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            # Check if latest_buysell_date is from the most recent trading day
            # Walk backwards from run_date to find the most recent trading day
            from algo.infrastructure import MarketCalendar

            most_recent_trading_day = run_date
            check_iterations = 0
            while most_recent_trading_day > run_date - timedelta(days=10) and check_iterations < 10:
                if MarketCalendar.is_trading_day(most_recent_trading_day):
                    break
                most_recent_trading_day -= timedelta(days=1)
                check_iterations += 1

            days_stale = (run_date - latest_buysell_date).days

            # TRADING-DAY-AWARE TOLERANCE: the loader publishes buy_sell_daily for trading day D
            # using D's EOD close, so the freshest data available *before* D+1's own close is D's -
            # i.e. up to one trading day of lag is normal, not stale. A raw "most_recent_trading_day
            # - 1 calendar day" tolerance (the previous version of this check) false-halts every
            # Monday (Friday's data is 3 calendar days old) and after any holiday, since it doesn't
            # walk back over the weekend/holiday gap - same bug class already fixed for
            # market_exposure_daily regime staleness (regime_manager.py._expected_regime_date) and
            # for price_daily (phase1_data_freshness.py, Session 239/288). Walk back to the actual
            # previous trading day instead of subtracting a fixed calendar day.
            previous_trading_day = most_recent_trading_day - timedelta(days=1)
            prev_trading_day_iterations = 0
            while not MarketCalendar.is_trading_day(previous_trading_day) and prev_trading_day_iterations < 10:
                previous_trading_day -= timedelta(days=1)
                prev_trading_day_iterations += 1

            is_trading_today = MarketCalendar.is_trading_day(run_date)
            data_is_from_recent_trading_day = latest_buysell_date >= previous_trading_day
            data_is_within_window = latest_buysell_date >= run_date - timedelta(days=4)  # 4-day window covers weekends

            # BLOCKER #9 FIX: Explicit Monday handling - Friday data on Monday is EXPECTED and VALID
            # Markets close Friday, so Friday's EOD close is the most recent data available through Monday morning.
            # We use Friday data on Monday if <1 trading day old, because markets didn't trade over weekend.
            is_monday = run_date.weekday() == 0  # Monday = 0
            is_recent_trading_day_data_on_monday = is_monday and latest_buysell_date >= previous_trading_day

            acceptable_staleness = data_is_from_recent_trading_day or (not is_trading_today and data_is_within_window)
            if is_recent_trading_day_data_on_monday:
                logger.debug(
                    f"[PHASE 7] Monday {run_date}: Using Friday {latest_buysell_date} data "
                    f"(most recent trading day, expected behavior)"
                )

            if latest_buysell_date < previous_trading_day and not acceptable_staleness:
                # Most recent data is OLDER than recent trading days - this is a red flag
                msg = (
                    f"[PHASE 7 CRITICAL HALT] buy_sell_daily data is STALE: most recent is from {latest_buysell_date}. "
                    f"Expected from recent trading day ({most_recent_trading_day}). This indicates: "
                    f"(1) EOD pipeline ({latest_buysell_date}) did not complete, OR "
                    f"(2) Technical_data_daily loader failed (buy_sell_daily depends on it), OR "
                    f"(3) Buy_sell_daily loader itself failed. "
                    f"Check data_loader_status for: (1) technical_data_daily - completion/error status, "
                    f"(2) buy_sell_daily - last_updated timestamp, (3) price_daily freshness. "
                    f"DO NOT proceed with stock_scores fallback - fix upstream data issues first."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            # Check if most recent day has suspiciously ZERO signals
            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND date = %s",
                (latest_buysell_date,),
            )
            today_count_row = cur.fetchone()
            today_count = today_count_row[0] if today_count_row else 0

            # NOTE: no separate "is latest_buysell_date recent enough" gate here - the
            # acceptable_staleness check above already halted (returned False) if
            # latest_buysell_date were too old, so by this point it's already confirmed to be
            # the correct current reference day. A flat `>= run_date - timedelta(days=1)`
            # gate here used to silently disable this anomaly check every weekend (e.g. on a
            # Monday, Friday's real latest_buysell_date is < Sunday, so the gate was always
            # False) - the same bug class as the staleness check itself, but in the opposite,
            # more dangerous direction: it made a real zero-signal upstream failure on the
            # most recent trading day invisible instead of halting on it, the exact failure
            # mode this check exists to catch.
            if today_count == 0:
                # Most recent trading day has 0 signals - this is anomalous
                msg = (
                    f"[PHASE 7 CRITICAL HALT] buy_sell_daily on {latest_buysell_date} has ZERO BUY signals. "
                    f"Historical normal (post edge-trigger-fix, see bc0047231): ~80-250 signals per trading day. "
                    f"This indicates: (1) technical_data_daily loader failed (required for buy_sell generation), "
                    f"(2) Signal generation thresholds were too strict, or "
                    f"(3) No symbols passed selection criteria. "
                    f"Most likely: upstream technical_data_daily failure. "
                    f"Check: (1) technical_data_daily status in data_loader_status, "
                    f"(2) CloudWatch logs for buy_sell_daily loader errors, "
                    f"(3) Check if price_daily and other dependencies are fresh. "
                    f"DO NOT use stock_scores fallback - fix underlying data issue first."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            # Severe but non-zero collapse: Drop from typical 300+/day to handful of signals
            # indicates underlying failure (upstream loader degradation or universe coverage collapse).
            # Use dynamically-calculated threshold (median_30d / 3) not hardcoded constant.
            anomaly_threshold = _calculate_dynamic_anomaly_threshold()
            if 0 < today_count < anomaly_threshold:
                msg = (
                    f"[PHASE 7 CRITICAL HALT] buy_sell_daily on {latest_buysell_date} has only {today_count} "
                    f"BUY signals (< anomaly floor of {anomaly_threshold}). "
                    f"This indicates a severe upstream data quality problem: "
                    f"(1) technical_data_daily loader partially failed, "
                    f"(2) universe coverage collapsed for another reason. "
                    f"Check: (1) technical_data_daily status in data_loader_status, "
                    f"(2) CloudWatch logs for buy_sell_daily loader errors, "
                    f"(3) Check if price_daily and other dependencies are fresh. "
                    f"DO NOT use stock_scores fallback - fix underlying data issue first."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return False, msg

            # Data freshness and signal count look OK
            if days_stale == 1:
                logger.info(
                    f"[PHASE 7] buy_sell_daily is 1 day old (dated {latest_buysell_date}, "
                    f"{today_count} signals on that day). "
                    f"This is expected for morning runs (EOD pipeline ran yesterday evening)."
                )
            else:
                logger.info(
                    f"[PHASE 7] buy_sell_daily freshness OK: latest from {latest_buysell_date} "
                    f"({latest_buysell_count} signals in table)"
                )

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[PHASE 7 CRITICAL] Could not validate critical dependencies: {e}"
        logger.critical(msg, exc_info=True)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        return False, msg

    return True, None


def _should_halt_on_zero_scored_symbols(score_result: dict[str, Any]) -> bool:
    """A symbols_processed == 0 signal-quality-score result should only halt Phase 7 when it
    signals a real failure (lock contention aside, which is its own non-halting degraded path
    handled by the caller). `already_computed_today` and `no_signals_found` are both legitimate,
    non-error reasons for an empty result and must not trip the halt.
    """
    return not (
        score_result.get("lock_contention", False)
        or score_result.get("already_computed_today", False)
        or score_result.get("no_signals_found", False)
    )


def _validate_composite_score_for_ranking(score: Any, symbol: Any) -> None:
    """Fail fast if a composite_score is unfit to be used as a ranking sort key.

    None/wrong-type checks alone are not sufficient: isinstance(score, (int, float)) does
    NOT catch NaN/Infinity - float('nan') is a real float instance (same NaN-comparison-guard
    class as the original signal_quality_score version of this check, found 2026-08-10). A NaN
    key sailing through into a downstream .sort() call has no total order in Python (NaN < x and
    x < NaN are both False) - the NaN-scored signal's position in the ranked list is
    undefined, potentially landing at the top and proceeding toward real trade execution
    as if it were the highest-quality candidate.

    Raises:
        RuntimeError: if score is None (a logic error - callers must filter None first).
        ValueError: if score is non-numeric, NaN, or Infinity.
    """
    if score is None:
        msg = (
            f"[PHASE 7 CRITICAL] Signal {symbol} has None composite_score "
            f"after all filters. This is a logic error in the filtering code - the upstream "
            f"INNER JOIN requires composite_score IS NOT NULL, so this should be unreachable. "
            f"Failing fast to expose the issue."
        )
        logger.critical(msg)
        raise RuntimeError(msg)
    if not isinstance(score, (int, float)):
        msg = (
            f"[PHASE 7 CRITICAL] Signal {symbol} composite_score is {type(score).__name__}, "
            f"expected float. composite_score must be numeric for sorting. Cannot proceed."
        )
        logger.critical(msg)
        raise ValueError(msg)
    if math.isnan(score) or math.isinf(score):
        msg = (
            f"[PHASE 7 CRITICAL] Signal {symbol} composite_score is non-finite "
            f"({score!r}). Cannot sort/rank by a NaN/Infinity score - would produce undefined "
            f"ordering and could rank a corrupted signal as top-quality. Failing fast."
        )
        logger.critical(msg)
        raise ValueError(msg)


def _resolve_min_composite_score(
    exposure_constraints: ExposureConstraints | None,
    config: dict[str, Any],
) -> float:
    """Resolve the entry-quality bar (min_composite_score) for this run.

    FIXED 2026-08-25 (see [[phase7_min_composite_score_fallback_not_fail_closed_flagged_20260825]]
    in memory): this used to independently re-call read_market_regime()/tier_for_exposure() here
    - a SECOND live lookup of the same regime Phase 5 already computed moments earlier - and on
    any transient failure of that redundant call (a DB blip unrelated to Phase 5's own result),
    fell back to the LEAST selective tier's threshold (60.0), silently admitting lower-quality
    signals than the actual regime called for even when Phase 5 succeeded fine and reported a
    stricter tier. Fixed per option (a) from that memory entry: use Phase 5's already-fetched
    exposure_constraints.min_composite_score directly - eliminates the redundant call (and its
    independent failure mode) entirely rather than picking a different fallback number. Only
    re-derive from config if exposure_constraints itself is unavailable or lacks the key (e.g.
    the orchestrator's own halt-safe fallback dict when Phase 5 didn't run at all - see
    orchestrator.py's exposure_constraints construction - which already forces
    halt_new_entries=True, so no entries get through regardless of min_composite_score there).
    """
    if exposure_constraints is not None and exposure_constraints.get("min_composite_score") is not None:
        min_composite_score = float(exposure_constraints["min_composite_score"])
        logger.info(
            f"[PHASE 7 TUNING] Using regime-based min_composite_score={min_composite_score:.0f} "
            f"from Phase 5's exposure_constraints (tier={exposure_constraints.get('tier_name')})"
        )
        return min_composite_score

    logger.warning(
        "[PHASE 7] exposure_constraints missing min_composite_score (Phase 5 did not run or "
        "produced fallback constraints) - falling back to config value."
    )
    return get_config_float(config, "phase7_min_composite_score", "phase_7_signal_generation", default=60.0)


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
    exposure_constraints: ExposureConstraints | None = None,
    check_halt_flag: Callable[..., bool] | None = None,
    config: dict[str, Any] | None = None,
) -> PhaseResult:

    if config is None:
        raise ValueError(
            "phase7_signal_generation.run() requires explicit config parameter (dependency injection). "
            "Get config at orchestrator level and pass it explicitly."
        )

    # Validate required config keys at phase entry (fail-fast)
    validate_phase_config(config, "phase_7_signal_generation")

    # TUNING FIX (2026-08-02): Enforce regime-based minimum composite scores (see
    # _resolve_min_composite_score's docstring for the 2026-08-25 fix to how this is sourced).
    # Old: hard-coded min_composite_score=30 (below median 32.75, rejected only 60% of universe)
    # New: Use market regime tier's minimum (uptrend=60, pressure=65, caution=70, correction=75 -
    # raised from 50/60/70/80 on 2026-08-24, see EXPOSURE_TIERS in exposure_policy.py)
    # This dramatically raises entry quality by filtering weak signals in all market conditions.
    min_composite_score = _resolve_min_composite_score(exposure_constraints, config)

    phase_start = time.time()
    logger.info("[PHASE 7] Starting signal generation")

    min_close_quality = (
        get_config_float(config, "min_close_quality_pct", "phase_7_signal_generation", default=40.0) / 100.0
    )

    # ISSUE #8 FIX: Guard rails - check critical dependencies BEFORE signal generation
    # Fails fast if ANY dependency is unavailable, preventing silent degradation
    ok, dep_error = _check_critical_dependencies(run_date, log_phase_result_fn)
    if not ok:
        return PhaseResult(
            7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, dep_error
        )

    # ISSUE #7 FIX: Check per-day signal counts to catch individual day degradation
    # Prevents accepting 250 total signals (150 Fri + 100 Mon) when Friday had a data gap
    ok_per_day, per_day_error = _check_per_day_signal_counts(run_date, log_phase_result_fn)
    if not ok_per_day:
        return PhaseResult(
            7, "signal_generation", "halted", {"qualified_trades": [], "liquidity_passed": 0}, True, per_day_error
        )

    # SESSION 367 FIX: Compute signal quality scores BEFORE Phase 8 entry
    # CRITICAL: Signal quality scores must be available for Phase 8 to apply quality gates
    # This prevents trades from entering without SQS >= 75 validation (root cause of 38.5% win rate)
    # OPTIMIZATION (Session Current): Reduced backfill_days from 60 to 3 to eliminate lock contention
    # Phase 7 runs 3x daily (9:30 AM, 1 PM, 3 PM) so 3-day lookback ensures all recent signals scored
    # This reduces processing from 5468 symbols for 60 days -> ~1-2k symbol-days, holding lock 5 min instead of 35 min
    # CRITICAL FIX: Skip signal quality score computation in dry-run mode (no trades will execute anyway)
    score_result, halt_result = _compute_signal_quality_scores_for_run(run_date, dry_run, log_phase_result_fn)
    if halt_result is not None:
        return halt_result

    _backfill_orphaned_signal_scores()

    halt_result = _check_halt_flag_gate(check_halt_flag, log_phase_result_fn)
    if halt_result is not None:
        return halt_result

    regime, halt_result = _check_market_regime_gate(run_date, log_phase_result_fn)
    if halt_result is not None:
        return halt_result

    halt_result = _check_exposure_constraints_gate(exposure_constraints, log_phase_result_fn)
    if halt_result is not None:
        return halt_result

    signal_source = "buysell_breakout"
    raw_candidates, halt_result = _fetch_and_handle_candidates(
        run_date, min_composite_score, min_close_quality, log_phase_result_fn
    )
    if halt_result is not None:
        return halt_result

    quality_filtered, degraded_result = _apply_post_fetch_quality_filters(
        raw_candidates, run_date, signal_source, log_phase_result_fn
    )
    if degraded_result is not None:
        return degraded_result

    liq_passed, _liq_checked = _run_liquidity_checks(quality_filtered, run_date, config)

    liq_passed = _filter_inactive_symbols(liq_passed)

    _finalize_ranking_and_log(liq_passed, signal_source)

    elapsed = time.time() - phase_start
    log_phase_result_fn(
        7,
        "signal_generation",
        "success",
        f"{len(liq_passed)} signals qualified from {len(raw_candidates)} candidates",
    )

    # signals_generated/buy_signals/sell_signals/avg_strength/symbols_with_signals: the
    # health dashboard (dashboard/panels/health.py, Phase 7 detail row) reads these exact
    # keys, but this dict never carried them - previously always rendered nothing.
    # sell_signals=0 is not a guess: every query feeding this phase filters
    # WHERE signal = 'BUY' (this system is long-only), so every qualified trade here is
    # necessarily a buy signal by construction.
    strength_vals = [float(s["signal_quality_score"]) for s in liq_passed if s.get("signal_quality_score") is not None]

    # DEBUG: Log what signal_quality_score values are in liq_passed
    if liq_passed:
        logger.info("[PHASE 7 DEBUG] Top 5 qualified trades signal_quality_score values:")
        for i, sig in enumerate(liq_passed[:5]):
            logger.info(
                f"  {i + 1}. {sig.get('symbol')}: sqs={sig.get('signal_quality_score')}, trend={sig.get('trend_template_score')}, base_q={sig.get('base_quality')}"
            )

    phase_data = {
        "qualified_trades": liq_passed,
        "total_candidates": len(raw_candidates),
        "pre_liquidity_check": len(quality_filtered),
        "liquidity_passed": len(liq_passed),
        "regime": regime,
        "signal_source": signal_source,
        "signals_generated": len(liq_passed),
        "buy_signals": len(liq_passed),
        "sell_signals": 0,
        "avg_strength": (sum(strength_vals) / len(strength_vals)) if strength_vals else None,
        "symbols_with_signals": [s["symbol"] for s in liq_passed if s.get("symbol")],
        # CRITICAL FIX: Include lock_contention flag so Phase 8 knows if signal quality score
        # batch pre-computation had contention. This is safe degradation (inline scores still computed)
        # but Phase 8 should log it for visibility.
        "lock_contention": score_result.get("lock_contention", False),
        "no_signals_found": score_result.get("no_signals_found", False),
    }
    validate_phase_data(7, phase_data)
    return PhaseResult(
        7,
        "signal_generation",
        "ok",
        phase_data,
        False,
        f"Generated {len(liq_passed)} signals in {elapsed:.1f}s (source={signal_source})",
    )


def _backfill_orphaned_signal_scores() -> None:
    """BACKFILL: Compute quality scores for older loader-created signals that don't have scores.

    This is separate from the batch loader in _compute_signal_quality_scores_for_run() (called
    just before this in run()) - it specifically targets orphaned signals that were created by
    the EOD pipeline but never processed by Phase 7 (timing mismatch: EOD creates signals at
    4:05 PM, Phase 7 runs at 9:30 AM, 1 PM, 3 PM).

    Kept in this module (not moved to algo/orchestrator/phase7_run_steps.py alongside the other
    run() step helpers) because it calls compute_signal_quality_components() - see
    _score_candidates_inline's docstring above for why both call sites of that shared formula
    must stay in phase7_signal_generation.py's own source
    (tests/unit/test_signal_quality_score_single_source_of_truth_20260820.py inspects this
    module's source text and requires >= 2 occurrences).

    A failure here is logged but never halts Phase 7 - this is a secondary/optional process to
    score orphaned signals; primary score computation already ran by the time this is called.
    """
    try:
        logger.info("[PHASE 7] Backfilling quality scores for orphaned loader-created signals")
        with DatabaseContext("read") as cur_backfill:
            # Find signals without scores from last 60 days
            # (Extended from 3 days to catch signals for past dates created by backfill pipelines)
            cur_backfill.execute("""
                SELECT symbol, date FROM buy_sell_daily
                WHERE signal_quality_score IS NULL
                  AND signal = 'BUY'
                  AND date >= (CURRENT_DATE - INTERVAL '60 days')
                ORDER BY date DESC, symbol
                LIMIT 500
            """)
            backfill_rows = cur_backfill.fetchall()

        if backfill_rows:
            from loaders.signal_quality_scorer import compute_signal_quality_components

            backfill_scores = []

            # CRITICAL FIX: Move DatabaseContext outside the for loop to prevent connection leaks
            # Opening a new context for each iteration exhausts the connection pool
            with DatabaseContext("read") as cur_tech_shared:
                for symbol, signal_date in backfill_rows:
                    try:
                        # Fetch technical data AND trend template data for full score computation
                        cur_tech_shared.execute(
                            """
                            WITH price_window AS (
                                SELECT date, close,
                                       MAX(high) OVER (
                                           ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                                       ) AS high_52w
                                FROM price_daily
                                WHERE symbol = %s AND date <= %s
                            )
                            SELECT
                              t.rsi, t.macd, t.macd_signal,
                              tr.minervini_trend_score, tr.weinstein_stage,
                              CASE WHEN pw.high_52w > 0
                                   THEN (pw.close - pw.high_52w) / pw.high_52w * 100
                                   ELSE NULL END AS percent_from_52w_high
                            FROM technical_data_daily t
                            LEFT JOIN trend_template_data tr ON tr.symbol = t.symbol AND tr.date = t.date
                            LEFT JOIN price_window pw ON pw.date = t.date
                            WHERE t.symbol = %s AND t.date = %s
                        """,
                            (symbol, signal_date, symbol, signal_date),
                        )
                        tech_row = cur_tech_shared.fetchone()

                        if not tech_row:
                            logger.debug(f"[PHASE 7 BACKFILL] {symbol}: No technical data for {signal_date}, skipping")
                            continue

                        rsi, macd, macd_signal, minervini, weinstein, pct_from_52w_high = tech_row
                        # CRITICAL: Missing trend data for older dates is expected (historical backfill)
                        # Skip rather than halt, since backfill targets old signals without scores
                        # Main signal generation (for current date) will halt if trend data missing
                        if minervini is None or weinstein is None:
                            logger.debug(
                                f"[PHASE 7 BACKFILL] {symbol} {signal_date}: Skipping - missing trend template data. "
                                f"This is expected for older dates. Main signal generation will halt if trend data missing for current date."
                            )
                            continue
                        # Compute score via the same shared formula as the main inline scorer above
                        # and the batch loader (loaders/signal_quality_scorer.py::
                        # compute_signal_quality_components) - see the fix note on the main inline
                        # scorer block for why this consolidation matters.
                        try:
                            institutional_ownership = _fetch_institutional_ownership_for_scoring(symbol)
                            vcp_strength = _fetch_vcp_strength_for_scoring(symbol, str(signal_date))
                            scores = compute_signal_quality_components(
                                signal_type="BUY",
                                rsi=rsi,
                                macd=macd,
                                macd_signal=macd_signal,
                                minervini_score=minervini,
                                weinstein_stage=weinstein,
                                percent_from_52w_high=(
                                    float(pct_from_52w_high) if pct_from_52w_high is not None else None
                                ),
                                institutional_ownership=institutional_ownership,
                                vcp_strength=vcp_strength,
                            )
                            composite_sqs = scores["composite_sqs"]
                            if composite_sqs < 0 or composite_sqs > 100:
                                raise ValueError(f"Composite SQS out of range: {composite_sqs} (expected 0-100)")
                            backfill_scores.append((composite_sqs, composite_sqs, symbol, signal_date))
                            logger.debug(f"[PHASE 7 BACKFILL] {symbol} {signal_date}: Computed score={composite_sqs}")
                        except ValueError as calc_e:
                            raise RuntimeError(
                                f"[PHASE 7 BACKFILL] Score calculation failed for {symbol} {signal_date}: {calc_e} "
                                f"Cannot backfill scores with invalid calculation logic. "
                                f"Check scorer implementation and technical data quality."
                            ) from calc_e
                    except RuntimeError as rt_e:
                        raise RuntimeError(f"[PHASE 7 BACKFILL] Score calculation runtime error: {rt_e}") from rt_e
                    except Exception as bf_e:
                        logger.error(
                            f"[PHASE 7 BACKFILL] Unexpected error computing score for {symbol}: {type(bf_e).__name__}: {bf_e}",
                            exc_info=True,
                        )
                        raise RuntimeError(
                            f"[PHASE 7 BACKFILL] Failed to compute score for {symbol} {signal_date}: {type(bf_e).__name__}: {bf_e}"
                        ) from bf_e

            # Write backfill scores
            if backfill_scores:
                try:
                    with DatabaseContext("write") as cur_write:
                        for bf_sqs, entry_sqs, symbol, signal_date in backfill_scores:
                            cur_write.execute(
                                """
                                UPDATE buy_sell_daily
                                SET signal_quality_score = %s, entry_quality_score = %s
                                WHERE symbol = %s AND date = %s AND signal_quality_score IS NULL
                            """,
                                (bf_sqs, entry_sqs, symbol, signal_date),
                            )
                    logger.info(f"[PHASE 7 BACKFILL] Wrote {len(backfill_scores)} backfill scores to buy_sell_daily")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as write_db_e:
                    msg = (
                        f"[PHASE 7 BACKFILL CRITICAL] Failed to persist backfill scores to database: {write_db_e} "
                        f"Computed {len(backfill_scores)} signal quality scores but could not write them. "
                        f"This leaves signals without scores, violating data integrity. "
                        f"Check: (1) database connection, (2) buy_sell_daily table writable, "
                        f"(3) sufficient disk space, (4) transaction state."
                    )
                    logger.critical(msg)
                    raise RuntimeError(msg) from write_db_e
                except Exception as write_bf_e:
                    msg = (
                        f"[PHASE 7 BACKFILL CRITICAL] Unexpected error writing backfill scores: {type(write_bf_e).__name__}: {write_bf_e} "
                        f"Cannot persist {len(backfill_scores)} computed signal quality scores. "
                        f"This violates data integrity - scores must be persisted once computed."
                    )
                    logger.critical(msg)
                    raise RuntimeError(msg) from write_bf_e
        else:
            logger.debug("[PHASE 7 BACKFILL] No orphaned signals to backfill")
    except RuntimeError as rt_e:
        raise RuntimeError(f"[PHASE 7 BACKFILL] Backfill process critical error: {rt_e}") from rt_e
    except Exception as bf_outer_e:
        msg = (
            f"[PHASE 7 BACKFILL] Backfill process failed: {type(bf_outer_e).__name__}: {bf_outer_e} "
            f"This is a secondary/optional process to score orphaned signals that weren't scored during initial generation. "
            f"Log the error for investigation but allow Phase 7 to continue - primary score computation already ran."
        )
        logger.error(msg, exc_info=True)

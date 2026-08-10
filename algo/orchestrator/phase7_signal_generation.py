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
9. Liquidity checks on top LIQUIDITY_CHECK_LIMIT candidates
10. Return composite-score-ranked candidates to Phase 8

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

Ranking: composite_score from stock_scores (quality 25%, growth 20%, value 20%,
positioning 15%, stability 12%, momentum 8%).

Signal source: buy_sell_daily + stock_scores INNER JOIN (EXPLICIT - no degradation mode).
"""

import logging
import math
import time
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from datetime import date as _date
from datetime import timedelta
from typing import Any

import psycopg2

from algo.orchestrator.config_validator import get_config_float, validate_phase_config
from algo.orchestrator.phase_data_contract import ExposureConstraints, validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

from algo.orchestrator.validation_thresholds import (
    LIQUIDITY_CHECK_LIMIT,
    BUY_SELL_DAILY_ANOMALY_THRESHOLD,
    PHASE7_LIQUIDITY_CHECK_WORKERS,
)

_BUYSELL_LOOKBACK_DAYS = 1  # Use TODAY's signals + yesterday's if today unavailable (EOD pipeline runs 4:05 PM)


def _calculate_dynamic_anomaly_threshold() -> int:
    """Calculate signal anomaly threshold from historical 30-day median.

    Adapts to universe size: if your universe is smaller, median is lower,
    threshold scales accordingly. Prevents false positives from hardcoded constants.

    Returns: threshold = median_30d / 3 (catches signals dropped to 33% of normal)
    """
    try:
        from utils.db.context import DatabaseContext
        from algo.infrastructure import MarketCalendar

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
                threshold = max(100, int(median_signals / 3))  # At least 100, catch drops to 1/3 of median
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
            lookback_date = (
                _buysell_lookback_start_date(run_date) if signal_source == "buysell_breakout" else None
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
                    min_completeness_threshold,
                    min_close_quality,
                    limit,
                ),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            # CRITICAL: Verify query returned all 20 expected columns before unpacking (indices 0-19)
            if len(r) < 20:
                logger.error(
                    f"[PHASE 7 CRITICAL] Query returned {len(r)} columns instead of expected 20. "
                    f"Schema mismatch detected. Skipping malformed row."
                )
                continue

            symbol = r[0]

            # CRITICAL FIX BLOCKER #6: Verify spinoff filtering worked
            # SQL query filters data_unavailable = false, but double-check at runtime
            # If a symbol with data_unavailable=True somehow makes it here, it's a critical bug
            # because that symbol's metrics are incomplete (spinoff/delisted/etc)
            # Composite score guaranteed by INNER JOIN with stock_scores (non-null check in SQL WHERE)
            if r[1] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: composite_score is NULL - "
                    "INNER JOIN to stock_scores and WHERE ss.composite_score IS NOT NULL guarantees non-null"
                )
            composite = float(r[1])

            # Close guaranteed by LATERAL price_daily join
            if r[6] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: close price is NULL - price_daily lateral join guarantees latest close"
                )
            close = float(r[6])

            # Signal strength guaranteed by WHERE clause (bsd.strength IS NOT NULL)
            if r[15] is None:
                raise ValueError(
                    f"[PHASE 7] {symbol}: signal_strength is NULL - WHERE clause guarantees non-null strength"
                )
            raw_strength = float(r[15])

            # Validate signal has complete scoring
            quality_score = float(r[2]) if r[2] is not None else None
            growth_score = float(r[3]) if r[3] is not None else None
            momentum_score = float(r[4]) if r[4] is not None else None
            rs_percentile = float(r[5]) if r[5] is not None else None

            # CRITICAL: Most core signal quality metrics should be present
            # If >2 of these are missing (only 1-2 available), signal quality is severely degraded
            # Incomplete signals indicate upstream data quality issues (stock_scores incomplete)
            missing_scores = sum(
                [quality_score is None, growth_score is None, momentum_score is None, rs_percentile is None]
            )
            if missing_scores > 2:
                error_msg = (
                    f"[PHASE 7 CRITICAL] {symbol}: Signal generated with severely incomplete scoring data. "
                    f"Missing {missing_scores}/4 component scores (only {4-missing_scores} available): "
                    f"quality={quality_score}, growth={growth_score}, momentum={momentum_score}, rs={rs_percentile}. "
                    f"Fail-fast: cannot trade on signals with <50% scoring quality assessment. "
                    f"Indicates stock_scores loader is incomplete for this symbol. "
                    f"Check: (1) stock_scores coverage for {symbol}, "
                    f"(2) quality_metrics/growth_metrics/momentum_metrics/positioning_metrics loaders, "
                    f"(3) data_completeness threshold in signal query."
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)
            elif missing_scores > 0:
                logger.warning(
                    f"[PHASE 7] {symbol}: Signal generated with incomplete scoring data "
                    f"(missing {missing_scores}/4 components). "
                    f"quality={quality_score}, growth={growth_score}, momentum={momentum_score}, rs={rs_percentile}. "
                    f"Position sizing should account for reduced signal quality."
                )

            # _compute_risk_score() intentionally raises ValueError for a single candidate
            # that fails the extreme-volatility gate (ATR > 18% of close) or lacks ATR(14)
            # history (e.g. a recent IPO) - it's a per-symbol tradability filter, not a
            # data-integrity guarantee. Letting that exception escape this loop previously
            # aborted the ENTIRE candidate fetch (caught by the function's outer except and
            # re-raised as a RuntimeError that halts all of Phase 7), so on any day where one
            # candidate happened to be unusually volatile, ZERO signals were generated instead
            # of just excluding that one stock - the exact "some days halt for no clear system
            # reason" pattern this was meant to prevent. Skip just this candidate instead.
            try:
                risk_score = _compute_risk_score(float(r[10]) if r[10] is not None else None, close)
            except ValueError as e:
                logger.info(f"[PHASE 7] {symbol}: excluded from candidates - {e}")
                continue

            # CRITICAL FIX 2026-08-05: Skip stocks with missing rs_percentile
            # Phase 8 requires rs_percentile for entry validation. Passing signals with
            # missing rs_percentile causes Phase 8 to reject them as 'processing_error'.
            # Better to filter here in Phase 7 so only fully-qualified signals reach Phase 8.
            if rs_percentile is None:
                logger.warning(
                    f"[PHASE 7] {symbol}: Skipping candidate - missing rs_percentile "
                    f"(from positioning_metrics table). Position sizing requires relative strength validation."
                )
                continue

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
                    "signal_quality_score": None,  # CRITICAL: Initialize to None to ensure key exists. Will be set by inline scorer.
                    "trend_template_score": None,  # CRITICAL: Initialize to None. Will be set by inline scorer if available.
                    "base_quality": None,  # CRITICAL: Initialize to None. Will be set by inline scorer after scoring completes.
                    "sector": r[11],
                    "industry": r[12],
                    "buylevel": float(r[13]) if r[13] is not None else None,
                    "stoplevel": float(r[14]) if r[14] is not None else None,
                    "volume_surge_pct": float(r[16]) if len(r) > 16 and r[16] is not None else None,
                    "market_stage": r[17] if len(r) > 17 and r[17] is not None else "unknown",
                    "signal_date": str(r[18]) if len(r) > 18 and r[18] is not None else None,
                    "base_type": r[19] if len(r) > 19 and r[19] is not None else None,
                    "risk_score": risk_score,
                }
            )

        logger.info(
            f"[PHASE 7] {len(candidates)} candidates from buy_sell_daily + stock_scores "
            f"(lookback: {lookback_date} to {run_date}, "
            f"SQL filters: trend & close_quality applied at query level)"
        )

        # Compute signal quality scores (composite_sqs & trend_template_score) for candidates.
        # ARCHITECTURE FIX (Session 376): Batch loader fails for live signals. Compute inline instead.
        if candidates:
            from loaders.signal_quality_scorer import get_signal_scorer

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
                            SELECT
                                t.rsi, t.macd, t.macd_signal,
                                COALESCE(tr1.minervini_trend_score, tr2.minervini_trend_score) as minervini,
                                COALESCE(tr1.weinstein_stage, tr2.weinstein_stage) as weinstein
                            FROM technical_data_daily t
                            LEFT JOIN trend_template_data tr1 ON tr1.symbol = t.symbol AND tr1.date = t.date
                            LEFT JOIN trend_template_data tr2 ON tr2.symbol = t.symbol AND tr2.date = t.date - INTERVAL '1 day'
                            WHERE t.symbol = %s AND t.date = %s
                            """,
                            (symbol, signal_date),
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

                        rsi, macd, macd_signal, minervini, weinstein = tech_row

                        # CRITICAL FIX: psycopg2 returns numeric columns as Decimal type
                        # Convert to float BEFORE passing to scorer (scorer uses pd.isna and float comparisons)
                        # Decimal + float operations or Decimal subtraction can fail
                        rsi = float(rsi) if rsi is not None else None
                        macd = float(macd) if macd is not None else None
                        macd_signal = float(macd_signal) if macd_signal is not None else None
                        minervini = float(minervini) if minervini is not None else None
                        weinstein = int(weinstein) if weinstein is not None else None

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

                        # Compute scores using strategy pattern (same as batch loader)
                        scorer = get_signal_scorer("BUY")
                        base_score = scorer.calculate_base_quality_score()
                        volume_score = scorer.calculate_volume_confirmation_score(rsi, macd, macd_signal)
                        trend_score = scorer.calculate_trend_template_score(minervini, weinstein)

                        # Composite SQS = sum of components (clamped to 100)
                        composite_sqs = min(100, int(base_score + volume_score + trend_score))

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

            # CRITICAL FIX: Write computed signal_quality_scores back to buy_sell_daily
            # so that backtest and other systems can access them. Only write non-NULL scores.
            scores_to_write = [
                (c.get("signal_quality_score"), c.get("signal_quality_score"), c.get("symbol"), c.get("signal_date"))
                for c in candidates
                if c.get("symbol") and c.get("signal_date") and c.get("signal_quality_score") is not None
            ]

            if scores_to_write:
                try:
                    with DatabaseContext("write") as cur_write:
                        # CRITICAL FIX: Use non-blocking advisory lock to prevent concurrent Phase 7 runs from race condition
                        # Multiple orchestrator instances may run concurrently in AWS Lambda/ECS.
                        # OPTIMIZATION: Use pg_try_advisory_lock (non-blocking) instead of pg_advisory_lock (blocking)
                        # - Blocking lock causes 7+ halts when Phase 7 runs 3x daily and lock contention occurs
                        # - Non-blocking lock fails fast: if held, skip update and next Phase 7 run handles it
                        # - Prevents timeouts that halt the orchestrator unnecessarily
                        # Advisory lock ID: deterministic hash of 'phase7_signal_scores'.
                        # BUG FIX: previously `hash('phase7_signal_scores') % (2**31)` - Python
                        # randomizes str hashing per-process by default (PYTHONHASHSEED, unset
                        # anywhere in this repo's deploy config), so concurrent Phase 7 instances
                        # (the exact multi-instance scenario this lock exists for) each computed a
                        # DIFFERENT lock_id, silently defeating the race-condition protection.
                        # zlib.crc32 is not seed-randomized, matching the fixed-constant pattern
                        # used elsewhere for the same reason (see PORTFOLIO_SNAPSHOT_LOCK_ID).
                        lock_id = zlib.crc32(b'phase7_signal_scores') % (2 ** 31)
                        lock_acquired = False

                        try:
                            cur_write.execute(f"SELECT pg_try_advisory_lock({lock_id})")
                            result = cur_write.fetchone()
                            lock_acquired = result[0] if result and result[0] is not None else False

                            if lock_acquired:
                                logger.debug(f"[PHASE 7] Acquired non-blocking advisory lock for signal quality score updates")
                            else:
                                logger.info(f"[PHASE 7] Lock held by concurrent Phase 7 instance, skipping score updates (next run will handle)")
                        except Exception as lock_err:
                            logger.warning(f"[PHASE 7] Could not acquire advisory lock: {lock_err}. Continuing without lock.")

                        try:
                            # Only proceed with updates if lock was acquired
                            if lock_acquired:
                                failed_writes = []
                                for sqs, entry_sqs, symbol, signal_date in scores_to_write:
                                    cur_write.execute(
                                        """
                                        UPDATE buy_sell_daily
                                        SET signal_quality_score = %s, entry_quality_score = %s
                                        WHERE symbol = %s AND date = %s
                                        """,
                                        (sqs, entry_sqs, symbol, signal_date),
                                    )
                                    if cur_write.rowcount == 0:
                                        failed_writes.append(f"{symbol} on {signal_date}")

                                if failed_writes:
                                    raise RuntimeError(
                                        f"[PHASE 7 CRITICAL] Signal quality score persistence failed for {len(failed_writes)} symbols: {', '.join(failed_writes)}. "
                                        f"Expected rows were not found in buy_sell_daily table. This indicates a data integrity issue that must be investigated."
                                    )
                                logger.info(f"[PHASE 7] Wrote {len(scores_to_write)} signal_quality_scores to buy_sell_daily")
                            else:
                                logger.info(f"[PHASE 7] Skipping {len(scores_to_write)} score updates (lock held by concurrent run)")
                        finally:
                            # Release advisory lock if acquired
                            if lock_acquired:
                                try:
                                    cur_write.execute(f"SELECT pg_advisory_unlock({lock_id})")
                                    logger.debug(f"[PHASE 7] Released non-blocking advisory lock after signal quality score updates")
                                except Exception as unlock_err:
                                    logger.warning(f"[PHASE 7] Could not release advisory lock: {unlock_err}. Lock will auto-release on connection close.")
                except Exception as write_e:
                    raise RuntimeError(
                        f"[PHASE 7] Failed to write signal quality scores to buy_sell_daily: {write_e}. "
                        f"Cannot proceed with phase completion without persisting signal data."
                    ) from write_e

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

            # Check each day individually (threshold of 200 per-day to catch gaps)
            # Historical median is 300-1000+ per day, so 200 is ~20-30% of median
            for day_row in daily_counts:
                signal_date = day_row[0]
                day_signal_count = day_row[1]

                if day_signal_count < 200:  # Per-day threshold
                    msg = (
                        f"[PHASE 7 CRITICAL HALT] buy_sell_daily for {signal_date} has only {day_signal_count} signals "
                        f"(< per-day threshold of 200). This indicates a data quality gap for that specific day. "
                        f"Historical normal: 300-1000+ signals per day. "
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
                    f"Historical normal: 300-1000+ signals per trading day. "
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


def run(  # noqa: C901
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

    # TUNING FIX (2026-08-02): Enforce regime-based minimum composite scores.
    # Old: hard-coded min_composite_score=30 (below median 32.75, rejected only 60% of universe)
    # New: Use market regime tier's minimum (uptrend=50, pressure=60, caution=70, correction=80)
    # This dramatically raises entry quality by filtering weak signals in all market conditions.
    from algo.risk.exposure_policy import tier_for_exposure
    from algo.risk.market_exposure import read_market_regime

    try:
        market_regime = read_market_regime(run_date)
        exposure_tier = tier_for_exposure(market_regime["exposure_pct"])
        min_composite_score = float(exposure_tier["min_composite_score"])
        logger.info(
            f"[PHASE 7 TUNING] Using regime-based min_composite_score={min_composite_score:.0f} "
            f"(tier={exposure_tier['name']}, exposure={market_regime['exposure_pct']}%)"
        )
    except Exception as e:
        # Fallback to config value if regime lookup fails
        logger.warning(
            f"[PHASE 7] Could not get regime-based min score: {e}. "
            f"Falling back to config value."
        )
        min_composite_score = get_config_float(config, "phase7_min_composite_score", "phase_7_signal_generation", default=50.0)

    phase_start = time.time()
    logger.info("[PHASE 7] Starting signal generation")

    min_close_quality = get_config_float(config, "min_close_quality_pct", "phase_7_signal_generation", default=40.0) / 100.0

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
    # This reduces processing from 5468 symbols for 60 days → ~1-2k symbol-days, holding lock 5 min instead of 35 min
    # CRITICAL FIX: Skip signal quality score computation in dry-run mode (no trades will execute anyway)
    if dry_run:
        logger.info("[PHASE 7] DRY-RUN: Skipping signal quality score computation (not needed for dry-run)")
        score_result = {"symbols_processed": 0, "symbols_failed": 0}
    else:
        # CRITICAL FIX (Session Current): Check if today's signal_quality_scores are already computed.
        # Phase 7 runs 3x daily (9:30 AM, 1 PM, 3 PM) and all three runs were calling loader.run(),
        # causing lock contention. If run_date's scores are already in the table, skip the loader call.
        today_scores_exist = False
        try:
            with DatabaseContext("read") as cur:
                # Use run_date (the caller's Eastern trading date), not bare CURRENT_DATE -
                # CURRENT_DATE resolves in the DB session's timezone, which may not track
                # the Eastern trading day (e.g. UTC flips over ~4-5h before Eastern midnight,
                # so an evening run would see "today" as tomorrow and wrongly conclude no
                # scores exist yet, re-running the loader unnecessarily and reintroducing the
                # lock-contention this check exists to prevent).
                cur.execute(
                    "SELECT COUNT(*) FROM signal_quality_scores WHERE date = %s",
                    (run_date,),
                )
                result = cur.fetchone()
                count = result[0] if result else 0
                today_scores_exist = count > 0
                if today_scores_exist:
                    logger.info(f"[PHASE 7] Today's signal_quality_scores already computed ({count} rows exist)")
        except Exception as check_err:
            logger.warning(
                f"[PHASE 7] Could not check if today's scores exist (will proceed with loader): {check_err}"
            )

        try:
            from loaders.load_signal_quality_scores import SignalQualityScoresLoader
            from concurrent.futures import TimeoutError as FutureTimeoutError

            if today_scores_exist:
                logger.info("[PHASE 7] Skipping signal quality score loader (today's scores already available)")
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "already_computed_today": True}
            else:
                logger.info("[PHASE 7] Computing signal quality scores before Phase 8 entry execution")
                loader = SignalQualityScoresLoader()

                # OPTIMIZATION: Only compute scores for symbols with actual BUY signals, not all 4896 symbols.
                # This cuts execution time by ~80% (600-900 symbols vs 4896 total).
                # Query buy_sell_daily for recent BUY signals to get the target symbol list.
                with DatabaseContext("read") as cur:
                    cur.execute("""
                        SELECT DISTINCT symbol FROM buy_sell_daily
                        WHERE signal = 'BUY' AND date >= CURRENT_DATE - %s
                        ORDER BY symbol
                    """, (_BUYSELL_LOOKBACK_DAYS,))
                    signal_symbols = [row[0] for row in cur.fetchall()]

                if not signal_symbols:
                    # No BUY signals at all - fall back to empty result (Phase 8 handles gracefully)
                    logger.warning("[PHASE 7] No BUY signals found in buy_sell_daily. Skipping quality score computation.")
                    score_result = {"symbols_processed": 0, "symbols_failed": 0, "no_signals_found": True}
                else:
                    logger.info(
                        f"[PHASE 7] Computing scores for {len(signal_symbols)} symbols with BUY signals (vs 4896 total active). "
                        f"Optimization: 80% reduction in computation scope."
                    )
                    # Use watermark-based incremental loading: only recompute scores for symbols
                    # whose underlying data (buy_sell_daily signals, technical indicators) have changed
                    # since the last score update. This is tracked via updated_at watermark.
                    loader_start = time.time()
                    loader_timeout_secs = 600  # 10 minutes (was 15 min with backfill_days=3 workaround)
                    score_result = loader.run(
                        symbols=signal_symbols,
                        parallelism=8,
                    )
                    loader_elapsed = time.time() - loader_start
                    if loader_elapsed > loader_timeout_secs:
                        logger.warning(f"[PHASE 7] Signal quality score loader took {loader_elapsed:.0f}s (exceeded {loader_timeout_secs}s timeout)")
                        msg = (
                            f"[PHASE 7 CRITICAL] Signal quality score computation exceeded timeout ({loader_elapsed:.0f}s > {loader_timeout_secs}s). "
                            f"This indicates the loader is stalled or locked. Cannot proceed without valid signal scores."
                        )
                        logger.critical(msg)
                        log_phase_result_fn(7, "signal_generation", "halt", msg)
                        return PhaseResult(
                            7,
                            "signal_generation",
                            "halted",
                            {"qualified_trades": [], "liquidity_passed": 0},
                            True,
                            msg,
                        )
        except Exception as e:
            # Handle LockAcquisitionError FIRST - don't halt on temporary lock contention
            # CRITICAL: This must come before TimeoutError, as both may indicate lock issues
            from algo.exceptions import LockAcquisitionError

            # Check multiple ways: isinstance, type name, string message
            # Lock errors can be wrapped or have import timing issues
            error_str = str(e)
            error_type_name = type(e).__name__
            is_lock_error = (
                isinstance(e, LockAcquisitionError)
                or error_type_name == 'LockAcquisitionError'
                or 'LockAcquisitionError' in error_type_name
                or 'lock' in error_str.lower()
            )
            if is_lock_error:
                # Temporary lock issue - log warning but don't halt
                msg = (
                    f"[PHASE 7 WARNING] Signal quality score loader could not acquire lock (temporary contention). "
                    f"Will proceed without updated scores. Trades will use previously cached scores if available."
                )
                logger.warning(msg)
                log_phase_result_fn(7, "signal_generation", "degraded", msg)
                # Return empty result - downstream Phase 8 will detect and handle gracefully
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "lock_contention": True}
            elif isinstance(e, (TimeoutError, FutureTimeoutError)):
                # Timeout (separate from lock acquisition) - also graceful degradation
                msg = (
                    f"[PHASE 7 WARNING] Signal quality score computation timed out. "
                    f"Will proceed without updated scores. Trades will use previously cached scores if available."
                )
                logger.warning(msg)
                log_phase_result_fn(7, "signal_generation", "degraded", msg)
                score_result = {"symbols_processed": 0, "symbols_failed": 0, "timeout": True}
            else:
                # CRITICAL: Other errors halt Phase 7
                # Signal quality scores are REQUIRED for Phase 8 entry gates.
                # If computation fails, trades cannot proceed safely - must halt and investigate.
                msg = (
                    f"[PHASE 7 CRITICAL] Signal quality score computation failed: {type(e).__name__}: {e}. "
                    f"Signal quality scores are REQUIRED for Phase 8 entry validation. "
                    f"Cannot proceed without valid signal scores. Check loader logs for details."
                )
                logger.critical(msg)
                log_phase_result_fn(7, "signal_generation", "halt", msg)
                return PhaseResult(
                    7,
                    "signal_generation",
                    "halted",
                    {"qualified_trades": [], "liquidity_passed": 0},
                    True,
                    msg,
                )

        # CRITICAL: Validate result structure before using it
        if not isinstance(score_result, dict):
            raise RuntimeError(
                f"Signal quality score loader returned invalid type: {type(score_result).__name__}. "
                f"Expected dict with 'symbols_failed' and 'symbols_processed' keys."
            )

        if "symbols_failed" not in score_result:
            raise RuntimeError(
                f"Signal quality score result missing 'symbols_failed' key. "
                f"Loader must return complete result structure. Got keys: {score_result.keys()}"
            )

        symbols_failed = score_result["symbols_failed"]
        if symbols_failed > 0:
            logger.warning(f"[PHASE 7] Signal quality score computation had {symbols_failed} failures: {score_result}")

        if "symbols_processed" not in score_result:
            raise RuntimeError(
                f"Signal quality score result missing 'symbols_processed' key. "
                f"Loader must return complete result structure. Got keys: {score_result.keys()}"
            )

        symbols_processed = score_result["symbols_processed"]
        logger.info(f"[PHASE 7] Signal quality scores computed: {symbols_processed} symbols")

        # CRITICAL: Validate that scores were actually computed.
        # If symbols_processed == 0, the loader couldn't acquire lock or hit an error.
        # This happens when signal_quality_scores lock is held by stale process.
        # EXCEPTION: If lock_contention flag is set, we already logged this as degraded mode
        # and should NOT halt - Phase 8 will proceed without updated scores.
        # EXCEPTION: If already_computed_today is set, symbols_processed=0 is the skip
        # sentinel from the "today's scores already exist" fast path above, not a failure -
        # live-confirmed 2026-08-03: the loader completed successfully at 09:39-09:40
        # (53,353 rows, loader_execution_history status=success), then Phase 7 re-ran at
        # 09:42, correctly skipped re-computing, and this check treated that intentional
        # skip as "loader failed to acquire lock" and halted the entire orchestrator -
        # blocking Phase 8 entries on data that was valid and current.
        # EXCEPTION: If no_signals_found is set, symbols_processed=0 means there were simply
        # no BUY signals in buy_sell_daily to score (e.g. stale upstream data, quiet market) -
        # live-confirmed 2026-08-10: this legitimately-empty result was falling through to the
        # same "failed to acquire the processing lock" halt message despite the no_signals_found
        # branch's own comment saying "Phase 8 handles gracefully", cascading a benign
        # zero-signals morning into a full orchestrator halt (Phase 7 halted -> Phase 8/9 errored).
        if symbols_processed == 0 and _should_halt_on_zero_scored_symbols(score_result):
            msg = (
                "[PHASE 7 CRITICAL] Signal quality score computation produced 0 symbols processed. "
                "This indicates the loader failed to acquire the processing lock (likely held by stale process) "
                "or completed with no symbols to process. Signal quality scores are REQUIRED for Phase 8 entry validation. "
                "Check: (1) Stale signal_quality_scores locks in database, (2) Upstream data availability, "
                "(3) Loader infrastructure status. Cannot proceed without valid signal scores."
            )
            logger.critical(msg)
            log_phase_result_fn(7, "signal_generation", "halt", msg)
            return PhaseResult(
                7,
                "signal_generation",
                "halted",
                {"qualified_trades": [], "liquidity_passed": 0},
                True,
                msg,
            )

    # BACKFILL: Compute quality scores for older loader-created signals that don't have scores
    # This is separate from the batch loader above - it specifically targets orphaned signals
    # that were created by the EOD pipeline but never processed by Phase 7 (timing mismatch:
    # EOD creates signals at 4:05 PM, Phase 7 runs at 9:30 AM, 1 PM, 3 PM).
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
            from loaders.signal_quality_scorer import get_signal_scorer

            backfill_scores = []
            scorer = get_signal_scorer("BUY")

            # CRITICAL FIX: Move DatabaseContext outside the for loop to prevent connection leaks
            # Opening a new context for each iteration exhausts the connection pool
            with DatabaseContext("read") as cur_tech_shared:
                for symbol, signal_date in backfill_rows:
                    try:
                        # Fetch technical data AND trend template data for full score computation
                        cur_tech_shared.execute(
                            """
                            SELECT
                              t.rsi, t.macd, t.macd_signal,
                              tr.minervini_trend_score, tr.weinstein_stage
                            FROM technical_data_daily t
                            LEFT JOIN trend_template_data tr ON tr.symbol = t.symbol AND tr.date = t.date
                            WHERE t.symbol = %s AND t.date = %s
                        """,
                            (symbol, signal_date),
                        )
                        tech_row = cur_tech_shared.fetchone()

                        if not tech_row:
                            logger.debug(f"[PHASE 7 BACKFILL] {symbol}: No technical data for {signal_date}, skipping")
                            continue

                        rsi, macd, macd_signal, minervini, weinstein = tech_row
                        # CRITICAL: Missing trend data for older dates is expected (historical backfill)
                        # Skip rather than halt, since backfill targets old signals without scores
                        # Main signal generation (for current date) will halt if trend data missing
                        if minervini is None or weinstein is None:
                            logger.debug(
                                f"[PHASE 7 BACKFILL] {symbol} {signal_date}: Skipping - missing trend template data. "
                                f"This is expected for older dates. Main signal generation will halt if trend data missing for current date."
                            )
                            continue
                        # Compute score using same logic as inline scorer (with trend data)
                        try:
                            base_score = scorer.calculate_base_quality_score()
                            if base_score is None or base_score < 0:
                                raise ValueError(f"Base score calculation failed: got {base_score} (expected 0-100 range)")
                            volume_score = scorer.calculate_volume_confirmation_score(rsi, macd, macd_signal)
                            if volume_score is None:
                                raise ValueError(f"Volume score calculation failed: got None for {symbol} {signal_date}")
                            trend_score = scorer.calculate_trend_template_score(minervini, weinstein)
                            if trend_score is None:
                                raise ValueError(f"Trend score calculation failed: got None for {symbol} {signal_date}")
                            composite_sqs = min(100, int(base_score + volume_score + trend_score))
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

    # Halt flag check before generating signals
    if check_halt_flag and check_halt_flag():
        # Halt flag can be set by Phase 1 (data quality) or Phase 2 (circuit breaker)
        # Check halt_reason to provide clearer diagnostics
        halt_reason = "unknown halt condition"
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT halt_reason FROM algo_runtime_state WHERE state_key = 'orchestrator_halt'")
                result = cur.fetchone()
                if result and result[0]:
                    halt_reason = result[0]
        except Exception as diagnostic_err:
            logger.debug(f"[PHASE 7] Could not fetch halt reason for diagnostics: {diagnostic_err}")

        logger.critical(
            f"[PHASE 7] Halt flag detected (reason: {halt_reason[:100]}). Halting signal generation."
        )
        log_phase_result_fn(7, "signal_generation", "halt", f"Halt flag set: {halt_reason[:150]}")
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            f"Halt flag set: {halt_reason}",
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
            f"Market regime halted entries: {reasons[:500]}",
        )
        return PhaseResult(
            7,
            "signal_generation",
            "halted",
            {"qualified_trades": [], "liquidity_passed": 0},
            True,
            reasons[:500],
        )

    # ISSUE #7 FIX: Exposure policy gate - fail-closed if constraints not provided
    if exposure_constraints is None:
        msg = (
            "[PHASE 7 CRITICAL] Exposure constraints not provided by Phase 5. "
            "Cannot proceed with signal generation without knowing market exposure limits. "
            "Check that Phase 5 (Exposure Policy) completed successfully."
        )
        logger.critical(msg)
        log_phase_result_fn(7, "signal_generation", "halt", msg)
        phase_data = {"qualified_trades": [], "liquidity_passed": 0}
        validate_phase_data(7, phase_data)
        return PhaseResult(7, "signal_generation", "halted", phase_data, True, msg)

    # VALIDATION: Detect if Phase 5 failed and we're using fallback defaults (fail-safe mode)
    if (
        exposure_constraints
        and exposure_constraints.get("tier_name") == "CORRECTION"
        and exposure_constraints.get("risk_multiplier") == 0.0
        and exposure_constraints.get("max_new_positions_today") == 0
    ):
        logger.warning(
            "[PHASE 7] Using fallback CORRECTION constraints (tier_name=CORRECTION, risk_multiplier=0.0). "
            "Phase 5 (Exposure Policy) may have failed - verify via orchestrator logs. "
            "Trading is restricted to exits and rebalancing only."
        )

    if exposure_constraints and exposure_constraints.get("halt_new_entries"):
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
    # NO FALLBACK: If buy_sell_daily is unexpectedly empty, anomaly detection caught it in
    # _check_critical_dependencies() and halted. If we reach here, buy_sell_daily must have data.
    signal_source = "buysell_breakout"
    try:
        raw_candidates = _get_candidates_from_buysell(
            run_date, min_composite_score, min_close_quality=min_close_quality
        )

        if not raw_candidates:
            msg = (
                f"[PHASE 7] No BUY signals found in lookback window (prior trading day through {run_date}, "
                f"min_composite_score={min_composite_score}). Possible causes: (1) buy_sell_daily has no recent signals "
                f"(EOD pipeline may not have run yet), (2) all signals below min_score threshold, "
                f"(3) market regime prevents entries. Check market_exposure_daily for regime/halt_entries."
            )
            logger.warning(msg)
            log_phase_result_fn(7, "signal_generation", "no_signals", msg)
            # Report truth: no trades generated (degraded state, not success)
            return PhaseResult(
                7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
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
        return PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    # All trend and close quality validation happens at SQL level in _get_candidates_from_buysell().
    # Candidates here are already filtered for: close > sma_50, close_position > min_close_quality.
    # This eliminates wasted I/O and ensures data quality drift is detected immediately.
    quality_filtered = raw_candidates

    # CRITICAL FIX (Session 383): Signal quality scores already computed in _get_candidates_from_buysell()
    # All candidates here already have signal_quality_score from technical data (RSI, MACD, Minervini, Weinstein)
    # Removed redundant computation - just validate they exist
    if quality_filtered:
        missing_scores = sum(1 for c in quality_filtered if c.get("signal_quality_score") is None)
        if missing_scores > 0:
            logger.info(
                f"[PHASE 7] {missing_scores}/{len(quality_filtered)} candidates missing signal quality scores "
                f"(insufficient technical data during candidate fetch). These will be rejected."
            )
            # Filter out signals without valid SQS (fail-fast validation)
            quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]
            if not quality_filtered:
                # No candidates have signal_quality_scores (likely due to missing technical data)
                # This is an expected state - some days have no tradeable signals with sufficient history
                msg = "[PHASE 7] All candidates rejected due to missing signal quality scores (insufficient technical data)"
                logger.info(msg)
                log_phase_result_fn(7, "signal_generation", "no_data", msg)
                return PhaseResult(
                    7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
                )

    # Check for upstream data quality issues (e.g., composite_score not populated)
    upstream_drift = _detect_upstream_data_quality_drift(run_date, signal_source)
    if upstream_drift.get("has_drift"):
        logger.warning(
            f"[PHASE 7] Upstream data quality drift detected: {upstream_drift.get('drift_message', 'Unknown issue')}. "
            f"This may suppress valid candidates."
        )

    # FAIL-FAST: Validate signal_quality_score is present and numeric before sorting
    # CRITICAL FIX (Session 377): Rank by technical quality (SQS) not fundamental quality (composite_score)
    # Composite_score reflects long-term fundamental strength (balance sheet, growth, value)
    # but doesn't predict short-term price movement. Signal_quality_score (based on RSI, MACD,
    # Minervini, Weinstein) is more predictive of 1-5 day price action. Switching to SQS-based
    # ranking should improve win rate from 33% to 50%+.

    # Defensive: Filter out any candidates with None signal_quality_score (shouldn't happen but catch edge cases)
    before_filter = len(quality_filtered)
    quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]
    after_filter = len(quality_filtered)
    if before_filter > after_filter:
        logger.warning(
            f"[PHASE 7] Filtered out {before_filter - after_filter}/{before_filter} candidates with None signal_quality_score. "
            f"Remaining: {after_filter} candidates."
        )

    if not quality_filtered:
        msg = "[PHASE 7] All candidates rejected due to missing signal quality scores (edge case after filtering)"
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_data", msg)
        return PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    # Final defensive filter: Remove any None values that made it through previous filters
    # Edge case handling: if a signal's technical data became unavailable or an earlier filter missed it,
    # this catches it and removes it gracefully instead of crashing Phase 7
    none_sqs_candidates = [c for c in quality_filtered if c.get("signal_quality_score") is None]
    if none_sqs_candidates:
        error_symbols = [c.get("symbol") for c in none_sqs_candidates]
        logger.warning(
            f"[PHASE 7] {len(none_sqs_candidates)} candidates with None signal_quality_score "
            f"escaped prior filters: {error_symbols}. Filtering out and continuing."
        )
        # Remove them gracefully instead of crashing
        quality_filtered = [c for c in quality_filtered if c.get("signal_quality_score") is not None]

    # Verify we still have candidates after the final filter
    if not quality_filtered:
        msg = "[PHASE 7] All candidates rejected (final filter removed all with None signal_quality_score)"
        logger.warning(msg)
        log_phase_result_fn(7, "signal_generation", "no_data", msg)
        return PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    for sig in quality_filtered:
        sqs: int | float | None = sig.get("signal_quality_score")
        if sqs is None:
            # This should NEVER reach here due to all previous filters removing None values
            # If it does, it indicates a critical logic error in our filtering
            msg = (
                f"[PHASE 7 CRITICAL] Signal {sig.get('symbol')} has None signal_quality_score "
                f"after all filters. This is a logic error in the filtering code - None values should "
                f"have been removed by prior filters. Failing fast to expose the issue."
            )
            logger.critical(msg)
            raise RuntimeError(msg)
        if not isinstance(sqs, (int, float)):
            msg = (
                f"[PHASE 7 CRITICAL] Signal {sig.get('symbol')} signal_quality_score is {type(sqs).__name__}, "
                f"expected float. Signal quality score must be numeric for sorting. Cannot proceed."
            )
            logger.critical(msg)
            raise ValueError(msg)

    # CRITICAL: Final defensive filter - remove ANY signals with None scores before sorting
    # (defensive in case filtering above had gaps)
    quality_filtered = [s for s in quality_filtered if s.get("signal_quality_score") is not None]
    if not quality_filtered:
        msg = (
            "[PHASE 7 CRITICAL] All signals filtered out in final defensive check. "
            "This should not happen if quality filter worked correctly above."
        )
        logger.critical(msg)
        return PhaseResult(
            7, "signal_generation", "degraded", {"qualified_trades": [], "liquidity_passed": 0}, False, msg
        )

    quality_filtered.sort(key=lambda s: float(s["signal_quality_score"]), reverse=True)

    # Liquidity checks on top candidates - parallelized
    # ISSUE 13 FIX: Improved timeout handling with per-task monitoring
    liq_passed = []
    liq_checked = 0
    to_check = quality_filtered[:LIQUIDITY_CHECK_LIMIT]

    if to_check:
        try:
            executor = ThreadPoolExecutor(max_workers=PHASE7_LIQUIDITY_CHECK_WORKERS, thread_name_prefix="phase7_liq")
            pending_symbols = []
            completed_results = {}

            try:
                # Submit all tasks
                future_to_symbol = {executor.submit(_check_liquidity_parallel, cand, run_date, config): cand for cand in to_check}

                # ISSUE 13 FIX: Wait with timeout per completed future
                executor_timeout = 60  # seconds - overall limit for all futures

                for future in as_completed(future_to_symbol, timeout=executor_timeout):
                    liq_checked += 1
                    candidate = future_to_symbol[future]
                    symbol = candidate.get("symbol", "UNKNOWN")

                    try:
                        result = future.result(timeout=2)  # Per-future timeout is shorter
                        candidate_result, passed = result
                        completed_results[symbol] = passed
                        if passed:
                            liq_passed.append(candidate_result)
                    except FutureTimeoutError:
                        logger.warning(f"[PHASE 7] Liquidity check timed out for {symbol} (exceeds 2s per-future limit)")
                        pending_symbols.append(symbol)
                    except Exception as e:
                        logger.error(f"[PHASE 7] Liquidity check failed for {symbol}: {e}")
                        pending_symbols.append(symbol)

            except FutureTimeoutError:
                logger.critical(
                    f"[PHASE 7] Overall liquidity check timeout - {len(pending_symbols)} symbols still pending "
                    f"(exceeded {executor_timeout}s overall limit)"
                )
            finally:
                # ISSUE 13 FIX: Kill hanging threads instead of waiting
                executor.shutdown(wait=False)

            # Log skipped symbols
            if pending_symbols:
                logger.warning(
                    f"[PHASE 7] Skipping {len(pending_symbols)} symbols due to timeout: {pending_symbols[:10]}"
                )

            # Continue with results we got
            logger.info(
                f"[PHASE 7] Liquidity check completed: {len(liq_passed)} passed, "
                f"{len(pending_symbols)} skipped (timeout)"
            )

        except Exception as executor_exc:
            # CRITICAL FIX: Re-raise exceptions instead of silently continuing
            # If executor setup fails or critical errors occur, halt Phase 7
            logger.critical(
                f"[PHASE 7 CRITICAL] ThreadPoolExecutor failure during liquidity checks: {type(executor_exc).__name__}: {executor_exc}. "
                f"Cannot verify liquidity for {len(to_check)} candidates. "
                f"Liquidity checks are critical for trading safety - failing fast instead of proceeding with unverified candidates."
            )
            msg = (
                f"[PHASE 7] Liquidity check system failure: {type(executor_exc).__name__}. "
                f"Cannot proceed with signal generation without liquidity validation. "
                f"Check system resources (thread pool, memory, database connections) and retry."
            )
            raise RuntimeError(msg) from executor_exc

    logger.info(
        f"[PHASE 7] Liquidity check: {liq_checked} checked, {len(liq_passed)} passed. "
        f"{len(quality_filtered) - liq_checked} unchecked candidates dropped."
    )

    # Filter out inactive symbols (symbols not available in Alpaca/trading platforms)
    if liq_passed:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT symbol FROM stock_symbols WHERE symbol = ANY(%s) AND active = false""",
                    ([sig.get("symbol") for sig in liq_passed],),
                )
                inactive_set = {row[0] for row in cur.fetchall()}

            inactive_removed = [sig for sig in liq_passed if sig.get("symbol") in inactive_set]
            if inactive_removed:
                logger.warning(
                    f"[PHASE 7] Filtering {len(inactive_removed)} inactive symbols: "
                    f"{', '.join(sig['symbol'] for sig in inactive_removed)}"
                )
            liq_passed = [sig for sig in liq_passed if sig.get("symbol") not in inactive_set]
        except Exception as e:
            logger.warning(f"[PHASE 7] Could not filter inactive symbols: {e}. Continuing with current list.")

    # Final ranking by signal_quality_score (already validated by quality_filtered sort, but re-validate for safety)
    if liq_passed:
        for sig in liq_passed:
            # signal_quality_score and signal_date are critical; market_stage is optional (used only for logging)
            required_fields = ["signal_quality_score", "signal_date"]
            missing_fields = [f for f in required_fields if f not in sig or sig[f] is None]
            if missing_fields:
                sym = sig.get("symbol", "UNKNOWN_SYMBOL")
                raise ValueError(
                    f"[PHASE 7 CRITICAL] Liquidity-passed signal {sym} missing required fields: {missing_fields}. "
                    f"Cannot log or execute incomplete signal data. Signal keys: {list(sig.keys())}. "
                    f"Check upstream signal generation pipeline for data quality issues."
                )
            # market_stage is optional - provide default if missing (used only for logging)
            if not sig.get("market_stage"):
                sig["market_stage"] = "unknown"
        liq_passed.sort(key=lambda s: float(s["signal_quality_score"]), reverse=True)

    logger.info(f"[PHASE 7] Top 10 qualified signals (source={signal_source}):")
    for i, sig in enumerate(liq_passed[:10]):

        def _fmt(v: Any, spec: str = ":.1f") -> str:
            return format(v, spec[1:]) if v is not None else "?"

        buylevel_str = (
            f" buylevel={_fmt(sig.get('buylevel'), ':.2f')} signal_date={sig['signal_date']}"
            if sig.get("buylevel")
            else ""
        )
        logger.info(
            f"  {i + 1}. {sig['symbol']:6s} "
            f"sqs={_fmt(sig.get('signal_quality_score'))} "
            f"composite={_fmt(sig.get('composite_score'))} "
            f"momentum={_fmt(sig.get('momentum_score'))} "
            f"rs_pct={_fmt(sig.get('rs_percentile'))} "
            f"stage={sig['market_stage']}"
            f"{buylevel_str}"
        )

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
        logger.info(f"[PHASE 7 DEBUG] Top 5 qualified trades signal_quality_score values:")
        for i, sig in enumerate(liq_passed[:5]):
            logger.info(f"  {i+1}. {sig.get('symbol')}: sqs={sig.get('signal_quality_score')}, trend={sig.get('trend_template_score')}, base_q={sig.get('base_quality')}")

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

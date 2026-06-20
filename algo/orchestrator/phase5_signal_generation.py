#!/usr/bin/env python3
"""
PHASE 5: SIGNAL GENERATION

Primary path: buy_sell_daily pivot-breakout BUY signals filtered by stock_scores ranking.
Fallback path: stock_scores + price_daily only (when buy_sell_daily has no fresh data).

Pipeline:
1. Check halt flag (data freshness gate)
2. Check market regime: halt if entries not allowed per market_exposure_daily
3. Fetch candidates (primary): buy_sell_daily BUY signals within last 3 days
   joined to stock_scores (composite ranking) + price_daily (current prices + SMA_50)
   Fallback: stock_scores with composite_score >= threshold + price_daily
4. Filter: close > sma_50 (uptrend confirmation)
5. Filter: composite_score >= min threshold
6. Close quality gate: skip weak closes (bottom of day's range = distribution)
7. Liquidity checks on top _LIQUIDITY_CHECK_LIMIT candidates
8. Return composite-score-ranked candidates to Phase 6

Ranking: composite_score from stock_scores (quality 25%, growth 20%, value 20%,
positioning 15%, stability 12%, momentum 8%).

Signal source priority:
  buy_sell_daily (breakout timing gate) → stock_scores (quality ranking)
  Fallback: stock_scores only when buy_sell_daily has no fresh BUY signals
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date
from datetime import timedelta
from typing import Callable, Dict, List, Optional, Tuple

from algo.orchestrator.phase_result import PhaseResult
from algo.risk import LiquidityChecks
from config.thresholds import ThresholdConfig
from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)

_LIQUIDITY_CHECK_LIMIT = 10
_MAX_WORKERS = 4
_MIN_COMPOSITE_SCORE = 50  # Minimum composite_score to qualify (0–100 scale)
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


def _validate_signal_completeness(candidates: List[Dict], source: str) -> Tuple[List[Dict], int]:
    """ISSUE #8 FIX: Filter signals with missing required fields for Phase 6.

    Logs each incomplete signal explicitly (so operators see what was excluded).
    Returns (complete_signals, incomplete_count).

    This prevents silent skips by providing upstream alerts when signals are filtered
    due to incomplete data.
    """
    complete_signals = []
    incomplete_count = 0

    for sig in candidates:
        symbol = sig.get("symbol", "UNKNOWN")
        missing_fields = []
        for field_name, field_type in _REQUIRED_SIGNAL_FIELDS.items():
            val = sig.get(field_name)
            if val is None:
                missing_fields.append(field_name)

        if missing_fields:
            incomplete_count += 1
            logger.warning(
                f"[PHASE 5] {symbol}: incomplete signal data — filtering from candidates "
                f"(missing: {', '.join(missing_fields)}). Source={source}"
            )
        else:
            complete_signals.append(sig)

    if incomplete_count > 0:
        logger.info(
            f"[PHASE 5] Signal completeness validation ({source}): "
            f"{incomplete_count} incomplete signals filtered, {len(complete_signals)} complete signals retained"
        )

    return complete_signals, incomplete_count


def _check_market_regime(run_date: _date) -> Dict:
    """Return current market regime from market_exposure_daily."""

    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT is_entry_allowed, exposure_pct, regime, halt_reasons
                FROM market_exposure_daily
                WHERE date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (run_date,),
            )
            row = cur.fetchone()
            if row is None:
                logger.warning(
                    "[PHASE 5] No market_exposure_daily data — halting entries (fail-closed)"
                )
                return {
                    "is_entry_allowed": False,
                    "exposure_pct": 0,
                    "regime": "unknown",
                    "halt_reasons": ["No market regime data available"],
                }
            import json

            if row[1] is None:
                logger.critical(
                    "[PHASE 5] market_exposure_daily exposure_pct is NULL — halting entries (fail-closed)"
                )
                return {
                    "is_entry_allowed": False,
                    "exposure_pct": 0,
                    "regime": "unknown",
                    "halt_reasons": ["Market exposure_pct is NULL — cannot proceed with regime-aware sizing"],
                }

            halt_reasons = json.loads(row[3]) if row[3] else []
            return {
                "is_entry_allowed": bool(row[0]),
                "exposure_pct": float(row[1]),
                "regime": row[2] or "unknown",
                "halt_reasons": halt_reasons,
            }
    except Exception as e:
        logger.warning(f"[PHASE 5] Could not read market regime: {e} — halting entries (fail-closed)")
        return {
            "is_entry_allowed": False,
            "exposure_pct": 0,
            "regime": "unknown",
            "halt_reasons": [f"Market regime read failed: {type(e).__name__}: {str(e)}"],
        }


def _detect_upstream_data_quality_drift(run_date: _date, signal_source: str) -> Dict:
    """Detect upstream data quality issues by comparing expected vs. actual swing_trader_scores coverage.

    Returns dict with: {"swing_scores_missing": count_by_symbol, "has_drift": bool, "drift_symbols": list}
    """
    drift = {"swing_scores_missing": 0, "has_drift": False, "drift_symbols": []}

    try:
        with DatabaseContext("read") as cur:
            lookback_date = run_date - timedelta(days=_BUYSELL_LOOKBACK_DAYS) if signal_source == "buysell_breakout" else None

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
    except Exception as e:
        logger.debug(f"[PHASE 5] Could not check upstream data quality: {e}")

    return drift


def _check_liquidity_parallel(candidate: Dict, run_date: _date) -> Tuple[Dict, bool]:
    """Check liquidity for a single candidate. Returns (candidate, passed)."""
    try:
        liquidity = LiquidityChecks(config={})
        liq_ok, liq_reason = liquidity.run_all(candidate["symbol"], 0, run_date)
        if not liq_ok:
            logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity — {liq_reason}")
        return candidate, liq_ok
    except Exception as e:
        logger.warning(
            f"[PHASE 5] {candidate['symbol']}: liquidity check error ({type(e).__name__}): {str(e)}"
        )
        return candidate, False


def _get_candidates_from_buysell(
    run_date: _date, min_score: float, limit: int = 100, min_close_quality: float = 0.3
) -> List[Dict]:
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
                (lookback_date, run_date, run_date, run_date, run_date, min_score, min_close_quality, limit),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            close = float(r[6]) if r[6] is not None else None
            composite = float(r[1]) if r[1] is not None else None
            raw_strength = float(r[14]) if r[14] is not None else None
            swing_score = float(r[18]) if r[18] is not None else 0.0
            swing_components = r[19] if r[19] is not None else None
            candidates.append({
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
                "entry_price": close,
                "signal_strength": raw_strength,
                "sector": r[10],
                "industry": r[11],
                "buylevel": float(r[12]) if r[12] is not None else None,
                "stoplevel": float(r[13]) if r[13] is not None else None,
                "volume_surge_pct": float(r[15]) if r[15] is not None else None,
                "market_stage": r[16],
                "signal_date": str(r[17]) if r[17] is not None else None,
            })

        swing_score_positive = sum(1 for c in candidates if c["swing_score"] > 0)
        logger.info(
            f"[PHASE 5] {len(candidates)} candidates from buy_sell_daily + stock_scores + swing_trader_scores "
            f"(swing_scores: {swing_score_positive}, lookback: {lookback_date} to {run_date}, "
            f"SQL filters: trend & close_quality applied at query level)"
        )

        complete_candidates, incomplete_count = _validate_signal_completeness(candidates, "buy_sell_daily path")

        return complete_candidates
    except Exception as e:
        raise RuntimeError(
            f"[PHASE 5] Failed to fetch buy_sell_daily candidates: {e}. "
            "Cannot proceed with signal generation without candidate data."
        ) from e


def _get_candidates(run_date: _date, min_score: float, limit: int = 100, min_close_quality: float = 0.3) -> List[Dict]:
    """Fallback: fetch candidates from stock_scores + swing_trader_scores with current prices.

    Used when buy_sell_daily has no fresh BUY signals (e.g., EOD loader hasn't run yet).
    Returns symbols ranked by swing_score (if available) or composite_score — no breakout confirmation,
    just uptrend + quality + swing trading factors.

    ISSUE #3 FIX: All validation filters (swing_score, trend, close quality) moved to SQL WHERE clauses
    for efficiency and to detect upstream data quality drift immediately.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SET LOCAL statement_timeout = '15000ms'")
            cur.execute(
                """
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
                    cp.sector,
                    cp.industry,
                    sts.score AS swing_score,
                    sts.components AS swing_components
                FROM stock_scores ss
                INNER JOIN swing_trader_scores sts ON sts.symbol = ss.symbol
                    AND sts.date <= %s AND sts.score IS NOT NULL
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
                LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                WHERE ss.composite_score >= %s
                  AND p.close > sma.avg_close
                  AND p.high > p.low
                  AND ((p.close - p.low) / (p.high - p.low)) > %s
                ORDER BY sts.score DESC, ss.composite_score DESC
                LIMIT %s
                """,
                (run_date, run_date, run_date, min_score, min_close_quality, limit),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            close = float(r[6]) if r[6] is not None else None
            swing_score = float(r[12]) if r[12] is not None else 0.0
            swing_components = r[13] if r[13] is not None else None
            candidates.append({
                "symbol": r[0],
                "composite_score": float(r[1]) if r[1] is not None else None,
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
                "entry_price": close,
                "signal_strength": None,
                "sector": r[10],
                "industry": r[11],
            })

        swing_score_positive = sum(1 for c in candidates if c["swing_score"] > 0)
        logger.info(
            f"[PHASE 5] {len(candidates)} candidates from stock_scores + swing_trader_scores + price_daily "
            f"(swing_scores: {swing_score_positive}, SQL filters: trend & close_quality applied at query level)"
        )

        complete_candidates, incomplete_count = _validate_signal_completeness(candidates, "stock_scores fallback path")

        return complete_candidates
    except Exception as e:
        raise RuntimeError(
            f"[PHASE 5] Failed to fetch candidates: {e}. "
            "Cannot proceed with signal generation without candidate data."
        ) from e


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: Optional[Dict] = None,
    check_halt_flag: Optional[Callable] = None,
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
        config.get("phase5_min_composite_score", _MIN_COMPOSITE_SCORE)
        if config else _MIN_COMPOSITE_SCORE
    )

    # Halt flag check before generating signals
    if check_halt_flag and check_halt_flag():
        logger.critical(
            "[PHASE 5] Halt flag set by Phase 1 — data quality degradation detected. Halting signal generation."
        )
        log_phase_result_fn(5, "signal_generation", "halt", "Halt flag set: data quality degradation")
        return PhaseResult(
            5, "signal_generation", "halted", {"qualified_trades": []}, True,
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
        return PhaseResult(
            5, "signal_generation", "halted", {"qualified_trades": []}, True, reasons[:100]
        )

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
    raw_candidates = _get_candidates_from_buysell(run_date, min_composite_score, min_close_quality=min_close_quality)
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
            futures = {
                executor.submit(_check_liquidity_parallel, cand, run_date): cand
                for cand in to_check
            }
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
            f" buylevel={_fmt(sig.get('buylevel'), ':.2f')}"
            f" signal_date={sig.get('signal_date', '?')}"
            if sig.get("buylevel") else ""
        )
        logger.info(
            f"  {i+1}. {sig['symbol']:6s} "
            f"composite={_fmt(sig.get('composite_score'))} "
            f"quality={_fmt(sig.get('quality_score'))} "
            f"momentum={_fmt(sig.get('momentum_score'))} "
            f"rs_pct={_fmt(sig.get('rs_percentile'))} "
            f"stage={sig.get('market_stage', '?')}"
            f"{buylevel_str}"
        )

    elapsed = time.time() - phase_start
    log_phase_result_fn(
        5, "signal_generation", "success",
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

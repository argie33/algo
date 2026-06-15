#!/usr/bin/env python3
"""
PHASE 5: SIGNAL GENERATION

Generates candidate signals on-the-fly from stock_scores + price_daily.
buy_sell_daily was removed from the EOD pipeline; Phase 5 now queries live data.

Pipeline:
1. Check halt flag (data freshness gate)
2. Check market regime: halt if entries not allowed per market_exposure_daily
3. Fetch candidates: stock_scores (composite ranking) + price_daily (latest prices + SMA_50)
4. Filter: close > sma_50 (price must be in uptrend above 50-day MA)
5. Filter: composite_score >= min threshold
6. Close quality gate: skip weak closes (bottom of day's range = distribution)
7. Liquidity checks on top _LIQUIDITY_CHECK_LIMIT candidates
8. Return composite-score-ranked candidates to Phase 6

Ranking: composite_score from stock_scores (quality 25%, growth 20%, value 20%,
positioning 15%, stability 12%, momentum 8%).
"""

import logging
import time
from datetime import date as _date
from typing import Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.db.context import DatabaseContext
from algo.risk import LiquidityChecks
from algo.orchestrator.phase_result import PhaseResult
from config.thresholds import ThresholdConfig

logger = logging.getLogger(__name__)

_LIQUIDITY_CHECK_LIMIT = 10
_MAX_WORKERS = 4
_MIN_COMPOSITE_SCORE = 50  # Minimum composite_score to qualify (0–100 scale)


def _check_market_regime(run_date: _date) -> Dict:
    """Return current market regime from market_exposure_daily."""
    import os

    bypass_regime = os.getenv("BYPASS_MARKET_REGIME", "").lower() in ("true", "1", "yes")
    if bypass_regime:
        logger.critical(
            "[PATH_B] BYPASS_MARKET_REGIME=true — forcing is_entry_allowed=True"
        )
        return {
            "is_entry_allowed": True,
            "exposure_pct": 100,
            "regime": "proof_of_concept",
            "halt_reasons": [],
        }

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
                    "[PHASE 5] No market_exposure_daily data — proceeding with default permissive regime"
                )
                return {
                    "is_entry_allowed": True,
                    "exposure_pct": 50,
                    "regime": "unknown",
                    "halt_reasons": [],
                }
            import json

            halt_reasons = json.loads(row[3]) if row[3] else []
            return {
                "is_entry_allowed": bool(row[0]),
                "exposure_pct": float(row[1]) if row[1] is not None else 50,
                "regime": row[2] or "unknown",
                "halt_reasons": halt_reasons,
            }
    except Exception as e:
        logger.warning(f"[PHASE 5] Could not read market regime: {e} — proceeding permissively")
        return {
            "is_entry_allowed": True,
            "exposure_pct": 50,
            "regime": "unknown",
            "halt_reasons": [],
        }


def _check_liquidity_parallel(candidate: Dict, run_date: _date) -> Tuple[Dict, bool]:
    """Check liquidity for a single candidate. Returns (candidate, passed)."""
    try:
        liquidity = LiquidityChecks(config={})
        liq_ok, liq_reason = liquidity.run_all(candidate["symbol"], 0, run_date)
        if not liq_ok:
            logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity — {liq_reason}")
        return candidate, liq_ok
    except Exception as e:
        logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity check error — {str(e)[:50]}")
        return candidate, False


def _get_candidates(run_date: _date, min_score: float, limit: int = 100) -> List[Dict]:
    """Fetch candidate symbols from stock_scores with current prices from price_daily.

    Computes on-the-fly: no pre-computed buy_sell_daily needed.
    Returns symbols ranked by composite_score with latest price data.
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
                    sma.avg_close AS sma_50
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
                WHERE ss.composite_score >= %s
                ORDER BY ss.composite_score DESC NULLS LAST
                LIMIT %s
                """,
                (run_date, run_date, min_score, limit),
            )
            rows = cur.fetchall()

        candidates = []
        for r in rows:
            close = float(r[6]) if r[6] is not None else None
            candidates.append({
                "symbol": r[0],
                "composite_score": float(r[1]) if r[1] is not None else None,
                "quality_score": float(r[2]) if r[2] is not None else None,
                "growth_score": float(r[3]) if r[3] is not None else None,
                "momentum_score": float(r[4]) if r[4] is not None else None,
                "rs_percentile": float(r[5]) if r[5] is not None else None,
                "close": close,
                "high": float(r[7]) if r[7] is not None else None,
                "low": float(r[8]) if r[8] is not None else None,
                "sma_50": float(r[9]) if r[9] is not None else None,
                "entry_price": close,
                "signal_strength": (float(r[1]) / 100.0) if r[1] is not None else 0.5,
            })

        logger.info(f"[PHASE 5] {len(candidates)} candidates from stock_scores + price_daily")
        return candidates
    except Exception as e:
        logger.error(f"[PHASE 5] Error fetching candidates: {e}", exc_info=True)
        return []


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
    import os

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

    # Exposure policy gate
    bypass_exposure = os.getenv("BYPASS_EXPOSURE_POLICY", "").lower() in ("true", "1", "yes")
    if exposure_constraints and exposure_constraints.get("halt_new_entries") and not bypass_exposure:
        reason = exposure_constraints.get("halt_reason", "Exposure policy halted new entries")
        logger.warning(f"[PHASE 5] {reason}")
        log_phase_result_fn(5, "signal_generation", "halt", reason)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, reason)
    elif bypass_exposure and exposure_constraints and exposure_constraints.get("halt_new_entries"):
        logger.critical("[PATH_B] BYPASS_EXPOSURE_POLICY=true — overriding exposure policy halt")

    # Fetch candidates from stock_scores + price_daily (on-the-fly, no buy_sell_daily)
    raw_candidates = _get_candidates(run_date, min_composite_score)

    if not raw_candidates:
        msg = f"No candidates in stock_scores with composite_score >= {min_composite_score} for {run_date}"
        logger.warning(f"[PHASE 5] {msg}")
        log_phase_result_fn(5, "signal_generation", "halt", msg)
        return PhaseResult(5, "signal_generation", "halted", {"qualified_trades": []}, True, msg)

    # Filter: price must be above 50-day moving average (basic uptrend requirement)
    trend_filtered = []
    trend_skipped = 0
    for sig in raw_candidates:
        close = sig.get("close")
        sma_50 = sig.get("sma_50")
        if close and sma_50 and close < sma_50:
            trend_skipped += 1
            logger.debug(f"[PHASE 5] {sig['symbol']}: close {close:.2f} < sma_50 {sma_50:.2f} — skip")
            continue
        trend_filtered.append(sig)

    logger.info(
        f"[PHASE 5] Trend filter (close > SMA50): {len(trend_filtered)} passed, {trend_skipped} skipped"
    )

    # composite_score already populated from stock_scores in _get_candidates
    score_filtered = trend_filtered

    # Close quality gate: skip if close is in bottom of day's range (distribution signal)
    quality_filtered = []
    weak_close_count = 0
    for sig in score_filtered:
        close = sig.get("close")
        high = sig.get("high")
        low = sig.get("low")
        if high and low and close and high > low:
            close_position = (close - low) / (high - low)
            if close_position < min_close_quality:
                weak_close_count += 1
                logger.debug(
                    f"[PHASE 5] {sig['symbol']}: weak close {close_position:.0%} of range "
                    f"(threshold={min_close_quality:.0%}) — skip"
                )
                continue
        quality_filtered.append(sig)

    logger.info(
        f"[PHASE 5] Close quality gate: {len(quality_filtered)} passed, {weak_close_count} weak closes skipped"
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

    logger.info("[PHASE 5] Top 10 qualified signals:")
    for i, sig in enumerate(liq_passed[:10]):
        def _fmt(v, spec=":.1f"):
            return format(v, spec[1:]) if v is not None else "?"
        logger.info(
            f"  {i+1}. {sig['symbol']:6s} "
            f"composite={_fmt(sig.get('composite_score'))} "
            f"quality={_fmt(sig.get('quality_score'))} "
            f"momentum={_fmt(sig.get('momentum_score'))} "
            f"rs_pct={_fmt(sig.get('rs_percentile'))} "
            f"strength={_fmt(sig.get('signal_strength'), ':.2f')}"
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
            "trend_filtered": len(trend_filtered),
            "score_filtered": len(score_filtered),
            "quality_filtered": len(quality_filtered),
            "liquidity_passed": len(liq_passed),
            "regime": regime,
        },
        False,
        f"Generated {len(liq_passed)} signals in {elapsed:.1f}s",
    )

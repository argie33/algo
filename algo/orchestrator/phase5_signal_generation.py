#!/usr/bin/env python3
"""
PHASE 5: SIGNAL GENERATION

Computes signals on-the-fly from price_daily — no dependency on pre-computed
technical_data_daily or buy_sell_daily tables.

Pipeline:
1. Check market regime: halt if entries not allowed per market_exposure_daily
2. Fetch all symbols with price data for run_date
3. For each symbol, compute: Minervini trend template, Weinstein stage,
   VCP pattern, base detection, power trend
4. Hard gate: skip symbol if Minervini trend template does not pass (all 8 criteria)
5. Score quality 0-100 from remaining signals (Stage 2 only — Stage 3 is distribution)
6. Run liquidity checks on top _LIQUIDITY_CHECK_LIMIT candidates
7. Run SwingScore 7-component deep-quality ranking on top _SWING_SCORE_LIMIT
   liquidity-passed candidates; filter/re-rank by swing_score
8. Return swing-score-ranked candidates to Phase 6

Quality scoring (max 100):
  30-40  Minervini trend template (score-scaled: 5/8=30, 6/8=33, 7/8=37, 8/8=40)
     20  Weinstein Stage 2 confirmed uptrend (+5 if Stage 1 base-building)
     20  VCP (Volatility Contraction Pattern)
     15  Base detection (consolidation before breakout)
      5  Power trend (21-day return >= 20%)

Final ranking: SwingScore (7 components: setup, trend, momentum, volume,
fundamentals, sector, multi-TF). Min threshold: _MIN_SWING_SCORE (grade C).
Regime tier can impose a stricter floor via exposure_constraints['min_swing_score'].
"""

import logging
import time
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional

from utils.database_context import DatabaseContext
from algo.algo_signals import SignalComputer
from algo.algo_swing_score import SwingTraderScore
from algo.algo_liquidity_checks import LiquidityChecks
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

# Run liquidity checks on at most this many candidates (performance guard)
_LIQUIDITY_CHECK_LIMIT = 150
# Run full SwingScore on top N liquidity-passed candidates (~1-2s each)
_SWING_SCORE_LIMIT = 75
# Minimum scores to qualify
_MIN_QUALITY = 50       # Pre-swing-score quality gate
_MIN_SWING_SCORE = 35   # Grade D+ minimum (A+=85, A=75, B=65, C=55, D=45, D+=35)


def _check_market_regime(run_date: _date) -> Dict:
    """Return current market regime from market_exposure_daily.

    Returns dict with: is_entry_allowed, exposure_pct, regime, halt_reasons.
    Defaults to permissive if no data (don't block trading on missing data).
    PATH_B_OVERRIDE: If BYPASS_MARKET_REGIME is set, force is_entry_allowed=True.
    """
    import os
    bypass_regime = os.getenv('BYPASS_MARKET_REGIME', '').lower() in ('true', '1', 'yes')
    if bypass_regime:
        logger.critical("[PATH_B] BYPASS_MARKET_REGIME=true — forcing is_entry_allowed=True")
        return {'is_entry_allowed': True, 'exposure_pct': 100, 'regime': 'proof_of_concept', 'halt_reasons': []}

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT is_entry_allowed, exposure_pct, regime, halt_reasons
                FROM market_exposure_daily
                WHERE date <= %s
                ORDER BY date DESC LIMIT 1
            """, (run_date,))
            row = cur.fetchone()
            if not row:
                logger.warning("[PHASE 5] No market_exposure_daily data — proceeding with default permissive regime")
                return {'is_entry_allowed': True, 'exposure_pct': 50, 'regime': 'unknown', 'halt_reasons': []}
            import json
            halt_reasons = json.loads(row[3]) if row[3] else []
            return {
                'is_entry_allowed': bool(row[0]),
                'exposure_pct': float(row[1]) if row[1] is not None else 50,
                'regime': row[2] or 'unknown',
                'halt_reasons': halt_reasons,
            }
    except Exception as e:
        logger.warning(f"[PHASE 5] Could not read market regime: {e} — proceeding permissively")
        return {'is_entry_allowed': True, 'exposure_pct': 50, 'regime': 'unknown', 'halt_reasons': []}


def _score_signal(minervini: Dict, weinstein: Dict, vcp: Dict, base: Dict, power: Dict) -> int:
    """Compute 0-100 quality score. Returns 0 if Minervini template does not pass.

    Weinstein Stage 2 = confirmed uptrend (buy zone).
    Stage 3 = distribution/topping — never reward it.
    Stage 4 = downtrend — never reward it.
    """
    if not minervini.get('pass'):
        return 0  # Hard gate

    # Minervini 5/8→30 pts, 6/8→33, 7/8→37, 8/8→40 — differentiates marginal from ideal setups
    _minervini_pts = {5: 30, 6: 33, 7: 37, 8: 40}
    quality = _minervini_pts.get(minervini.get('score', 5), 30)

    stage = weinstein.get('stage', 0)
    if stage == 2:
        quality += 20   # Confirmed Stage 2 uptrend
    elif stage == 1:
        quality += 5    # Stage 1 base-building: potential but unconfirmed

    if vcp.get('is_vcp'):
        quality += 20

    if base.get('in_base'):
        quality += 15

    if power.get('power_trend', False):  # power_trend() key is 'power_trend', not 'power_trend_pct'
        quality += 5

    return quality


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: Dict = None,
    check_halt_flag: Callable = None,
    phase1_degraded: bool = False,
) -> PhaseResult:
    phase_start = time.time()
    logger.info("[PHASE 5] Starting signal generation")

    # Market regime gate
    regime = _check_market_regime(run_date)
    logger.info(
        f"[PHASE 5] Market regime: {regime['regime']} "
        f"exposure={regime['exposure_pct']:.0f}% "
        f"entry_allowed={regime['is_entry_allowed']}"
    )
    if not regime['is_entry_allowed']:
        reasons = '; '.join(regime['halt_reasons']) if regime['halt_reasons'] else 'no halt reasons logged'
        logger.warning(f"[PHASE 5] Entries halted by market regime: {reasons}")
        log_phase_result_fn(5, 'signal_generation', 'halt', f"Market regime halted entries: {reasons[:100]}")
        return PhaseResult(5, 'signal_generation', 'halted', {'qualified_trades': []}, True, reasons[:100])

    # Exposure policy gate
    bypass_exposure = os.getenv('BYPASS_EXPOSURE_POLICY', '').lower() in ('true', '1', 'yes')
    if exposure_constraints and exposure_constraints.get('halt_new_entries') and not bypass_exposure:
        reason = exposure_constraints.get('halt_reason', 'Exposure policy halted new entries')
        logger.warning(f"[PHASE 5] {reason}")
        log_phase_result_fn(5, 'signal_generation', 'halt', reason)
        return PhaseResult(5, 'signal_generation', 'halted', {'qualified_trades': []}, True, reason)
    elif bypass_exposure and exposure_constraints and exposure_constraints.get('halt_new_entries'):
        logger.critical("[PATH_B] BYPASS_EXPOSURE_POLICY=true — overriding exposure policy halt")

    # Verify price data coverage
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s", (run_date,))
        symbol_count = cur.fetchone()[0] or 0

    price_date = run_date
    if symbol_count < 1000:
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT date, COUNT(DISTINCT symbol) FROM price_daily "
                "GROUP BY date ORDER BY date DESC LIMIT 5"
            )
            for row in cur.fetchall():
                if row[1] >= 1000:
                    price_date = row[0]
                    symbol_count = row[1]
                    break

    if symbol_count == 0:
        log_phase_result_fn(5, 'signal_generation', 'halt', 'No price data available')
        return PhaseResult(5, 'signal_generation', 'halted', {}, True, 'No price data')

    if price_date != run_date:
        logger.info(f"[PHASE 5] run_date={run_date} has partial coverage; using price_date={price_date} ({symbol_count} symbols)")

    with DatabaseContext('read') as cur:
        cur.execute(
            "SELECT symbol, close, high, low FROM price_daily WHERE date = %s ORDER BY symbol ASC",
            (price_date,)
        )
        rows = cur.fetchall()
        symbols = [r[0] for r in rows]
        # Cache OHLC for close quality gate (free — already fetched, no extra queries)
        _ohlc = {
            r[0]: {
                'close': float(r[1]) if r[1] else None,
                'high':  float(r[2]) if r[2] else None,
                'low':   float(r[3]) if r[3] else None,
            }
            for r in rows
        }

    if not symbols:
        log_phase_result_fn(5, 'signal_generation', 'halt', 'No symbols in price_daily')
        return PhaseResult(5, 'signal_generation', 'halted', {}, True, 'No symbols found')

    logger.info(f"[PHASE 5] Generating signals for {len(symbols)} symbols (Minervini gate active)")

    signal_computer = SignalComputer()
    candidates = []
    errors = []
    minervini_pass_count = 0

    start_compute = time.time()
    for i, symbol in enumerate(symbols):
        try:
            minervini = signal_computer.minervini_trend_template(symbol, run_date)

            # Hard gate: skip immediately if Minervini template fails (saves ~5 DB queries per symbol)
            if not minervini.get('pass'):
                continue

            minervini_pass_count += 1
            weinstein = signal_computer.weinstein_stage(symbol, run_date)
            base = signal_computer.base_detection(symbol, run_date)
            vcp = signal_computer.vcp_detection(symbol, run_date)
            power = signal_computer.power_trend(symbol, run_date)

            quality = _score_signal(minervini, weinstein, vcp, base, power)

            if quality >= _MIN_QUALITY:
                # Close quality gate: stock must close in upper 40% of day's range.
                # A weak close (near day lows) on signal day indicates distribution — not a buy setup.
                ohlc = _ohlc.get(symbol, {})
                c, h, lo = ohlc.get('close'), ohlc.get('high'), ohlc.get('low')
                if h and lo and c and h > lo:
                    close_position = (c - lo) / (h - lo)
                    if close_position < 0.40:
                        logger.debug(f"[PHASE 5] {symbol}: weak close {close_position:.0%} of range — skip")
                        continue

                candidates.append({
                    'symbol': symbol,
                    'date': run_date.isoformat(),
                    'quality_score': quality,
                    'minervini_score': minervini.get('score', 0),
                    'weinstein_stage': weinstein.get('stage'),
                    'base_detected': base.get('in_base', False),
                    'vcp_pattern': vcp.get('is_vcp', False),
                    'power_trend': power.get('power_trend', False),
                    'return_21d': power.get('return_21d'),
                    'entry_price': c,  # Today's close from already-fetched OHLC
                })

            if verbose and i % 500 == 0:
                logger.debug(f"  [{i}/{len(symbols)}] processed, {minervini_pass_count} minervini passes so far")

        except Exception as e:
            errors.append(f"{symbol}: {str(e)[:50]}")

    compute_elapsed = time.time() - start_compute
    logger.info(
        f"[PHASE 5] Signal compute: {len(symbols)} symbols in {compute_elapsed:.1f}s, "
        f"{minervini_pass_count} passed Minervini gate, {len(candidates)} scored >={_MIN_QUALITY}"
    )

    # Sort by quality before liquidity checks
    candidates.sort(key=lambda s: s['quality_score'], reverse=True)

    # Liquidity checks on top candidates only (DB query per symbol — limit for performance)
    liquidity = LiquidityChecks(config={})
    liq_passed = []
    liq_checked = 0
    for candidate in candidates[:_LIQUIDITY_CHECK_LIMIT]:
        liq_ok, liq_reason = liquidity.run_all(candidate['symbol'], 0, run_date)
        liq_checked += 1
        if liq_ok:
            liq_passed.append(candidate)
        else:
            logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity — {liq_reason}")

    logger.info(
        f"[PHASE 5] Liquidity check: {liq_checked} checked, {len(liq_passed)} passed. "
        f"{len(candidates) - liq_checked} unchecked candidates dropped."
    )

    # SwingScore: 7-component deep-quality ranking. Run on top liquidity-passed candidates only.
    # Respects tier's min_swing_score when regime requires a stricter threshold.
    tier_min_swing = (
        exposure_constraints.get('min_swing_score', _MIN_SWING_SCORE)
        if exposure_constraints else _MIN_SWING_SCORE
    )
    effective_min_swing = max(_MIN_SWING_SCORE, tier_min_swing)

    swing_scorer = SwingTraderScore()
    swing_scored = []
    swing_errors = 0

    for candidate in liq_passed[:_SWING_SCORE_LIMIT]:
        try:
            result = swing_scorer.compute(candidate['symbol'], run_date)
            if result and result.get('pass') and result.get('swing_score', 0) >= effective_min_swing:
                candidate['swing_score'] = result['swing_score']
                candidate['swing_grade'] = result.get('grade', 'F')
                swing_scored.append(candidate)
        except Exception as e:
            swing_errors += 1
            logger.debug(f"[PHASE 5] SwingScore error {candidate['symbol']}: {e}")

    swing_checked = min(len(liq_passed), _SWING_SCORE_LIMIT)
    swing_error_rate = swing_errors / swing_checked if swing_checked > 0 else 0

    logger.info(
        f"[PHASE 5] SwingScore: {swing_checked} checked, {len(swing_scored)} passed "
        f"(>={effective_min_swing:.0f}), {swing_errors} errors"
    )

    # If >80% of swing scores errored, fall back to quality-ranked liquidity-passed candidates
    # rather than blocking all trades on an infrastructure failure.
    if swing_error_rate > 0.8 and swing_checked >= 5:
        logger.warning(
            f"[PHASE 5] SwingScore error rate {swing_error_rate:.0%} — "
            "falling back to quality-scored candidates"
        )
        final_candidates = liq_passed
    else:
        swing_scored.sort(key=lambda s: s.get('swing_score', 0), reverse=True)
        final_candidates = swing_scored

    logger.info(f"[PHASE 5] Top 10 qualified signals:")
    for i, sig in enumerate(final_candidates[:10]):
        swing_info = f" swing={sig.get('swing_score', '?')}{sig.get('swing_grade', '')}" if 'swing_score' in sig else ''
        logger.info(
            f"  {i+1}. {sig['symbol']:6s} quality={sig['quality_score']:3d} "
            f"stage={sig['weinstein_stage']} vcp={sig['vcp_pattern']} base={sig['base_detected']}{swing_info}"
        )

    elapsed = time.time() - phase_start
    log_phase_result_fn(5, 'signal_generation', 'success',
                        f'{len(final_candidates)} signals qualified ({len(errors)} errors)')

    return PhaseResult(
        5, 'signal_generation', 'ok',
        {
            'qualified_trades': final_candidates,
            'total_evaluated': len(symbols),
            'minervini_pass': minervini_pass_count,
            'quality_passed': len(candidates),
            'liquidity_passed': len(liq_passed),
            'swing_scored': len(swing_scored),
            'errors': errors,
            'regime': regime,
        },
        False,
        f'Generated {len(final_candidates)} signals in {elapsed:.1f}s'
    )

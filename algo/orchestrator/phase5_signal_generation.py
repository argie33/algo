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
import os
import time
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.db.context import DatabaseContext
from algo.signals import SignalComputer, VectorizedSignalGenerator, SwingTraderScore
from algo.risk import LiquidityChecks
from algo.orchestrator.phase_result import PhaseResult
from config.thresholds import ThresholdConfig

logger = logging.getLogger(__name__)

# Performance optimization limits (can be overridden by config)
# WARNING: These are performance trade-offs, not intentional feature disables.
# _SWING_SCORE_LIMIT = 0 disables SwingScore 7-component ranking (issue #10)
# This means signals are ranked only by quality score, not by deep swing trading metrics.
# To enable: set phase5_swing_score_limit in algo_config (non-zero value enables scoring)
_LIQUIDITY_CHECK_LIMIT = 10
_SWING_SCORE_LIMIT = 0  # Disabled by default (too slow for 60s SLA), enabled if config>0
_MAX_WORKERS = 4
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
            if row is None:
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


def _check_liquidity_parallel(candidate: Dict, run_date: _date) -> Tuple[Dict, bool]:
    """Check liquidity for a single candidate. Returns (candidate, passed)."""
    try:
        liquidity = LiquidityChecks(config={})
        liq_ok, liq_reason = liquidity.run_all(candidate['symbol'], 0, run_date)
        if not liq_ok:
            logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity — {liq_reason}")
        return candidate, liq_ok
    except Exception as e:
        logger.debug(f"[PHASE 5] {candidate['symbol']}: liquidity check error — {str(e)[:50]}")
        return candidate, False


def _compute_swing_score_parallel(candidate: Dict, run_date: _date, min_swing: int, config) -> Tuple[Dict, bool]:
    """Compute swing score for a single candidate. Returns (candidate_with_score, passed).

    Args:
        config: Required configuration object (dependency injection)
    """
    try:
        if config is None:
            raise ValueError("_compute_swing_score_parallel requires config parameter (dependency injection)")
        swing_scorer = SwingTraderScore(config)
        result = swing_scorer.compute(candidate['symbol'], run_date)
        if result and result.get('pass') and result.get('swing_score', 0) >= min_swing:
            candidate['swing_score'] = result['swing_score']
            candidate['swing_grade'] = result.get('grade', 'F')
            return candidate, True
        return candidate, False
    except Exception as e:
        logger.debug(f"[PHASE 5] {candidate['symbol']}: swing score error — {str(e)[:50]}")
        return candidate, False


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
    config = None,
) -> PhaseResult:
    import os
    # Enforce config parameter for dependency injection
    if config is None:
        raise ValueError("phase5_signal_generation.run() requires explicit config parameter (dependency injection). "
                        "Get config at orchestrator level and pass it explicitly.")
    phase_start = time.time()
    logger.info("[PHASE 5] Starting signal generation")

    # Load configurable thresholds
    min_close_quality = ThresholdConfig.min_close_quality_pct() / 100.0  # Convert percent to decimal

    # Allow SwingScore to be enabled/disabled via config (ISSUE #10)
    # phase5_swing_score_limit: 0=disabled (fast path), >0=number of candidates to score
    swing_score_limit = config.get('phase5_swing_score_limit', _SWING_SCORE_LIMIT) if config else _SWING_SCORE_LIMIT
    if swing_score_limit != _SWING_SCORE_LIMIT:
        logger.info(f"[PHASE 5] SwingScore limit overridden by config: {_SWING_SCORE_LIMIT} → {swing_score_limit}")

    # ISSUE #8 FIX: Check halt flag before generating signals
    # If Phase 1 detected stale data, don't generate full-intensity signals
    if check_halt_flag and check_halt_flag():
        logger.critical("[PHASE 5] Halt flag set by Phase 1 — data quality degradation detected. Halting signal generation.")
        log_phase_result_fn(5, 'signal_generation', 'halt', 'Halt flag set: data quality degradation')
        return PhaseResult(5, 'signal_generation', 'halted', {'qualified_trades': []}, True,
                         'Halt flag set: data quality degradation detected')

    # Verify signal score freshness (swing_trader_scores, signal_quality_scores must be <24h old)
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    signal_max_age_hours = config.get('phase5_signal_max_age_hours', 24) if config else 24
    try:
        with DatabaseContext('read') as cur:
            for score_table in ['swing_trader_scores', 'signal_quality_scores']:
                cur.execute(f"SELECT MAX(created_at) FROM {score_table}")
                max_created = cur.fetchone()[0]
                if max_created:
                    if max_created.tzinfo is None:
                        max_created = max_created.replace(tzinfo=timezone.utc)
                    age_hours = (now_utc - max_created).total_seconds() / 3600
                    if age_hours > signal_max_age_hours:
                        logger.critical(f"[PHASE 5] {score_table} is {age_hours:.1f}h old (max {signal_max_age_hours}h) — halting")
                        log_phase_result_fn(5, 'signal_scores_stale', 'halt',
                                           f'{score_table} is {age_hours:.1f}h old')
                        return PhaseResult(5, 'signal_scores_stale', 'halted', {'qualified_trades': []}, True,
                                         f'{score_table} stale: {age_hours:.1f}h old')
    except Exception as e:
        logger.warning(f"[PHASE 5] Could not check signal score freshness: {e} — proceeding")

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

    start_compute = time.time()

    # VECTORIZED: Compute Minervini + Weinstein + power_trend in parallel for ALL symbols
    vectorized_gen = VectorizedSignalGenerator()
    vectorized_signals = vectorized_gen.run(symbols, run_date)

    minervini_results = vectorized_signals.get('minervini', {})
    weinstein_results = vectorized_signals.get('weinstein', {})
    power_results = vectorized_signals.get('power', {})

    # Count passes before detailed scoring
    minervini_pass_count = sum(1 for r in minervini_results.values() if r.get('pass'))

    candidates = []
    errors = []
    signal_computer = SignalComputer()  # Only used for base/vcp on passing symbols

    for symbol in symbols:
        try:
            minervini = minervini_results.get(symbol, {'pass': False})

            # Hard gate: skip immediately if Minervini template fails (saves ~3 DB queries per symbol)
            if not minervini.get('pass'):
                continue

            # For passing Minervini symbols, compute base + VCP details (still per-symbol but only on ~500-1000 candidates)
            base = signal_computer.base_detection(symbol, run_date)
            vcp = signal_computer.vcp_detection(symbol, run_date)
            weinstein = weinstein_results.get(symbol, {})
            power = power_results.get(symbol, {})

            quality = _score_signal(minervini, weinstein, vcp, base, power)

            if quality >= _MIN_QUALITY:
                # Close quality gate (configurable via min_close_quality_pct).
                # A weak close (near day lows) on signal day indicates distribution — not a buy setup.
                ohlc = _ohlc.get(symbol, {})
                c, h, lo = ohlc.get('close'), ohlc.get('high'), ohlc.get('low')
                if h and lo and c and h > lo:
                    close_position = (c - lo) / (h - lo)
                    if close_position < min_close_quality:
                        logger.debug(f"[PHASE 5] {symbol}: weak close {close_position:.0%} of range (threshold={min_close_quality:.0%}) — skip")
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

        except Exception as e:
            errors.append(f"{symbol}: {str(e)[:50]}")

    compute_elapsed = time.time() - start_compute
    logger.info(
        f"[PHASE 5] Signal compute: {len(symbols)} symbols in {compute_elapsed:.1f}s (vectorized), "
        f"{minervini_pass_count} passed Minervini gate, {len(candidates)} scored >={_MIN_QUALITY}"
    )

    # Sort by quality before liquidity checks
    candidates.sort(key=lambda s: s['quality_score'], reverse=True)

    # Liquidity checks on top candidates — PARALLELIZED for speed
    liq_passed = []
    liq_checked = 0
    to_check = candidates[:_LIQUIDITY_CHECK_LIMIT]

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
        f"{len(candidates) - liq_checked} unchecked candidates dropped."
    )

    # SwingScore: 7-component deep-quality ranking — PARALLELIZED
    # Respects tier's min_swing_score when regime requires a stricter threshold.
    tier_min_swing = (
        exposure_constraints.get('min_swing_score', _MIN_SWING_SCORE)
        if exposure_constraints else _MIN_SWING_SCORE
    )
    effective_min_swing = max(_MIN_SWING_SCORE, tier_min_swing)

    swing_scored = []
    swing_errors = 0
    to_score = liq_passed[:swing_score_limit]

    if to_score:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            futures = {
                executor.submit(_compute_swing_score_parallel, cand, run_date, effective_min_swing, config): cand
                for cand in to_score
            }

            for future in as_completed(futures):
                candidate, passed = future.result()
                if passed:
                    swing_scored.append(candidate)
                elif not candidate.get('swing_score'):
                    swing_errors += 1

    swing_checked = len(to_score)
    swing_error_rate = swing_errors / swing_checked if swing_checked > 0 else 0

    logger.info(
        f"[PHASE 5] SwingScore: {swing_checked} checked, {len(swing_scored)} passed "
        f"(>={effective_min_swing:.0f}), {swing_errors} errors"
    )

    # If swing scoring is disabled (limit=0), or >80% of swing scores errored,
    # fall back to quality-ranked liquidity-passed candidates rather than blocking trades.
    if swing_score_limit == 0 or (swing_error_rate > 0.8 and swing_checked >= 5):
        if swing_score_limit == 0:
            logger.info("[PHASE 5] SwingScore disabled (phase5_swing_score_limit=0) — using quality-ranked candidates")
        else:
            logger.warning(
                f"[PHASE 5] SwingScore error rate {swing_error_rate:.0%} — "
                "falling back to quality-scored candidates"
            )
        # Sort by quality score for consistent ranking
        liq_passed.sort(key=lambda c: c.get('quality_score', 0), reverse=True)
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

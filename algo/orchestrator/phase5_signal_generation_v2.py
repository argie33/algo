#!/usr/bin/env python3
"""
PHASE 5: SIGNAL GENERATION (Simplified)

NEW APPROACH:
1. Query price_daily for all symbols (today + lookback)
2. Use SignalComputer to generate signals on-the-fly
3. Rank by quality
4. Cache results for Phase 6
5. Done in 30-40 minutes for 5000 symbols

OLD APPROACH (removed):
- Depended on technical_data_daily being pre-computed (180 min)
- Depended on buy_sell_daily being pre-computed (30 min)
- Complex state machine logic around halt flags
"""

import logging
import time
from datetime import date as _date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable, List, Dict, Optional

from utils.database_context import DatabaseContext
from algo.algo_signals import SignalComputer
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


def run(
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: Dict = None,
    check_halt_flag: Callable = None,
    phase1_degraded: bool = False,
) -> PhaseResult:
    """Execute Phase 5: Generate trading signals from price data.

    This version computes signals on-the-fly from price_daily,
    without needing pre-computed technical_data_daily.

    Args:
        run_date: Trading date
        dry_run: Whether running in dry-run mode
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        exposure_constraints: Portfolio exposure limits
        check_halt_flag: Function to check if trading is halted
        phase1_degraded: Whether Phase 1 reported degraded data quality

    Returns:
        PhaseResult with signals and metadata
    """
    phase_start = time.time()
    logger.info("[PHASE 5] Starting signal generation from price data")

    try:
        # Quick sanity check: prices loaded? If today has partial coverage (intraday seed),
        # fall back to the most recent date with full data (same logic as Phase 1).
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (run_date,)
            )
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
            logger.error(f"[PHASE 5] No price data for {run_date}")
            log_phase_result_fn(5, 'signal_generation', 'halt', 'No price data available')
            return PhaseResult(5, 'signal_generation', 'halted', {}, True, 'No price data')

        if price_date != run_date:
            logger.info(f"[PHASE 5] run_date={run_date} has partial coverage; using price_date={price_date} ({symbol_count} symbols)")

        logger.info(f"[PHASE 5] Computing signals for {symbol_count} symbols...")

        # Initialize signal computer
        signal_computer = SignalComputer()
        signals = []
        errors = []

        # Generate signals for all symbols
        start_compute = time.time()
        with DatabaseContext('read') as cur:
            # Get all symbols with prices on the most recent complete date
            cur.execute(
                "SELECT DISTINCT symbol FROM price_daily WHERE date = %s ORDER BY symbol",
                (price_date,)
            )
            symbols = [row[0] for row in cur.fetchall()]

        logger.info(f"[PHASE 5] Generating signals for {len(symbols)} symbols...")

        for i, symbol in enumerate(symbols):
            try:
                # Compute all signal types for this symbol
                minervini = signal_computer.minervini_trend_template(symbol, run_date)
                weinstein = signal_computer.weinstein_stage(symbol, run_date)
                base = signal_computer.base_detection(symbol, run_date)
                td_seq = signal_computer.td_sequential(symbol, run_date)
                vcp = signal_computer.vcp_detection(symbol, run_date)
                power = signal_computer.power_trend(symbol, run_date)

                # Combine into overall signal
                signal = {
                    'symbol': symbol,
                    'date': run_date.isoformat(),
                    'minervini_score': minervini.get('score', 0),
                    'minervini_pass': minervini.get('pass', False),
                    'weinstein_stage': weinstein.get('stage'),
                    'base_detected': base.get('in_base', False),
                    'td_setup_count': td_seq.get('setup_count', 0),
                    'vcp_pattern': vcp.get('is_vcp', False),
                    'power_trend': power.get('power_trend_pct', 0),
                    'quality_score': 0,  # Will be calculated below
                }

                # Calculate quality score (0-100)
                # Reward: Minervini pass + Weinstein stage 3+ + VCP + Power trend
                quality = 0
                if minervini.get('pass'):
                    quality += 40
                if weinstein.get('stage', 0) >= 3:
                    quality += 20
                if vcp.get('is_vcp'):
                    quality += 20
                if power.get('power_trend_pct', 0) > 0:
                    quality += 20

                signal['quality_score'] = quality

                # Only include signals with minimum quality
                if quality >= 30:  # Minimum threshold
                    signals.append(signal)

                if verbose and (i % 500 == 0):
                    logger.debug(f"  [{i}/{len(symbols)}] {symbol}: quality={quality}")

            except Exception as e:
                errors.append(f"{symbol}: {str(e)[:50]}")
                if verbose:
                    logger.debug(f"[PHASE 5] {symbol}: Signal computation failed: {e}")

        compute_elapsed = time.time() - start_compute

        # Rank signals by quality score
        signals_ranked = sorted(signals, key=lambda s: s['quality_score'], reverse=True)

        logger.info(f"[PHASE 5] ✓ Generated {len(signals)} signals ({len(errors)} errors)")
        logger.info(f"[PHASE 5]   Top 10 signals by quality:")
        for i, sig in enumerate(signals_ranked[:10]):
            logger.info(
                f"[PHASE 5]   {i+1}. {sig['symbol']:6s} quality={sig['quality_score']:3d} "
                f"(minervini={sig['minervini_score']}/8, stage={sig['weinstein_stage']})"
            )

        elapsed = time.time() - phase_start

        log_phase_result_fn(5, 'signal_generation', 'success',
                           f'{len(signals)} signals generated, top {len(signals_ranked[:20])} qualified')

        return PhaseResult(
            5, 'signal_generation', 'ok',
            {
                'qualified_trades': signals_ranked[:50],  # Top 50 for Phase 6
                'total_signals': len(signals),
                'errors': errors,
            },
            False,
            f'Generated {len(signals)} signals in {elapsed:.1f}s'
        )

    except Exception as e:
        logger.error(f"[PHASE 5] ERROR: {e}", exc_info=True)
        log_phase_result_fn(5, 'signal_generation', 'error', str(e)[:100])
        return PhaseResult(5, 'signal_generation', 'error', {}, True, f'Signal generation error: {str(e)[:100]}')

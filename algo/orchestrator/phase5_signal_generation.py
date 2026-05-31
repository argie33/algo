#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, List, Dict

from utils.database_context import DatabaseContext
from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager
from algo.algo_metrics import MetricsPublisher

logger = logging.getLogger(__name__)

def _report_signal_waterfall(cur: Any, run_date: _date, verbose: bool, final_count: int = 0) -> None:
    """Log signal count at each filter tier for visibility on rejections."""
    try:
        # Count total BUY signals for today
        cur.execute(
            "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
            (run_date,)
        )
        result = cur.fetchone()
        total_signals = result[0] if result else 0

        # Count from trend_template_data where Stage 2 exists
        # (Stage 2 check is in filter_pipeline, using pre-filtered signals)
        cur.execute(
            """SELECT COUNT(DISTINCT symbol) FROM trend_template_data
               WHERE date = %s AND weinstein_stage = 2""",
            (run_date,)
        )
        result = cur.fetchone()
        stage2_count = result[0] if result else 0

        # Count rejections at each tier from filter_rejection_log (if table exists)
        tier_rejections = {}
        try:
            for tier_num, tier_name in enumerate(['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'Tier 6'], 1):
                cur.execute(
                    f"SELECT COUNT(DISTINCT symbol) FROM filter_rejection_log WHERE eval_date = %s AND rejected_at_tier = %s",
                    (run_date, tier_num)
                )
                result = cur.fetchone()
                rejected = result[0] if result else 0
                tier_rejections[tier_name] = rejected
        except Exception as e:
            logger.warning(f"Exception: {e}")
            # Table may not exist or columns different; skip
            for tier_name in ['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'Tier 6']:
                tier_rejections[tier_name] = 0

        # Always log waterfall to diagnose 'no trades' situations
        logger.info(f"\n  [WATERFALL] Signal filtering on {run_date}:")
        logger.info(f"    Total BUY signals:        {total_signals:4d}")
        logger.info(f"    Stage 2 (pre-pipeline):   {stage2_count:4d}")
        logger.info(f"    Tier 1 rejected:          {tier_rejections.get('Tier 1', 0):4d}")
        logger.info(f"    Tier 2 rejected:          {tier_rejections.get('Tier 2', 0):4d}")
        logger.info(f"    Tier 3 rejected:          {tier_rejections.get('Tier 3', 0):4d}")
        logger.info(f"    Tier 4 rejected:          {tier_rejections.get('Tier 4', 0):4d}")
        logger.info(f"    Tier 5 rejected:          {tier_rejections.get('Tier 5', 0):4d}")
        logger.info(f"    Tier 6 rejected:          {tier_rejections.get('Tier 6', 0):4d}")
        logger.info(f"    Final qualified:          {final_count:4d}")
        interpretation = _interpret_waterfall(total_signals, stage2_count, tier_rejections, final_count)
        logger.info(f"  Interpretation: {interpretation}")

    except Exception as e:
        logger.warning(f"Signal waterfall report failed: {e}")

def _interpret_waterfall(total: int, stage2: int, tier_rejections: Dict[str, int], final: int) -> str:
    """Interpret the signal waterfall to help diagnose 'no trades' situations."""
    if total == 0:
        return "No BUY signals generated today. Check buy_sell_daily loader or market conditions."
    if stage2 == 0:
        return f"{total} signals exist but NONE are Stage 2. RSI<30 in Stage 2 stocks is rare. Check market stage."
    if final > 0:
        return f"[OK] {final} candidates qualified. Ready to execute."

    # Find the biggest rejection point
    max_reject_tier = max(tier_rejections, key=tier_rejections.get) if tier_rejections else "Unknown"
    max_reject_count = tier_rejections.get(max_reject_tier, 0)
    return f"Stage 2 signals exist but {max_reject_count} rejected at {max_reject_tier}. Review config thresholds."

def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
    exposure_constraints: Dict[str, Any],
    check_halt_flag: Callable,
) -> PhaseResult:
    """Execute Phase 5: Signal Generation & Ranking.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        exposure_constraints: Exposure constraints from Phase 3b
        check_halt_flag: Function to check halt flag

    Returns:
        PhaseResult with status 'ok', data containing qualified trades
    """
    if check_halt_flag():
        return PhaseResult(5, 'signal_generation', 'halted', {}, True, 'Halt flag detected')

    logger.info(f"\n{'='*70}")
    logger.info(f"PHASE 5: SIGNAL GENERATION & RANKING")
    logger.info(f"{'='*70}")
    if exposure_constraints:
        logger.info(f"Exposure constraints: risk_mult={exposure_constraints.get('risk_multiplier', 1.0):.2f}x, tier='{exposure_constraints.get('tier_name', 'N/A')}'")
    else:
        logger.info("Exposure constraints: None (no tier active, using defaults)")

    try:
        from algo.algo_filter_pipeline import FilterPipeline

        exposure_mult = 1.0
        if exposure_constraints:
            exposure_mult = exposure_constraints.get('risk_multiplier', 1.0)

        pipeline = FilterPipeline(exposure_risk_multiplier=exposure_mult)
        qualified = pipeline.evaluate_signals(None)  # Auto-detect latest date with complete data
        eval_date = pipeline._snapshot_eval_date or run_date

        # Signal count waterfall report (for visibility on where signals die)
        try:
            with DatabaseContext('read') as cur:
                _report_signal_waterfall(cur, eval_date, verbose, len(qualified))
                # When nothing qualifies, emit a clear diagnostic so we know exactly why
                if len(qualified) == 0:
                    cur.execute(
                        "SELECT date, market_stage, market_trend, distribution_days_4w, vix_level "
                        "FROM market_health_daily ORDER BY date DESC LIMIT 1"
                    )
                    mh = cur.fetchone()
                    cur.execute(
                        "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
                        (eval_date,)
                    )
                    bsd_count = (cur.fetchone() or [0])[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM trend_template_data WHERE date = %s AND weinstein_stage = 2",
                        (eval_date,)
                    )
                    stage2_stocks = (cur.fetchone() or [0])[0]
                    if mh:
                        logger.warning(
                            f"[ZERO TRADES DIAGNOSIS] eval_date={eval_date} | "
                            f"market_health latest={mh[0]} stage={mh[1]} trend={mh[2]} "
                            f"dist_days={mh[3]} vix={mh[4]} | "
                            f"buy_signals={bsd_count} stage2_stocks={stage2_stocks}"
                        )
                        if mh[1] != 2:
                            logger.warning(
                                f"[ZERO TRADES] Primary blocker: market_stage={mh[1]} (need 2 for Tier 2). "
                                f"Set require_stage_2_market=false in algo_config table to trade in other market stages."
                            )
                    else:
                        logger.warning(f"[ZERO TRADES DIAGNOSIS] eval_date={eval_date} | market_health_daily: NO ROWS FOUND")
        except Exception as e:
            logger.warning(f"Signal waterfall report failed (non-blocking): {e}")

        log_phase_result_fn(
            5, 'signal_generation', 'success',
            f'{len(qualified)} qualified trades after all 6 tiers',
        )

        return PhaseResult(
            5, 'signal_generation', 'ok',
            {'qualified_trades': qualified, 'count': len(qualified)},
            False, None
        )

    except RuntimeError as e:
        logger.critical(f"PHASE 5 HALT — portfolio value unavailable, no new entries: {e}")
        try:
            with MetricsPublisher(dry_run=dry_run) as _m:
                _m.put_circuit_breaker('PortfolioValueUnavailable', fired=True)
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")

        log_phase_result_fn(5, 'signal_generation', 'halt', str(e))
        return PhaseResult(5, 'signal_generation', 'halted', {}, True, str(e))

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(5, 'signal_generation', 'error', str(e))
        # Fail-open: log error but don't halt — Phase 6 gets empty qualified_trades
        # and will log "no qualified trades" rather than blocking exits/reconciliation.
        return PhaseResult(5, 'signal_generation', 'error', {'qualified_trades': []}, False, str(e))

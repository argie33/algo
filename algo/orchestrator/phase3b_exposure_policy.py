#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date, datetime
from typing import Any, Callable, Dict, List

from utils.timezone_utils import EASTERN_TZ
from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager

logger = logging.getLogger(__name__)

def _is_live_evening_run(run_date):
    """Return True only for same-day live runs after 5 PM ET.

    Historical replays (run_date < today) never force-recompute — the data is
    already settled for that date and recomputing would hit the wrong market data.
    """
    from datetime import date as _today_date
    if run_date < _today_date.today():
        return False
    try:
        et_tz = EASTERN_TZ
        now_et = datetime.now(et_tz)
        return now_et.hour >= 17
    except Exception as e:
        logger.warning(f"Could not determine run time: {e}")
        return False

def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 3b: Exposure Policy Actions.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok', data containing exposure constraints and actions
    """
    try:
        # Refresh market exposure first
        from algo.algo_market_exposure import MarketExposure
        from algo.algo_market_exposure_policy import ExposurePolicy

        me = MarketExposure()
        # Use cached market exposure (computed once per day at EOD) unless we're in evening refresh
        # Evening refresh (after 5 PM) recomputes for next day's trading decisions
        force_recompute = _is_live_evening_run(run_date)
        exposure = me.compute(run_date, force_recompute=force_recompute)
        cache_status = " ✓ cached" if exposure.get('_cached') else " (recomputed)"
        logger.info(f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']}){cache_status}")
        if exposure.get('halt_reasons'):
            logger.info(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")

        policy = ExposurePolicy(config)
        constraints = policy.get_entry_constraints(run_date)

        if constraints:
            logger.info(f"  Tier: {constraints['tier_name']} — {constraints['description']}")
            logger.info(f"    risk_mult={constraints['risk_multiplier']}, "
                       f"max_new/day={constraints['max_new_positions_today']}, "
                       f"min_grade={constraints['min_swing_grade']}, "
                       f"halt_entries={constraints['halt_new_entries']}")

        try:
            actions = policy.review_existing_positions(run_date)
        except Exception as e:
            # If transaction is aborted (from prior phase), retry with fresh connection
            if "transaction is aborted" in str(e).lower() or "InFailedSqlTransaction" in str(type(e)):
                logger.warning(f"Transaction aborted, retrying with fresh connection: {e}")
                policy = ExposurePolicy(config)
                actions = policy.review_existing_positions(run_date)
            else:
                raise

        if not actions:
            logger.info(f"  No exposure-policy actions")
            log_phase_result_fn('3b', 'exposure_policy', 'success',
                               f'tier={constraints["tier_name"] if constraints else "n/a"}, no actions')
            return PhaseResult(
                '3b', 'exposure_policy', 'ok',
                {'constraints': constraints, 'actions': []},
                False, None
            )

        counts = {'tighten_stop': 0, 'partial_exit': 0, 'force_exit': 0}
        for action in actions:
            counts[action['action']] = counts.get(action['action'], 0) + 1

        logger.info(f"\n  {len(actions)} exposure-policy actions:")
        for a in actions:
            logger.info(f"    {a['symbol']:6s} -> {a['action'].upper():15s} "
                       f"R={a.get('r_multiple', 0):+.2f}  {a['reason']}")

        tier_name = constraints['tier_name'] if constraints else 'unknown'
        log_phase_result_fn(
            '3b', 'exposure_policy', 'success',
            f"tier={tier_name}, "
            f"{counts.get('tighten_stop', 0)} tighten, "
            f"{counts.get('partial_exit', 0)} partial, "
            f"{counts.get('force_exit', 0)} force_exit"
        )

        return PhaseResult(
            '3b', 'exposure_policy', 'ok',
            {'constraints': constraints, 'actions': actions},
            False, None
        )

    except Exception as e:
        # FAIL-OPEN: exposure policy errors don't block execution
        # (e.g., transaction aborts from prior phases, missing data, etc.)
        logger.warning(f"Exposure policy phase skipped due to error (fail-open): {e}")
        log_phase_result_fn('3b', 'exposure_policy', 'skip',
                           f'Skipped due to error: {str(e)[:80]}')
        return PhaseResult('3b', 'exposure_policy', 'ok', {'constraints': None, 'actions': []}, False, None)

#!/usr/bin/env python3
"""
Phase 3b: EXPOSURE POLICY ACTIONS

Apply market exposure tier policy to existing positions.

Tightens stops on extended winners, forces partial profits, and forces exits
on losers when in CORRECTION tier — all per the active exposure regime.

Returns exposure constraints for use in later phases (Phases 4, 6).

FAIL-OPEN: log errors but continue.
"""

import logging
import traceback
from datetime import date as _date, datetime
from typing import Any, Callable, Dict, List

from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager

logger = logging.getLogger(__name__)


def _is_evening_run():
    """Check if current time is evening (after 5 PM ET, before market close next day).

    Evening runs (5:30 PM ET) should recompute market exposure for next day's trading.
    Intraday runs (morning 9:30 AM, afternoon 1 PM, pre-close 3 PM) use cached value.
    """
    try:
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        now_et = datetime.now(et_tz)
        # Evening = after 5 PM (17:00)
        return now_et.hour >= 17
    except Exception:
        return False


def run(
    config: Any,
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 3b: Exposure Policy Actions.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
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
        force_recompute = _is_evening_run()
        exposure = me.compute(run_date, force_recompute=force_recompute)
        cache_status = " (RECOMPUTED)" if force_recompute or exposure.get('_cached') else " (RECOMPUTED, no cache)"
        if exposure.get('_cached'):
            cache_status = " ✓ cached"
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

        log_phase_result_fn(
            '3b', 'exposure_policy', 'success',
            f"tier={constraints['tier_name']}, "
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

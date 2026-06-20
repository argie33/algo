#!/usr/bin/env python3

import logging
from datetime import date as _date
from typing import Any, Callable

from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager


logger = logging.getLogger(__name__)


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
        # Load cached market exposure from EOD pipeline (4:05 PM is sole source of truth)
        # All orchestrator runs use the cached value — no recomputation.
        # This ensures single source of truth and prevents divergence between EOD and evening runs.
        from algo.risk import ExposurePolicy, MarketExposure

        me = MarketExposure()
        # Always use cached exposure (computed once per day at 4:05 PM EOD pipeline)
        exposure = me.compute(run_date, force_recompute=False)
        cache_status = (
            " ✓ cached"
            if exposure.get("_cached")
            else " (WARNING: not cached, using fallback)"
        )
        logger.info(
            f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']}){cache_status}"
        )
        if exposure.get("halt_reasons"):
            logger.info(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")

        policy = ExposurePolicy()
        constraints = policy.get_entry_constraints(run_date)

        if constraints:
            logger.info(
                f"  Tier: {constraints['tier_name']} — {constraints['description']}"
            )
            logger.info(
                f"    risk_mult={constraints['risk_multiplier']}, "
                f"max_new/day={constraints['max_new_positions_today']}, "
                f"min_grade={constraints['min_swing_grade']}, "
                f"halt_entries={constraints['halt_new_entries']}"
            )

        try:
            actions = policy.review_existing_positions(run_date)
        except Exception as e:
            # If transaction is aborted (from prior phase), retry with fresh connection
            if "transaction is aborted" in str(
                e
            ).lower() or "InFailedSqlTransaction" in str(type(e)):
                logger.warning(
                    f"Transaction aborted, retrying with fresh connection: {e}"
                )
                policy = ExposurePolicy()
                actions = policy.review_existing_positions(run_date)
            else:
                raise

        if not actions:
            logger.info("  No exposure-policy actions")
            log_phase_result_fn(
                "3b",
                "exposure_policy",
                "success",
                f'tier={constraints["tier_name"] if constraints else "n/a"}, no actions',
            )
            return PhaseResult(
                "3b",
                "exposure_policy",
                "ok",
                {"constraints": constraints, "actions": []},
                False,
                None,
            )

        counts = {"tighten_stop": 0, "partial_exit": 0, "force_exit": 0}
        for action in actions:
            counts[action["action"]] = counts.get(action["action"], 0) + 1

        logger.info(f"\n  {len(actions)} exposure-policy actions:")
        for a in actions:
            logger.info(
                f"    {a['symbol']:6s} -> {a['action'].upper():15s} "
                f"R={a.get('r_multiple', 0):+.2f}  {a['reason']}"
            )

        tier_name = constraints["tier_name"] if constraints else "unknown"
        log_phase_result_fn(
            "3b",
            "exposure_policy",
            "success",
            f"tier={tier_name}, "
            f"{counts.get('tighten_stop', 0)} tighten, "
            f"{counts.get('partial_exit', 0)} partial, "
            f"{counts.get('force_exit', 0)} force_exit",
        )

        return PhaseResult(
            "3b",
            "exposure_policy",
            "ok",
            {"constraints": constraints, "actions": actions},
            False,
            None,
        )

    except Exception as e:
        # FAIL-CLOSED: exposure policy errors result in conservative default constraints
        # (e.g., transaction aborts from prior phases, missing data, etc.)
        # Applies strictest tier to prevent position sizing violations when data is unavailable.
        logger.critical(f"Exposure policy computation failed — applying conservative defaults (fail-closed): {e}")

        # Conservative defaults: strictest constraints to prevent unlimited position sizing
        conservative_constraints = {
            "tier_name": "CAUTION",
            "description": "Conservative defaults (exposure policy unavailable)",
            "risk_multiplier": 0.5,
            "max_new_positions_today": 2,  # Drastically limit new entries
            "min_swing_grade": "A",  # Highest bar for entry
            "halt_new_entries": False,  # Do not halt, but cap strictly
            "max_concentration_pct": 5.0,  # Tightest concentration limit
            "halt_reason": f"Exposure policy unavailable: {str(e)[:80]}",
        }

        log_phase_result_fn(
            "3b", "exposure_policy", "fallback",
            f"Using conservative constraints due to error: {str(e)[:80]}"
        )
        return PhaseResult(
            "3b",
            "exposure_policy",
            "degraded",
            {"constraints": conservative_constraints, "actions": []},
            False,
            str(e),
        )

#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
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
        # Read market exposure from market_exposure_daily (4:05 PM EOD pipeline is sole source of truth)
        # Uses shared read_market_regime() to ensure Phase 3b and Phase 5 read same snapshot
        # with consistent JSON deserialization error handling.
        from algo.risk import ExposurePolicy, MarketDataUnavailableError, read_market_regime

        try:
            exposure = read_market_regime(run_date)
            logger.info(f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']})")
            if exposure.get("halt_reasons"):
                logger.info(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")
        except (MarketDataUnavailableError, KeyError, ValueError) as e:
            # Market data unavailable in test mode - use safe defaults for paper trading
            logger.warning(f"[PHASE 5] Market data unavailable ({type(e).__name__}): {str(e)[:80]}")
            exposure = {"exposure_pct": 50, "regime": "caution", "halt_reasons": ["market_data_unavailable"]}

        policy = ExposurePolicy()
        constraints = policy.get_entry_constraints(run_date)

        if constraints:
            logger.info(f"  Tier: {constraints['tier_name']} — {constraints['description']}")
            logger.info(
                f"    risk_mult={constraints['risk_multiplier']}, "
                f"max_new/day={constraints['max_new_positions_today']}, "
                f"min_composite={constraints['min_composite_score']}, "
                f"halt_entries={constraints['halt_new_entries']}"
            )

        try:
            actions = policy.review_existing_positions(run_date)
        except (RuntimeError, ValueError) as e:
            # If transaction is aborted (from prior phase), retry with fresh connection
            if "transaction is aborted" in str(e).lower() or "InFailedSqlTransaction" in str(type(e)):
                logger.warning(f"Transaction aborted, retrying with fresh connection: {e}")
                policy = ExposurePolicy()
                actions = policy.review_existing_positions(run_date)
            else:
                raise

        if not actions:
            logger.info("  No exposure-policy actions")
            # CRITICAL FIX: Never return None constraints. Apply conservative CAUTION defaults if missing.
            # Returning None causes Phase 8 to halt all trading, creating a complete system failure.
            if not constraints:
                logger.warning(
                    "[PHASE 5] No entry constraints from policy — applying CAUTION defaults to keep trading enabled"
                )
                constraints = {
                    "tier_name": "CAUTION",
                    "description": "Conservative entry constraints (system fallback)",
                    "max_new_positions_today": 2,
                    "halt_new_entries": False,
                    "halt_reason": None,  # Not halting, so no halt reason needed
                    "min_composite_score": 60,
                    "risk_multiplier": 0.5,
                    "max_concentration_pct": 12.0,  # Default concentration limit
                }
            log_phase_result_fn(
                5,
                "exposure_policy",
                "success",
                f"tier={constraints['tier_name']}, no actions",
            )
            return PhaseResult(
                5,
                "exposure_policy",
                "ok",
                {"constraints": constraints, "actions": []},
                False,
                None,
            )

        valid_actions = {"tighten_stop", "partial_exit", "force_exit"}
        counts = {"tighten_stop": 0, "partial_exit": 0, "force_exit": 0}
        for action in actions:
            if "action" not in action or "symbol" not in action or "reason" not in action:
                raise RuntimeError(
                    "[PHASE 5] Exposure action missing required fields (action, symbol, reason). "
                    "Cannot process exposure policy without all identifiers. "
                    "Verify ExposurePolicy.review_existing_positions() returns valid action data."
                )
            action_type = action["action"]
            if action_type not in valid_actions:
                raise RuntimeError(
                    f"[PHASE 5] Unknown exposure action type '{action_type}'. "
                    f"Must be one of: {', '.join(valid_actions)}. "
                    "Verify ExposurePolicy.review_existing_positions() returns valid action types."
                )
            counts[action_type] += 1

        logger.info(f"\n  {len(actions)} exposure-policy actions:")
        for a in actions:
            r_mult = a.get("r_multiple")
            r_str = f"{r_mult:+.2f}" if r_mult is not None else "N/A"
            logger.info(f"    {a['symbol']:6s} -> {a['action'].upper():15s} R={r_str}  {a['reason']}")

        # CRITICAL FIX: Never return None constraints. Apply conservative CAUTION defaults if missing.
        if constraints is None:
            logger.warning("[PHASE 5] Exposure actions computed without entry constraints — applying CAUTION defaults")
            constraints = {
                "tier_name": "CAUTION",
                "description": "Conservative entry constraints (system fallback)",
                "max_new_positions_today": 2,
                "halt_new_entries": False,
                "halt_reason": None,  # Not halting, so no halt reason needed
                "halt_new_entries": False,
                "min_composite_score": 60,
                "risk_multiplier": 0.5,
            }
            tier_name = "CAUTION (fallback)"
        else:
            tier_name = constraints["tier_name"]
        # Validate counts dict has required keys before logging
        log_phase_result_fn(
            5,
            "exposure_policy",
            "success",
            f"tier={tier_name}, "
            f"{counts['tighten_stop']} tighten, "
            f"{counts['partial_exit']} partial, "
            f"{counts['force_exit']} force_exit",
        )

        return PhaseResult(
            5,
            "exposure_policy",
            "ok",
            {"constraints": constraints, "actions": actions},
            False,
            None,
        )

    except MarketDataUnavailableError as e:
        # FAIL-CLOSED: Market exposure data missing (Phase 4 not run or database corrupt)
        # CRITICAL: No market regime data means we can't assess market conditions.
        # Halting all entries is mandatory; this is not optional.
        logger.critical(
            f"CRITICAL: Market exposure data missing (Phase 4 likely failed). "
            f"Halting all new entries until market regime is available: {e}"
        )
        fail_halt_constraints = {
            "tier_name": "CORRECTION",
            "description": "Market regime data missing — no entries allowed",
            "risk_multiplier": 0.0,
            "max_new_positions_today": 0,
            "halt_new_entries": True,
            "max_concentration_pct": 0.0,
            "halt_reason": f"Market exposure data missing: {str(e)[:80]}",
        }
        log_phase_result_fn(
            5,
            "exposure_policy",
            "error",
            f"Market regime unavailable, halting entries: {str(e)[:80]}",
        )
        return PhaseResult(
            5,
            "exposure_policy",
            "error",
            {"constraints": fail_halt_constraints, "actions": []},
            False,
            str(e),
        )

    except Exception as e:
        # FAIL-CLOSED: Transient failure (e.g., database connection issue) or computation error
        # Risk multiplier, entry constraints, and concentration limits are load-bearing.
        # Exposing them to be wrong is more dangerous than halting trading.
        logger.critical(
            f"CRITICAL: Exposure policy computation failed. "
            f"Cannot proceed with trading without valid risk management constraints: {type(e).__name__}: {e}"
        )
        fail_halt_constraints = {
            "tier_name": "CORRECTION",
            "description": "Exposure policy unavailable due to system error — no entries allowed",
            "risk_multiplier": 0.0,
            "max_new_positions_today": 0,
            "halt_new_entries": True,
            "max_concentration_pct": 0.0,
            "halt_reason": f"Exposure policy error: {str(e)[:100]}. No entries allowed until resolved.",
        }
        log_phase_result_fn(
            5,
            "exposure_policy",
            "error",
            f"Exposure policy error — halting entries: {str(e)[:80]}",
        )
        return PhaseResult(
            5,
            "exposure_policy",
            "error",
            {"constraints": fail_halt_constraints, "actions": []},
            False,
            str(e),
        )

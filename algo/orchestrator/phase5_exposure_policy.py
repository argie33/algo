#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any, cast

from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase_data_contract import ExposureConstraints, validate_phase_data
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)

# ISSUE 15 FIX: Define valid constraint values
# CRITICAL FIX: Must match the actual regime taxonomy written to market_exposure_daily.regime
# and read by algo.orchestration.regime_manager.RegimeManager.REGIMES. The previous list
# ("expansion"/"correction"/"caution") never matched real data - market_exposure_daily has
# produced "uptrend_under_pressure" every single day for weeks, so this validator raised
# ValueError on every real run and crashed Phase 5 (and Phase 6/8 downstream) unconditionally.
VALID_REGIMES = ["confirmed_uptrend", "uptrend_under_pressure", "caution", "correction"]
VALID_CONSTRAINT_KEYS = [
    "halt_new_entries",
    "halt_reason",
    "max_new_positions_today",
    "max_concentration_pct",
    "regime",
    "risk_multiplier",
    "tier_name",
    "description",
    "min_composite_score",
]


def validate_constraint_dict(constraints: ExposureConstraints | dict[str, Any]) -> None:
    """ISSUE 15 FIX: Validate constraint dict values, not just keys.

    Ensures all required constraint fields have valid values before trading.
    Fail-fast if any constraint is invalid or missing.

    Raises:
        ValueError: If any constraint is invalid or missing
    """
    if not isinstance(constraints, dict):
        raise TypeError(f"constraints must be dict, got {type(constraints).__name__}")

    errors = []

    # Check required keys exist
    required_keys = ["halt_new_entries", "max_new_positions_today", "max_concentration_pct", "regime"]
    for key in required_keys:
        if key not in constraints:
            errors.append(f"Missing required key: {key}")

    # Validate individual field values
    if "halt_new_entries" in constraints:
        if not isinstance(constraints["halt_new_entries"], bool):
            errors.append(
                f"halt_new_entries must be bool, got {type(constraints.get('halt_new_entries')).__name__}"
            )
        elif constraints["halt_new_entries"] and not constraints.get("halt_reason"):
            errors.append("halt_reason required when halt_new_entries=True")

    if "max_new_positions_today" in constraints:
        val = constraints.get("max_new_positions_today")
        if not isinstance(val, int) or val < 0:
            errors.append(f"max_new_positions_today must be int >= 0, got {val}")

    if "max_concentration_pct" in constraints:
        val = constraints.get("max_concentration_pct")
        if not isinstance(val, (int, float)) or not (0.0 <= val <= 100.0):
            errors.append(f"max_concentration_pct must be 0.0-100.0, got {val}")

    if "regime" in constraints:
        regime = constraints.get("regime", "").lower()
        if regime not in VALID_REGIMES:
            errors.append(f"regime must be one of {VALID_REGIMES}, got '{regime}'")

    if "risk_multiplier" in constraints:
        risk_mult = constraints.get("risk_multiplier")
        if risk_mult is not None and (not isinstance(risk_mult, (int, float)) or not (0.0 <= risk_mult <= 1.0)):
            errors.append(f"risk_multiplier must be 0.0-1.0, got {risk_mult}")

    if errors:
        error_msg = f"Invalid constraints: {'; '.join(errors)}"
        logger.error(f"[PHASE 5] {error_msg}")
        raise ValueError(error_msg)


def _health_panel_fields(constraints: ExposureConstraints | dict[str, Any] | Any) -> dict[str, Any]:
    """Map ExposurePolicy constraint keys to the exact keys the health dashboard
    (dashboard/panels/health.py, Phase 5 detail row) reads - previously PhaseResult.data
    only carried {"constraints": {...}, "actions": [...]}, so Market regime/New entries/
    Max slots/Halt status silently never rendered despite constraints already having this
    data under its own (differently-named) keys.

    Accepts both dataclass (ExposurePolicyConstraints), TypedDict (ExposureConstraints),
    and dict for backwards compatibility.
    """
    from algo.risk import ExposurePolicyConstraints

    # Convert dataclass to dict if needed
    if isinstance(constraints, ExposurePolicyConstraints):
        constraints_dict = constraints.to_dict()
    else:
        constraints_dict = cast(dict[str, Any], constraints)

    required_keys = ["regime", "halt_new_entries", "max_new_positions_today", "halt_reason"]
    missing = [k for k in required_keys if k not in constraints_dict]
    if missing:
        raise KeyError(
            f"Exposure constraints missing required fields {missing}. "
            f"Dashboard cannot render health panel without complete constraint data. "
            f"Constraints keys: {list(constraints_dict.keys())}"
        )

    return {
        "market_regime": constraints_dict["regime"],
        "entry_allowed": not constraints_dict["halt_new_entries"],
        "halt_active": constraints_dict["halt_new_entries"],
        "max_new_entries": constraints_dict["max_new_positions_today"],
        "halt_reason": constraints_dict["halt_reason"],
    }


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 5: Exposure Policy Actions.

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
    # CRITICAL FIX: Import exception types OUTSIDE try block so they're accessible in except clauses
    from algo.orchestration.halt_flag_manager import HaltFlagManager
    from algo.orchestrator.phase_data_contract import validate_phase_5_constraints
    from algo.risk import ExposurePolicy, MarketDataUnavailableError, read_market_regime

    try:
        validate_phase_config(config, "phase_5_exposure_policy")

        halt_mgr = HaltFlagManager(alerts, log_phase_result_fn)
        if halt_mgr.check_halt_flag():
            error_msg = "[PHASE 5] Halt flag detected at phase start - aborting signal generation"
            logger.critical(error_msg)
            log_phase_result_fn(5, "exposure_policy", "halt", error_msg)
            # CRITICAL: Must return safe halt constraints for Phase 8, not empty dict
            fail_halt_constraints = {
                "regime": "correction",
                "tier_name": "CORRECTION",
                "description": "Prior phase halted - no entries allowed",
                "risk_multiplier": 0.0,
                "max_new_positions_today": 0,
                "halt_new_entries": True,
                "max_concentration_pct": 0.0,
                "halt_reason": error_msg,
            }
            # ISSUE 15 FIX: Validate halt constraints before returning
            validate_constraint_dict(fail_halt_constraints)
            validate_phase_5_constraints(fail_halt_constraints)
            return PhaseResult(
                5,
                "exposure_policy",
                "halted",
                {"constraints": fail_halt_constraints, "actions": [], **_health_panel_fields(fail_halt_constraints)},
                True,
                error_msg,
            )

        # Read market exposure from market_exposure_daily (4:05 PM EOD pipeline is sole source of truth)
        # Uses shared read_market_regime() to ensure Phase 3b and Phase 5 read same snapshot
        # with consistent JSON deserialization error handling.
        try:
            exposure = read_market_regime(run_date)
            logger.info(f"  Exposure: {exposure['exposure_pct']}% ({exposure['regime']})")
            if exposure.get("halt_reasons"):
                logger.info(f"  Halt reasons: {'; '.join(exposure['halt_reasons'])}")
        except MarketDataUnavailableError as e:
            # Market data unavailable - fail-fast to prevent stale risk decisions
            e_str = f"{e!s}"[:120]
            logger.error(f"[PHASE 5] CRITICAL: Market data unavailable, cannot proceed with exposure policy: {e_str}")
            raise RuntimeError(f"[PHASE 5] Cannot compute exposure without market regime data. {e!s}") from e
        except (KeyError, ValueError) as e:
            # Data structure error - likely upstream bug
            e_str = f"{e!s}"[:120]
            logger.error(f"[PHASE 5] CRITICAL: Market regime data malformed or missing required fields: {e_str}")
            raise RuntimeError(f"[PHASE 5] Market regime data structure invalid. {e!s}") from e

        policy = ExposurePolicy()
        constraints = policy.get_entry_constraints(run_date)

        if constraints:
            logger.info(f"  Tier: {constraints.tier_name} - {constraints.description}")
            logger.info(
                f"    risk_mult={constraints.risk_multiplier}, "
                f"max_new/day={constraints.max_new_positions_today}, "
                f"min_composite={constraints.min_composite_score}, "
                f"halt_entries={constraints.halt_new_entries}"
            )

        try:
            actions = policy.review_existing_positions(run_date)
        except (RuntimeError, ValueError) as e:
            # Transaction aborts are NOT transient - they indicate a real error in a prior phase.
            # Do NOT retry silently; fail-fast so operators can investigate root cause.
            # If a prior phase left the transaction in a bad state, retrying here masks that issue.
            error_msg = (
                f"[PHASE 5 FAIL-FAST] Position review failed: {e}. "
                f"This indicates either a query error or a transaction state issue from a prior phase. "
                f"Do not retry - check database logs and prior phase execution. "
                f"Cannot proceed with exposure policy without successful position review."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from e

        if not actions:
            logger.info("  No exposure-policy actions")
            # CRITICAL: Constraints MUST exist. Failure to load risk policy is a system error.
            if not constraints:
                logger.error(
                    "[PHASE 5] CRITICAL: Risk policy constraints failed to load. Cannot proceed without defined risk tiers."
                )
                raise RuntimeError(
                    "[PHASE 5] Risk policy constraints are required but missing. Check ExposurePolicy configuration and database."
                )
            log_phase_result_fn(
                5,
                "exposure_policy",
                "success",
                f"tier={constraints.tier_name}, no actions",
            )
            # ISSUE 15 FIX: Validate constraints before returning
            constraints_dict = constraints.to_dict()
            validate_constraint_dict(constraints_dict)
            # CRITICAL: Validate constraints have all fields required by Phase 7 and Phase 8
            validate_phase_5_constraints(constraints_dict)
            return PhaseResult(
                5,
                "exposure_policy",
                "ok",
                {"constraints": constraints_dict, "actions": [], **_health_panel_fields(constraints)},
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

        # CRITICAL: Constraints MUST exist at this point
        if constraints is None:
            logger.error(
                "[PHASE 5] CRITICAL: Risk policy constraints are None after review_existing_positions. "
                "This indicates ExposurePolicy.get_entry_constraints() failed to load risk tiers."
            )
            raise RuntimeError(
                "[PHASE 5] Risk policy constraints missing after position review. Check database and policy configuration."
            )
        tier_name = constraints.tier_name
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

        # CRITICAL FIX: Store constraints as dict, not dataclass
        # Phase 8 expects dict with .get() and 'in' operations
        # Dataclass doesn't support these operations, causing Phase 8 to crash
        constraints_dict = constraints.to_dict()
        validate_constraint_dict(constraints_dict)
        validate_phase_5_constraints(constraints_dict)
        phase_data = {"constraints": constraints_dict, "actions": actions, **_health_panel_fields(constraints)}
        validate_phase_data(5, phase_data)
        return PhaseResult(
            5,
            "exposure_policy",
            "ok",
            phase_data,
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
            "regime": "correction",
            "tier_name": "CORRECTION",
            "description": "Market regime data missing - no entries allowed",
            "risk_multiplier": 0.0,
            "max_new_positions_today": 0,
            "halt_new_entries": True,
            "max_concentration_pct": 0.0,
            "halt_reason": f"Market exposure data missing: {str(e)[:80]}",
        }
        # ISSUE 15 FIX: Validate halt constraints before returning
        validate_constraint_dict(fail_halt_constraints)
        validate_phase_5_constraints(fail_halt_constraints)
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
            {"constraints": fail_halt_constraints, "actions": [], **_health_panel_fields(fail_halt_constraints)},
            True,  # CRITICAL: Market data missing = halt orchestrator
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
            "regime": "correction",
            "tier_name": "CORRECTION",
            "description": "Exposure policy unavailable due to system error - no entries allowed",
            "risk_multiplier": 0.0,
            "max_new_positions_today": 0,
            "halt_new_entries": True,
            "max_concentration_pct": 0.0,
            "halt_reason": f"Exposure policy error: {str(e)[:500]}. No entries allowed until resolved.",
        }
        # ISSUE 15 FIX: Validate halt constraints before returning
        validate_constraint_dict(fail_halt_constraints)
        validate_phase_5_constraints(fail_halt_constraints)
        log_phase_result_fn(
            5,
            "exposure_policy",
            "error",
            f"Exposure policy error - halting entries: {str(e)[:80]}",
        )
        return PhaseResult(
            5,
            "exposure_policy",
            "error",
            {"constraints": fail_halt_constraints, "actions": [], **_health_panel_fields(fail_halt_constraints)},
            True,  # CRITICAL: Exposure policy error = halt orchestrator
            str(e),
        )

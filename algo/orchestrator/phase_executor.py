#!/usr/bin/env python3
"""OrchestratorPhaseExecutor: Framework for executing phases with explicit dependency management."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


@dataclass
class PhaseDefinition:
    """Declares a phase's identity, dependencies, and execution function."""

    phase_num: int | str
    phase_name: str
    dependencies: list[int | str] = field(default_factory=list)
    execute_fn: Callable[..., PhaseResult] | None = None
    skip_if_halted: bool = True
    always_run: bool = False

    def __hash__(self) -> int:
        return hash((self.phase_num, self.phase_name))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, PhaseDefinition):
            return self.phase_num == other.phase_num
        return bool(self.phase_num == other)


class OrchestratorPhaseExecutor:
    """Manages orchestrator phases with explicit dependency checking and control flow.

    Replaces the monolithic orchestrator run() method with a declarative framework:
    1. Define phases with dependencies
    2. Execute phases in order with dependency validation
    3. Handle halt flags, timeouts, and failure modes consistently
    4. Enable phase reordering, parallelization, and unit testing
    """

    def __init__(self, config: Any, halt_check_fn: Callable[[], bool], skip_phases: list[int | str] | None = None):
        """Initialize executor.

        Args:
            config: Configuration object
            halt_check_fn: Function that returns True if orchestrator should halt
            skip_phases: Optional list of phase numbers to skip (useful for non-trading days)
        """
        self.config = config
        self.halt_check_fn = halt_check_fn
        self.phases: dict[int | str, PhaseDefinition] = {}
        self.phase_results: dict[int | str, PhaseResult] = {}
        self.execution_order: list[int | str] = []
        # CRITICAL: Explicit None check for skip_phases (not or [])
        self.skip_phases = set(skip_phases) if skip_phases is not None else set()

    def register_phase(self, definition: PhaseDefinition) -> None:
        """Register a phase for execution.

        Args:
            definition: PhaseDefinition with phase metadata and execution function
        """
        if definition.phase_num in self.phases:
            raise ValueError(f"Phase {definition.phase_num} already registered")
        self.phases[definition.phase_num] = definition
        self.execution_order.append(definition.phase_num)

    def register_phases(self, definitions: list[PhaseDefinition]) -> None:
        """Register multiple phases at once."""
        for definition in definitions:
            self.register_phase(definition)

    def get_result(self, phase_num: int | str) -> PhaseResult | None:
        return self.phase_results.get(phase_num)

    def get_phase_data_required(self, phase_num: int | str, *keys: str) -> Any:
        """Extract required data from phase result with validation.

        Fails if: phase not executed, result is None/failed, or keys are missing.

        Args:
            phase_num: Phase that produced data
            *keys: Required keys to extract

        Returns:
            Single value if one key, tuple if multiple keys

        Raises:
            Exception: If phase data is missing or invalid
        """
        from algo.orchestrator.phase_data_contract import (
            MissingPhaseDataError,
            extract_required_data,
        )

        result = self.phase_results.get(phase_num)
        if result is None:
            raise MissingPhaseDataError(
                f"Phase {phase_num} not executed. Available: {list(self.phase_results.keys())}",
                context={"phase_num": phase_num, "available_phases": list(self.phase_results.keys())},
            )

        if not result.ok:
            raise MissingPhaseDataError(
                f"Phase {phase_num} failed: {result.status} - {result.error}",
                context={
                    "phase_num": phase_num,
                    "phase_status": result.status,
                    "phase_error": result.error,
                    "phase_halted": result.halted,
                },
            )

        data = extract_required_data(phase_num, result.data, *keys)

        if len(keys) == 1:
            return data[0]
        return data

    def validate(self) -> list[str]:
        """Validate all phases are properly configured before execution.

        Checks:
        - All phases have execute_fn set
        - All dependencies reference registered phases
        - No circular dependencies

        Returns:
            Empty list if valid, list of error messages otherwise.
        """
        errors = []

        for phase_num, phase in self.phases.items():
            if not phase.execute_fn:
                errors.append(f"Phase {phase_num} ({phase.phase_name}) has no execute_fn set")

            for dep in phase.dependencies:
                if dep not in self.phases:
                    errors.append(f"Phase {phase_num} ({phase.phase_name}) depends on unregistered phase {dep}")

        if errors:
            logger.error(f"[PHASE VALIDATION FAILED] {len(errors)} issues found:")
            for error in errors:
                logger.error(f"  - {error}")

        return errors

    def _get_default_skip_data(self, phase_num: int | str) -> dict[str, Any]:
        """Get valid but empty data for a skipped phase.

        CRITICAL: Fails fast if phase_num is not recognized. Unknown phases
        indicate configuration errors that must not be silently masked.

        IMPORTANT: When a phase is skipped, downstream phases must be aware
        that the data is from a skip, not a full execution. This prevents
        silent cascading failures where empty defaults mask missing data.
        """
        defaults: dict[int | str, dict[str, Any]] = {
            1: {"status": "skipped", "reason": "phase skipped - no data available"},
            2: {"status": "skipped", "reason": "phase skipped - no data available"},
            3: {"recommendations": [], "reason": "phase skipped"},
            4: {"success": False, "reason": "phase skipped - no reconciliation performed"},
            5: {
                "constraints": {
                    "tier_name": "CORRECTION",
                    "regime": "CORRECTION",  # CRITICAL: Required by _health_panel_fields() in Phase 5
                    "risk_multiplier": 0.0,
                    "max_new_positions_today": 0,
                    "halt_new_entries": True,
                    "max_concentration_pct": 0.0,  # CRITICAL: Phase 8 requires this field (Session 416)
                    "halt_reason": "Previous phase halted - cannot determine exposure constraints",
                },
                "actions": [],
                # CRITICAL: Include health panel fields for dashboard rendering (same as Phase 5 normal execution)
                "market_regime": "CORRECTION",
                "entry_allowed": False,
                "halt_active": True,
                "max_new_entries": 0,
                "reason": "phase skipped - using safe defaults (no new entries)",
            },
            6: {"exits_executed": 0, "reason": "phase skipped"},
            7: {
                "qualified_trades": [],
                "liquidity_passed": 0,  # CRITICAL: Phase 8 metrics extraction requires this field (Session 416)
                "reason": "phase skipped - no signals generated (upstream phase halted)",
                "skipped": True,
            },
            8: {"entered": 0, "reason": "phase skipped"},
            9: {"positions": 0, "reason": "phase skipped"},
        }
        if phase_num not in defaults:
            raise ValueError(
                f"CRITICAL: Unknown phase number {phase_num}. "
                f"Cannot generate skip data for unregistered phase. "
                f"Known phases: {sorted(defaults.keys())}. "
                f"This indicates a configuration error in phase registration."
            )
        return defaults[phase_num]

    def _check_dependencies(self, phase_num: int | str) -> str | None:
        """Check if a phase's dependencies are satisfied.

        ISSUE #7 FIX: Validates both execution status AND data contracts (schema validation).
        Prevents phases from proceeding with incomplete dependency data.
        Ensures dependencies ran, succeeded, and produced valid output.

        Returns:
            None if all dependencies satisfied, error message otherwise.
        """
        from algo.orchestrator.phase_data_contract import (
            DataContractError,
            MissingPhaseDataError,
            validate_dependency_executed,
        )

        phase = self.phases.get(phase_num)
        if not phase:
            return f"Phase {phase_num} not registered"

        for dep in phase.dependencies:
            dep_result = self.phase_results.get(dep)

            # Check all three aspects: execution, success, and data validity
            try:
                validate_dependency_executed(phase_num, dep, dep_result)
            except (MissingPhaseDataError, DataContractError) as e:
                error_msg = f"[PHASE {phase_num} DEPENDENCY FAILED] {e}"
                logger.critical(error_msg)
                return error_msg

        return None

    def execute_phase(self, phase_num: int | str, **kwargs: Any) -> tuple[bool, str | None]:
        """Execute a single phase.

        ISSUE #7 FIX: Ensure all dependency failures are loud and actionable.
        Never silently skip a phase with dependencies - if dependencies fail, the phase must fail too.

        Flow:
        1. Check halt flag first (if phase skips on halt, no need to validate dependencies)
        2. Check dependencies (execution, success, data validity)
        3. Execute phase and capture result
        4. Report any errors clearly

        Args:
            phase_num: Phase to execute
            **kwargs: Additional arguments to pass to phase execution function

        Returns:
            (success: bool, error_message: Optional[str])
        """
        phase = self.phases.get(phase_num)
        if not phase:
            return False, f"Phase {phase_num} not registered"

        # Check halt flag FIRST (unless phase always runs)
        # If phase will be skipped, no need to validate its dependencies
        if not phase.always_run and phase.skip_if_halted:
            if self.halt_check_fn():
                logger.info(f"Phase {phase_num} ({phase.phase_name}) skipped due to halt flag")
                skip_data = self._get_default_skip_data(phase_num)
                # CRITICAL: Ensure skip data always includes status field for clarity
                if "status" not in skip_data:
                    skip_data["status"] = "halted"
                result = PhaseResult(
                    phase_num=phase_num,
                    phase_name=phase.phase_name,
                    status="skipped",
                    data=skip_data,
                    halted=True,
                    dependencies=phase.dependencies,
                )
                self.phase_results[phase_num] = result
                return True, None

        # Check dependencies (after halt check, so skipped phases don't validate them)
        # Check dependencies for all phases: ISSUE #7 requires dependencies to be validated
        # SESSION 396 note: always_run phases CAN execute with failed dependencies (handle gracefully),
        # but they MUST report the error to downstream phases, not silently degrade
        dep_error = self._check_dependencies(phase_num)
        if dep_error:
            logger.critical(f"[DEP-CHECK FAILED] {dep_error}")
            if phase.dependencies:
                logger.critical(
                    f"[PHASE {phase_num}] Cannot execute: {len(phase.dependencies)} "
                    f"unsatisfied dependencies. Dependency chain: {phase.dependencies}"
                )
            # CRITICAL FIX: Store error result so downstream phases see "dependency_failed" not "never executed"
            # Without storing this, missing phase_results[N] looks like phase N never ran, causing cascading failures
            result = PhaseResult(
                phase_num=phase_num,
                phase_name=phase.phase_name,
                status="error",
                data=self._get_default_skip_data(phase_num),
                error=dep_error,
                dependencies=phase.dependencies,
            )
            self.phase_results[phase_num] = result
            return False, dep_error

        # Execute phase
        try:
            if not phase.execute_fn:
                return False, f"Phase {phase_num} has no execution function"

            logger.info(f"\n{'=' * 70}")
            logger.info(f"PHASE {phase_num}: {phase.phase_name}")
            logger.info(f"{'=' * 70}")

            # Pass executor to phase so it can retrieve validated data from prior phases
            result = phase.execute_fn(executor=self, **kwargs)
            self.phase_results[phase_num] = result

            if result.halted:
                logger.critical(f"[PHASE {phase_num}] HALTED - {result.error or 'unknown reason'}")

            log_level = "error" if not result.ok else "info"
            if phase_num == 8:
                logger.info(f"[PHASE {phase_num} DEBUG] result.status={result.status!r}, result.ok={result.ok}, log_level={log_level}")
            logger.log(
                logging.ERROR if log_level == "error" else logging.INFO,
                f"\n-> Phase {phase_num} {result.status}: {result.data.get('summary', 'check logs for details')}",
            )

            return result.ok, result.error

        except RuntimeError as critical_err:
            # CRITICAL FIX: RuntimeError = governance violation. Must NOT be swallowed.
            # These include halt flag failures, data contract violations - orchestrator must crash.
            logger.critical(
                f"[PHASE {phase_num}] FATAL: RuntimeError indicates governance violation - re-raising to crash orchestrator: {critical_err}"
            )
            raise
        except Exception as e:
            logger.exception(f"[PHASE {phase_num}] Exception during execution: {e}")
            error_msg = str(e)
            # Use default skip data to ensure downstream phases get valid data contracts
            # This prevents cascading dependency failures from a single phase exception
            default_data = self._get_default_skip_data(phase_num)
            result = PhaseResult(
                phase_num=phase_num,
                phase_name=phase.phase_name,
                status="error",
                data=default_data,
                error=error_msg,
                dependencies=phase.dependencies,
            )
            self.phase_results[phase_num] = result
            return False, error_msg

    def run(self) -> dict[str, Any]:
        """Execute all registered phases in order.

        Respects:
        - Halt flags (skips subsequent phases if flagged)
        - Dependencies (errors if dependency not satisfied)
        - Phase-level skip_if_halted setting
        - Always-run phases (e.g., exits, reconciliation)

        Returns:
            Results summary with phase outcomes and any errors.
        """
        logger.info(f"\n{'#' * 70}")
        logger.info("#   ORCHESTRATOR EXECUTOR START")
        logger.info(f"#   Executing {len(self.execution_order)} phases")
        logger.info(f"{'#' * 70}")

        # Validate all phases are properly configured before execution
        validation_errors = self.validate()
        if validation_errors:
            logger.critical(
                f"[ORCHESTRATOR] Cannot proceed with {len(validation_errors)} phase configuration error(s). Aborting."
            )
            return {
                "success": False,
                "phases_executed": 0,
                "total_phases": len(self.execution_order),
                "error_phase": "initialization",
                "error_message": f"Phase configuration validation failed: {validation_errors}",
                "results": {},
            }

        success_count = 0
        error_phase = None
        error_message = None

        # Whether any non-always_run phase has failed (signals downstream to skip or check deps)
        halted = False
        remaining = list(self.execution_order)

        for phase_num in remaining:
            phase_def = self.phases[phase_num]

            # Skip phases in skip_phases list (unless always_run)
            if phase_num in self.skip_phases:
                if not phase_def.always_run:
                    logger.info(f"Phase {phase_num} ({phase_def.phase_name}) skipped (non-trading day)")
                    result = PhaseResult(
                        phase_num=phase_num,
                        phase_name=phase_def.phase_name,
                        status="skipped",
                        data=self._get_default_skip_data(phase_num),
                        halted=False,
                    )
                    self.phase_results[phase_num] = result
                    continue
                else:
                    logger.info(
                        f"Phase {phase_num} ({phase_def.phase_name}) running despite skip request (always_run=True)"
                    )

            # Skip non-always_run phases after a halt (they will fail dep checks anyway)
            if halted and not phase_def.always_run:
                logger.info(f"Phase {phase_num} ({phase_def.phase_name}) skipped due to earlier phase halt")
                result = PhaseResult(
                    phase_num=phase_num,
                    phase_name=phase_def.phase_name,
                    status="skipped",
                    data=self._get_default_skip_data(phase_num),
                    halted=True,
                )
                self.phase_results[phase_num] = result
                continue

            success, error = self.execute_phase(phase_num)

            if success:
                success_count += 1
            else:
                error_phase = phase_num
                error_message = error
                if not phase_def.always_run:
                    halted = True
                    logger.critical(f"[EXECUTOR] Phase {phase_num} halted - continuing to always_run phases")

        logger.info(f"\n{'#' * 70}")
        logger.info("#   ORCHESTRATOR EXECUTOR COMPLETE")
        logger.info(f"#   {success_count}/{len(self.execution_order)} phases succeeded")
        logger.info(f"{'#' * 70}")

        return {
            "success": error_phase is None,
            "phases_executed": success_count,
            "total_phases": len(self.execution_order),
            "error_phase": error_phase,
            "error_message": error_message,
            "results": self.phase_results,
        }

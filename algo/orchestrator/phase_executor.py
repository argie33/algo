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

    def __init__(self, config: Any, halt_check_fn: Callable[[], bool]):
        """Initialize executor.

        Args:
            config: Configuration object
            halt_check_fn: Function that returns True if orchestrator should halt
        """
        self.config = config
        self.halt_check_fn = halt_check_fn
        self.phases: dict[int | str, PhaseDefinition] = {}
        self.phase_results: dict[int | str, PhaseResult] = {}
        self.execution_order: list[int | str] = []

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
        """Get result from a previously executed phase."""
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
            raise MissingPhaseDataError(f"Phase {phase_num} not executed. Available: {list(self.phase_results.keys())}")

        if not result.ok:
            raise MissingPhaseDataError(f"Phase {phase_num} failed: {result.status} — {result.error}")

        data = extract_required_data(phase_num, result.data, *keys)

        if len(keys) == 1:
            return data[0]
        return data

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
        1. Check dependencies (execution, success, data validity)
        2. Check halt flag
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

        # ISSUE #7 FIX: Check dependencies BEFORE checking halt flag
        # Dependencies must be satisfied regardless of halt state
        dep_error = self._check_dependencies(phase_num)
        if dep_error:
            logger.critical(f"[DEP-CHECK FAILED] {dep_error}")
            if phase.dependencies:
                logger.critical(
                    f"[PHASE {phase_num}] BLOCKING: Cannot execute phase with {len(phase.dependencies)} "
                    f"unsatisfied dependencies. Dependency chain: {phase.dependencies}"
                )
            return False, dep_error

        # Check halt flag (unless phase always runs)
        if not phase.always_run and phase.skip_if_halted:
            if self.halt_check_fn():
                logger.info(f"Phase {phase_num} ({phase.phase_name}) skipped due to halt flag")
                result = PhaseResult(
                    phase_num=phase_num,
                    phase_name=phase.phase_name,
                    status="skipped",
                    halted=True,
                    dependencies=phase.dependencies,
                )
                self.phase_results[phase_num] = result
                return True, None

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
                logger.critical(f"[PHASE {phase_num}] HALTED — {result.error or 'unknown reason'}")

            log_level = "error" if not result.ok else "info"
            logger.log(
                logging.ERROR if log_level == "error" else logging.INFO,
                f"\n-> Phase {phase_num} {result.status}: {result.data.get('summary', 'check logs for details')}",
            )

            return result.ok, result.error

        except Exception as e:
            logger.exception(f"[PHASE {phase_num}] Exception during execution: {e}")
            error_msg = str(e)
            result = PhaseResult(
                phase_num=phase_num,
                phase_name=phase.phase_name,
                status="error",
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

        success_count = 0
        error_phase = None
        error_message = None

        # Whether any non-always_run phase has failed (signals downstream to skip or check deps)
        halted = False
        remaining = list(self.execution_order)

        for phase_num in remaining:
            phase_def = self.phases[phase_num]

            # Skip non-always_run phases after a halt (they will fail dep checks anyway)
            if halted and not phase_def.always_run:
                logger.info(f"Phase {phase_num} ({phase_def.phase_name}) skipped due to earlier phase halt")
                result = PhaseResult(
                    phase_num=phase_num,
                    phase_name=phase_def.phase_name,
                    status="skipped",
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
                    logger.critical(f"[EXECUTOR] Phase {phase_num} halted — continuing to always_run phases")

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

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

    def __hash__(self):
        return hash((self.phase_num, self.phase_name))

    def __eq__(self, other):
        if isinstance(other, PhaseDefinition):
            return self.phase_num == other.phase_num
        return self.phase_num == other


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

    def get_phase_data(
        self, phase_num: int | str, key: str, default: Any = None
    ) -> Any:
        """Convenience method to get specific data from a phase result.

        DEPRECATED: Use get_phase_data_required() for explicit validation.
        This method silently returns default, hiding missing dependencies.
        """
        result = self.phase_results.get(phase_num)
        if result:
            return result.data.get(key, default)
        return default

    def get_phase_data_required(
        self, phase_num: int | str, *keys: str
    ) -> Any:
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
                f"Phase {phase_num} not executed. Available: {list(self.phase_results.keys())}"
            )

        if not result.ok:
            raise MissingPhaseDataError(
                f"Phase {phase_num} failed: {result.status} — {result.error}"
            )

        data = extract_required_data(phase_num, result.data, *keys)

        if len(keys) == 1:
            return data[0]
        return data

    def _check_dependencies(self, phase_num: int | str) -> str | None:
        """Check if a phase's dependencies are satisfied.

        Validates both execution status AND data contracts (schema validation).
        Prevents phases from proceeding with incomplete dependency data.

        Returns:
            None if all dependencies satisfied, error message otherwise.
        """
        from algo.orchestrator.phase_data_contract import (
            DataContractError,
            validate_phase_data,
        )

        phase = self.phases.get(phase_num)
        if not phase:
            return f"Phase {phase_num} not registered"

        for dep in phase.dependencies:
            dep_result = self.phase_results.get(dep)
            if not dep_result:
                return f"Phase {phase_num} requires Phase {dep} (not executed)"
            if not dep_result.ok:
                return f"Phase {phase_num} requires Phase {dep} (status: {dep_result.status})"

            # CRITICAL: Validate dependency produced valid data schema
            try:
                validate_phase_data(dep, dep_result.data)
            except DataContractError as e:
                return f"Phase {phase_num} dependency {dep} data invalid: {e}"

        return None

    def execute_phase(
        self, phase_num: int | str, **kwargs
    ) -> tuple[bool, str | None]:
        """Execute a single phase.

        Args:
            phase_num: Phase to execute
            **kwargs: Additional arguments to pass to phase execution function

        Returns:
            (success: bool, error_message: Optional[str])
        """
        phase = self.phases.get(phase_num)
        if not phase:
            return False, f"Phase {phase_num} not registered"

        # Check halt flag (unless phase always runs)
        if not phase.always_run and phase.skip_if_halted:
            if self.halt_check_fn():
                logger.info(
                    f"Phase {phase_num} ({phase.phase_name}) skipped due to halt flag"
                )
                result = PhaseResult(
                    phase_num=phase_num,
                    phase_name=phase.phase_name,
                    status="skipped",
                    halted=True,
                    dependencies=phase.dependencies,
                )
                self.phase_results[phase_num] = result
                return True, None

        # Check dependencies
        dep_error = self._check_dependencies(phase_num)
        if dep_error:
            logger.critical(f"[DEP-CHECK] {dep_error}")
            return False, dep_error

        # Execute phase
        try:
            if not phase.execute_fn:
                return False, f"Phase {phase_num} has no execution function"

            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE {phase_num}: {phase.phase_name}")
            logger.info(f"{'='*70}")

            # Pass executor to phase so it can retrieve validated data from prior phases
            result = phase.execute_fn(executor=self, **kwargs)
            self.phase_results[phase_num] = result

            if result.halted:
                logger.critical(
                    f"[PHASE {phase_num}] HALTED — {result.error or 'unknown reason'}"
                )

            log_level = "error" if not result.ok else "info"
            logger.log(
                logging.ERROR if log_level == "error" else logging.INFO,
                f"\n-> Phase {phase_num} {result.status}: "
                f"{result.data.get('summary', 'check logs for details')}",
            )

            return result.ok, result.error

        except Exception as e:
            logger.exception(f"[PHASE {phase_num}] Exception during execution: {e}")
            result = PhaseResult(
                phase_num=phase_num,
                phase_name=phase.phase_name,
                status="error",
                error=str(e),
                dependencies=phase.dependencies,
            )
            self.phase_results[phase_num] = result
            return False, str(e)

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
        logger.info(f"\n{'#'*70}")
        logger.info("#   ORCHESTRATOR EXECUTOR START")
        logger.info(f"#   Executing {len(self.execution_order)} phases")
        logger.info(f"{'#'*70}")

        success_count = 0
        error_phase = None
        error_message = None

        for phase_num in self.execution_order:
            success, error = self.execute_phase(phase_num)

            if success:
                success_count += 1
            else:
                error_phase = phase_num
                error_message = error
                # Continue to always_run phases (e.g., exits, reconciliation)
                # Stop at first dependency-blocking error
                phase_def = self.phases[phase_num]
                if not phase_def.always_run:
                    logger.critical(
                        f"[EXECUTOR] Halting phase sequence at Phase {phase_num}: {error}"
                    )
                    break

        logger.info(f"\n{'#'*70}")
        logger.info("#   ORCHESTRATOR EXECUTOR COMPLETE")
        logger.info(f"#   {success_count}/{len(self.execution_order)} phases succeeded")
        logger.info(f"{'#'*70}")

        return {
            "success": error_phase is None,
            "phases_executed": success_count,
            "total_phases": len(self.execution_order),
            "error_phase": error_phase,
            "error_message": error_message,
            "results": self.phase_results,
        }

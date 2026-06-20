#!/usr/bin/env python3
"""Tests for phase dependency validation and data contracts.

Verifies that:
1. Phases fail explicitly if dependencies are missing
2. Phase data contracts are validated
3. No silent getattr() defaults hide failures
"""

import pytest
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import PhaseResult
from algo.orchestrator.phase_data_contract import (
    DataContractError,
    MissingPhaseDataError,
)


class TestPhaseDependencyValidation:
    """Test explicit phase dependency validation."""

    def test_missing_dependency_raises_error(self):
        """Phase 4 should fail if Phase 3 hasn't run yet."""
        executor = OrchestratorPhaseExecutor(config=None, halt_check_fn=lambda: False)

        def phase_4_fn(executor=None, **kwargs):
            """Try to retrieve Phase 3 data that doesn't exist."""
            if executor is None:
                return PhaseResult(4, "test", "error", {}, True, "No executor")
            try:
                position_recs = executor.get_phase_data_required(3, "recommendations")
                return PhaseResult(
                    4, "test", "ok", {"positions": position_recs}, False, None
                )
            except MissingPhaseDataError as e:
                return PhaseResult(4, "test", "error", {}, True, str(e))

        executor.register_phase(
            PhaseDefinition(
                phase_num=4,
                phase_name="TEST_PHASE_4",
                dependencies=[3],
                execute_fn=phase_4_fn,
            )
        )

        # Execute Phase 4 should fail because Phase 3 hasn't run
        success, error = executor.execute_phase(4)
        assert not success, "Phase 4 should fail if Phase 3 doesn't exist"
        assert "Phase 3" in error, f"Error should mention Phase 3 dependency: {error}"

    def test_phase_data_required_extracts_single_value(self):
        """get_phase_data_required should extract single values correctly."""
        executor = OrchestratorPhaseExecutor(config=None, halt_check_fn=lambda: False)

        # Manually set up Phase 3 result with data
        phase3_result = PhaseResult(
            3, "POSITION_MONITOR", "ok", {"recommendations": ["rec1", "rec2"]}
        )
        executor.phase_results[3] = phase3_result

        # Extract recommendations
        recs = executor.get_phase_data_required(3, "recommendations")
        assert recs == ["rec1", "rec2"]

    def test_phase_data_required_fails_on_missing_key(self):
        """get_phase_data_required should fail if required key is missing."""
        executor = OrchestratorPhaseExecutor(config=None, halt_check_fn=lambda: False)

        # Set up Phase 3 with incomplete data
        phase3_result = PhaseResult(3, "POSITION_MONITOR", "ok", {})
        executor.phase_results[3] = phase3_result

        # Try to extract non-existent key
        with pytest.raises(DataContractError):
            executor.get_phase_data_required(3, "recommendations")

    def test_phase_data_required_fails_if_phase_failed(self):
        """get_phase_data_required should fail if phase didn't complete successfully."""
        executor = OrchestratorPhaseExecutor(config=None, halt_check_fn=lambda: False)

        # Set up Phase 3 with failed status
        phase3_result = PhaseResult(
            3, "POSITION_MONITOR", "error", {"recommendations": []}, True, "Failed"
        )
        executor.phase_results[3] = phase3_result

        # Try to extract data from failed phase
        with pytest.raises(MissingPhaseDataError):
            executor.get_phase_data_required(3, "recommendations")

    def test_old_getattr_pattern_would_hide_failure(self):
        """Demonstrate that old getattr() pattern hides Phase 3 failure.

        This test shows why the fix was necessary: without explicit validation,
        Phase 4 would silently get an empty list and not know Phase 3 failed.
        """
        orchestrator_state = {"_position_recs": None}

        # Old pattern: silent default (BRITTLE - hides failure)
        position_recs = orchestrator_state.get("_position_recs") or []
        assert position_recs == []  # Appears OK but Phase 3 actually failed!

        # New pattern: explicit check (SAFE - fails loudly)
        has_recs = "_position_recs" in orchestrator_state and orchestrator_state["_position_recs"] is not None
        assert not has_recs, "Should detect that _position_recs was not properly set by Phase 3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""Test Phase Dependency Validation: Verify Phase 7 detects when Phase 5 fails to provide constraints."""

import pytest

from algo.orchestrator.phase_data_contract import validate_phase_5_constraints
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import Phase5Result, Phase7Result


def test_phase_5_constraints_validation():
    """Test that Phase 5 constraints validation catches empty or invalid constraints."""
    with pytest.raises(Exception):
        validate_phase_5_constraints({})

    with pytest.raises(Exception):
        validate_phase_5_constraints({"tier_name": "NORMAL"})

    valid_constraints = {"tier_name": "NORMAL", "risk_multiplier": 1.0, "max_new_positions_today": 5}
    validate_phase_5_constraints(valid_constraints)


def test_phase7_dependency_validation():
    """Phase 7 must detect when Phase 5 fails to provide exposure constraints."""
    class MockOrch:
        pass

    mock_orch = MockOrch()
    assert not hasattr(mock_orch, "_exposure_constraints")

    mock_orch._exposure_constraints = None
    with pytest.raises(Exception):
        validate_phase_5_constraints(mock_orch._exposure_constraints)

    mock_orch._exposure_constraints = {}
    with pytest.raises(Exception):
        validate_phase_5_constraints(mock_orch._exposure_constraints)

    mock_orch._exposure_constraints = {"tier_name": "NORMAL", "risk_multiplier": 1.0, "max_new_positions_today": 5}
    validate_phase_5_constraints(mock_orch._exposure_constraints)


def test_phase7_data_extraction():
    """Test that Phase 7 can extract exposure constraints from Phase 5."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    constraints = {
        "tier_name": "NORMAL",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 5,
        "halt_new_entries": False,
    }
    phase5_result = Phase5Result(status="ok", constraints=constraints, actions=[])
    executor.phase_results[5] = phase5_result

    extracted_constraints = executor.get_phase_data_required(5, "constraints")
    assert extracted_constraints == constraints

    with pytest.raises(Exception):
        executor.get_phase_data_required(5, "nonexistent_key")

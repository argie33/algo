#!/usr/bin/env python3
"""Test Phase Executor Dependency Validation: Verify the executor enforces dependencies."""

from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import PhaseResult


def test_executor_detects_missing_dependency():
    """Executor must fail phase if dependency never ran."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    def phase7_fn(**kwargs):
        return PhaseResult(phase_num=7, phase_name="SIGNAL GENERATION", status="ok", data={})

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    success, error = executor.execute_phase(7)
    assert not success
    assert "Phase 7" in error
    assert "Phase 5" in error
    assert "never executed" in error


def test_executor_detects_failed_dependency():
    """Executor must fail phase if dependency failed."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    phase5_result = PhaseResult(
        phase_num=5,
        phase_name="EXPOSURE POLICY",
        status="error",
        data={},
        error="Phase 5 failed due to bad constraints",
    )
    executor.phase_results[5] = phase5_result

    def phase7_fn(**kwargs):
        return PhaseResult(phase_num=7, phase_name="SIGNAL GENERATION", status="ok", data={})

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    success, error = executor.execute_phase(7)
    assert not success
    assert "Phase 7" in error
    assert "Phase 5" in error
    assert "failed" in error.lower()


def test_executor_detects_invalid_dependency_data():
    """Executor must fail phase if dependency produced missing data keys."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    phase5_result = PhaseResult(
        phase_num=5,
        phase_name="EXPOSURE POLICY",
        status="ok",
        data={},
        dependencies=[],
    )
    executor.phase_results[5] = phase5_result

    def phase7_fn(**kwargs):
        return PhaseResult(phase_num=7, phase_name="SIGNAL GENERATION", status="ok", data={})

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    success, error = executor.execute_phase(7)
    assert not success
    assert "constraints" in error
    assert "missing" in error.lower()


def test_executor_allows_valid_dependency():
    """Executor must allow phase execution with valid dependency."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    constraints = {
        "tier_name": "NORMAL",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 5,
    }
    phase5_result = PhaseResult(
        phase_num=5,
        phase_name="EXPOSURE POLICY",
        status="ok",
        data={"constraints": constraints},
    )
    executor.phase_results[5] = phase5_result

    phase7_executed = False

    def phase7_fn(**kwargs):
        nonlocal phase7_executed
        phase7_executed = True
        return PhaseResult(phase_num=7, phase_name="SIGNAL GENERATION",status="ok", qualified_trades=[])

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    success, _error = executor.execute_phase(7)
    assert success
    assert phase7_executed


def test_executor_validates_all_dependencies():
    """Executor must validate all dependencies in dependency chain."""
    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    def phase8_fn(**kwargs):
        return PhaseResult(phase_num=8, phase_name="ENTRY", status="ok")

    executor.register_phase(
        PhaseDefinition(
            phase_num=8,
            phase_name="ENTRY EXECUTION",
            dependencies=[7, 5],
            execute_fn=phase8_fn,
        )
    )

    phase5_result = PhaseResult(
        phase_num=5,
        phase_name="EXPOSURE POLICY",
        status="ok",
        data={
            "constraints": {
                "tier_name": "NORMAL",
                "risk_multiplier": 1.0,
                "max_new_positions_today": 5,
            }
        },
    )
    executor.phase_results[5] = phase5_result

    success, error = executor.execute_phase(8)
    assert not success
    assert "Phase 7" in error
    assert "never executed" in error

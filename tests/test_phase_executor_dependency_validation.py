#!/usr/bin/env python3
"""
Test Phase Executor Dependency Validation: Verify the executor enforces dependencies.

This test ensures that the OrchestratorPhaseExecutor properly validates:
1. Dependencies executed (not None)
2. Dependencies succeeded (ok status)
3. Dependencies produced valid data (schema validation)
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase_data_contract import (
    DataContractError,
    MissingPhaseDataError,
)
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import PhaseResult, Phase5Result, Phase7Result


def test_executor_detects_missing_dependency():
    """Test that executor fails phase if dependency never ran."""
    print("\n" + "=" * 80)
    print("TEST: Executor Detects Missing Dependency")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Phase 7 depends on Phase 5
    def phase7_fn(**kwargs):
        return Phase7Result(status="ok", qualified_trades=[])

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    # Phase 5 never executed - phase_results is empty
    # Now try to execute Phase 7
    success, error = executor.execute_phase(7)

    if not success and "Phase 7" in error and "Phase 5" in error and "never executed" in error:
        print(f"[PASS] Executor correctly blocked Phase 7: {error}")
        return True
    else:
        print(f"[FAIL] Expected Phase 7 to be blocked. Got: success={success}, error={error}")
        return False


def test_executor_detects_failed_dependency():
    """Test that executor fails phase if dependency failed."""
    print("\n" + "=" * 80)
    print("TEST: Executor Detects Failed Dependency")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Phase 5 fails
    phase5_result = Phase5Result(
        status="error",
        error="Phase 5 failed due to bad constraints",
        constraints=None,
        actions=[],
    )
    executor.phase_results[5] = phase5_result

    # Phase 7 depends on Phase 5
    def phase7_fn(**kwargs):
        return Phase7Result(status="ok", qualified_trades=[])

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    # Try to execute Phase 7
    success, error = executor.execute_phase(7)

    if not success and "Phase 7" in error and "Phase 5" in error and "failed" in error.lower():
        print(f"[PASS] Executor correctly blocked Phase 7 due to Phase 5 failure: {error}")
        return True
    else:
        print(f"[FAIL] Expected Phase 7 to be blocked. Got: success={success}, error={error}")
        return False


def test_executor_detects_invalid_dependency_data():
    """Test that executor fails phase if dependency produced missing data keys.

    Note: For Phase 5, the full schema validation (including constraints content)
    happens via validate_phase_5_constraints() in the phase's business logic.
    The executor validates that the 'constraints' key exists, but the actual
    constraint content validation happens separately.
    """
    print("\n" + "=" * 80)
    print("TEST: Executor Detects Invalid Dependency Data (missing required keys)")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Phase 5 succeeds but with completely invalid data (missing 'constraints' key entirely)
    phase5_result = PhaseResult(
        phase_num=5,
        phase_name="EXPOSURE POLICY",
        status="ok",
        data={},  # MISSING constraints key entirely!
        dependencies=[],
    )
    executor.phase_results[5] = phase5_result

    # Phase 7 depends on Phase 5
    def phase7_fn(**kwargs):
        return Phase7Result(status="ok", qualified_trades=[])

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    # Try to execute Phase 7
    success, error = executor.execute_phase(7)

    if not success and "constraints" in error and "missing" in error.lower():
        print(f"[PASS] Executor correctly blocked Phase 7 due to missing Phase 5 constraints key: {error}")
        return True
    else:
        print(f"[FAIL] Expected Phase 7 to be blocked due to missing data key. Got: success={success}, error={error}")
        return False


def test_executor_allows_valid_dependency():
    """Test that executor allows phase execution with valid dependency."""
    print("\n" + "=" * 80)
    print("TEST: Executor Allows Valid Dependency")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Phase 5 succeeds with VALID data
    constraints = {
        "tier_name": "NORMAL",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 5,
    }
    phase5_result = Phase5Result(
        status="ok",
        constraints=constraints,
        actions=[],
    )
    executor.phase_results[5] = phase5_result

    # Phase 7 depends on Phase 5
    phase7_executed = False

    def phase7_fn(**kwargs):
        nonlocal phase7_executed
        phase7_executed = True
        return Phase7Result(status="ok", qualified_trades=[])

    executor.register_phase(
        PhaseDefinition(
            phase_num=7,
            phase_name="SIGNAL GENERATION",
            dependencies=[5],
            execute_fn=phase7_fn,
        )
    )

    # Execute Phase 7
    success, error = executor.execute_phase(7)

    if success and phase7_executed:
        print(f"[PASS] Executor correctly allowed Phase 7 execution")
        return True
    else:
        print(f"[FAIL] Expected Phase 7 to execute. Got: success={success}, executed={phase7_executed}, error={error}")
        return False


def test_executor_validates_all_dependencies():
    """Test that executor validates all dependencies in dependency chain."""
    print("\n" + "=" * 80)
    print("TEST: Executor Validates All Dependencies")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Phase 8 depends on Phase 7 and Phase 5
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

    # Only Phase 5 exists, Phase 7 is missing
    phase5_result = Phase5Result(
        status="ok",
        constraints={"tier_name": "NORMAL", "risk_multiplier": 1.0, "max_new_positions_today": 5},
        actions=[],
    )
    executor.phase_results[5] = phase5_result

    # Try to execute Phase 8
    success, error = executor.execute_phase(8)

    if not success and "Phase 7" in error and "never executed" in error:
        print(f"[PASS] Executor correctly detected missing Phase 7 in dependency chain: {error}")
        return True
    else:
        print(f"[FAIL] Expected Phase 8 to be blocked due to missing Phase 7. Got: success={success}, error={error}")
        return False


if __name__ == "__main__":
    results = []

    results.append(("Missing Dependency Detection", test_executor_detects_missing_dependency()))
    results.append(("Failed Dependency Detection", test_executor_detects_failed_dependency()))
    results.append(("Invalid Data Detection", test_executor_detects_invalid_dependency_data()))
    results.append(("Valid Dependency Allowed", test_executor_allows_valid_dependency()))
    results.append(("All Dependencies Validated", test_executor_validates_all_dependencies()))

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")

    all_passed = all(result for _, result in results)
    sys.exit(0 if all_passed else 1)

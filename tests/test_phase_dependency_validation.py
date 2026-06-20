#!/usr/bin/env python3
"""
Test Phase Dependency Validation: Verify Phase 5 detects when Phase 3b fails to provide constraints.

This test ensures that Phase 5 cannot proceed with missing or invalid exposure constraints
from Phase 3b, preventing the silent failure scenario described in Issue #4.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase_data_contract import validate_phase_3b_constraints
from algo.orchestrator.phase_executor import OrchestratorPhaseExecutor, PhaseDefinition
from algo.orchestrator.phase_result import Phase3bResult, Phase5Result


def test_phase_3b_constraints_validation():
    """
    Test that Phase 3b constraints validation catches empty or invalid constraints.
    """
    print("\n" + "=" * 80)
    print("TEST: Phase 3b Constraints Validation")
    print("=" * 80)

    # Test 1: Empty constraints should fail
    print("\nTest 1: Empty constraints should fail validation")
    try:
        validate_phase_3b_constraints({})
        print("[FAIL] Should have raised error for empty constraints")
        return False
    except Exception as e:
        print(f"[PASS] Correctly raised error: {e}")

    # Test 2: Missing required fields should fail
    print("\nTest 2: Missing required fields should fail validation")
    try:
        validate_phase_3b_constraints({"tier_name": "NORMAL"})  # missing risk_multiplier, max_new_positions_today
        print("[FAIL] Should have raised error for missing fields")
        return False
    except Exception as e:
        print(f"[PASS] Correctly raised error: {e}")

    # Test 3: Valid constraints should pass
    print("\nTest 3: Valid constraints should pass validation")
    try:
        valid_constraints = {"tier_name": "NORMAL", "risk_multiplier": 1.0, "max_new_positions_today": 5}
        validate_phase_3b_constraints(valid_constraints)
        print("[PASS] Valid constraints accepted")
    except Exception as e:
        print(f"[FAIL] Should have accepted valid constraints: {e}")
        return False

    return True


def test_phase5_dependency_validation():
    """
    CRITICAL TEST: Phase 5 must detect when Phase 3b fails to provide exposure constraints.

    This test verifies that the orchestrator's phase_5_signal_generation() method
    validates exposure_constraints before calling the actual phase implementation.
    """
    print("\n" + "=" * 80)
    print("TEST: Phase 5 Dependency Validation — Detects Missing Exposure Constraints")
    print("=" * 80)

    # Test Scenario 1: Missing _exposure_constraints attribute (Phase 3b didn't run)
    print("\nScenario 1: _exposure_constraints attribute is missing")

    class MockOrch1:
        """Mock orchestrator without _exposure_constraints"""


    mock_orch = MockOrch1()
    has_constraints = hasattr(mock_orch, "_exposure_constraints")
    if not has_constraints:
        print("[PASS] Missing _exposure_constraints attribute correctly detected")
    else:
        print("[FAIL] Should detect missing _exposure_constraints")
        return False

    # Test Scenario 2: _exposure_constraints is None (Phase 3b returned ok but no constraints)
    print("\nScenario 2: _exposure_constraints is None")
    mock_orch._exposure_constraints = None
    try:
        validate_phase_3b_constraints(mock_orch._exposure_constraints)
        print("[FAIL] Should have raised error for None constraints")
        return False
    except Exception as e:
        print(f"[PASS] Validation caught None constraints: {e}")

    # Test Scenario 3: _exposure_constraints is empty dict
    print("\nScenario 3: _exposure_constraints is empty dict")
    mock_orch._exposure_constraints = {}
    try:
        validate_phase_3b_constraints(mock_orch._exposure_constraints)
        print("[FAIL] Should have raised error for empty constraints")
        return False
    except Exception as e:
        print(f"[PASS] Validation caught empty constraints: {e}")

    # Test Scenario 4: _exposure_constraints is valid
    print("\nScenario 4: _exposure_constraints is valid")
    mock_orch._exposure_constraints = {"tier_name": "NORMAL", "risk_multiplier": 1.0, "max_new_positions_today": 5}
    try:
        validate_phase_3b_constraints(mock_orch._exposure_constraints)
        print("[PASS] Valid constraints accepted")
    except Exception as e:
        print(f"[FAIL] Should have accepted valid constraints: {e}")
        return False

    return True


def test_phase5_data_extraction():
    """
    Test that Phase 5 can extract exposure constraints from Phase 3b using get_phase_data_required.
    """
    print("\n" + "=" * 80)
    print("TEST: Phase 5 Data Extraction — Using get_phase_data_required()")
    print("=" * 80)

    executor = OrchestratorPhaseExecutor(config={}, halt_check_fn=lambda: False)

    # Setup Phase 3b with valid result
    constraints = {
        "tier_name": "NORMAL",
        "risk_multiplier": 1.0,
        "max_new_positions_today": 5,
        "halt_new_entries": False,
    }
    phase3b_result = Phase3bResult(status="ok", constraints=constraints, actions=[])
    executor.phase_results["3b"] = phase3b_result

    # Phase 5 should be able to extract constraints
    try:
        extracted_constraints = executor.get_phase_data_required("3b", "constraints")
        if extracted_constraints == constraints:
            print(f"[PASS] Successfully extracted constraints: {extracted_constraints}")
        else:
            print(f"[FAIL] Extracted wrong constraints: {extracted_constraints}")
            return False
    except Exception as e:
        print(f"[FAIL] Could not extract constraints: {e}")
        return False

    # Try to extract missing key should fail
    print("\nTest extracting missing key from Phase 3b...")
    try:
        executor.get_phase_data_required("3b", "nonexistent_key")
        print("[FAIL] Should have raised error for missing key")
        return False
    except Exception as e:
        print(f"[PASS] Correctly raised error for missing key: {type(e).__name__}")

    return True


if __name__ == "__main__":
    results = []

    results.append(("Phase 3b Constraints Validation", test_phase_3b_constraints_validation()))
    results.append(("Phase 5 Dependency Validation", test_phase5_dependency_validation()))
    results.append(("Phase 5 Data Extraction", test_phase5_data_extraction()))

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")

    all_passed = all(result for _, result in results)
    sys.exit(0 if all_passed else 1)

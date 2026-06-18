#!/usr/bin/env python3
"""Test that the modular data patrol architecture works correctly."""

import sys
from pathlib import Path


# Setup imports
root = Path(__file__).parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from algo.monitoring.data_patrol import DataPatrol
from algo.monitoring.data_patrol.base import BaseCheck, CheckResult
from algo.monitoring.data_patrol.checks import (
    AlignmentChecker,
    CoverageChecker,
    PriceSanityChecker,
    QualityChecker,
    SpecializedChecker,
    StalenessChecker,
)
from algo.monitoring.data_patrol.config import CRIT, ERROR, INFO, WARN, PatrolConfig


def test_imports():
    """Verify all modules import correctly."""
    print("OK - All imports successful")


def test_check_result():
    """Test CheckResult class."""
    result = CheckResult(
        check_name="test_check",
        severity=INFO,
        target_table="test_table",
        message="Test message",
        details={"key": "value"},
    )
    assert result.check_name == "test_check"
    assert result.severity == INFO
    assert result.to_dict()["check"] == "test_check"
    print("OK - CheckResult works correctly")


def test_patrol_config():
    """Test PatrolConfig initialization without DB."""
    config = PatrolConfig()
    assert config.get("nonexistent_key", 42) == 42
    staleness = config.get_staleness_windows()
    assert "price_daily" in staleness
    assert staleness["price_daily"] == 7  # default
    print("OK - PatrolConfig works correctly")


def test_check_instantiation():
    """Test that all check classes can be instantiated."""
    config = PatrolConfig()

    checkers = [
        StalenessChecker(config),
        QualityChecker(config),
        PriceSanityChecker(config),
        CoverageChecker(config),
        AlignmentChecker(config),
        SpecializedChecker(config),
    ]

    for checker in checkers:
        assert isinstance(checker, BaseCheck)
        assert hasattr(checker, "run")
        assert hasattr(checker, "results")
        assert len(checker.results) == 0

    print(f"OK - All {len(checkers)} check classes instantiate correctly")


def test_data_patrol_instantiation():
    """Test that DataPatrol can be instantiated."""
    patrol = DataPatrol()
    assert patrol.run_id == ""
    assert len(patrol.results) == 0
    print("OK - DataPatrol instantiates correctly")


def test_checker_logging():
    """Test that checkers can log results."""
    config = PatrolConfig()
    checker = StalenessChecker(config)

    checker.log("test_check", WARN, "test_table", "Test warning", {"detail": "value"})

    assert len(checker.results) == 1
    assert checker.results[0].check_name == "test_check"
    assert checker.results[0].severity == WARN
    print("OK - Checker logging works correctly")


def test_severity_constants():
    """Test severity level constants."""
    severities = [INFO, WARN, ERROR, CRIT]
    assert all(isinstance(s, str) for s in severities)
    assert INFO == "info"
    assert WARN == "warn"
    assert ERROR == "error"
    assert CRIT == "critical"
    print("OK - Severity constants correct")


def test_architecture_benefits():
    """Verify the modular architecture benefits."""
    config = PatrolConfig()

    # Can test individual checks in isolation
    staleness = StalenessChecker(config)
    quality = QualityChecker(config)

    # Each has independent results
    staleness.log("staleness_test", INFO, "table1", "msg1")
    quality.log("quality_test", WARN, "table2", "msg2")

    assert len(staleness.results) == 1
    assert len(quality.results) == 1
    assert staleness.results[0].check_name == "staleness_test"
    assert quality.results[0].check_name == "quality_test"

    print("OK - Modular checks are properly isolated")


def main():
    """Run all tests."""
    print("Testing modular data patrol architecture...\n")

    test_imports()
    test_check_result()
    test_patrol_config()
    test_check_instantiation()
    test_data_patrol_instantiation()
    test_checker_logging()
    test_severity_constants()
    test_architecture_benefits()

    print("\nSUCCESS - All tests passed! Modular architecture is working correctly.")


if __name__ == "__main__":
    main()

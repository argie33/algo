#!/usr/bin/env python3
"""
Test Market Regime Fail-Closed (Issue #4)

Verifies that when market_exposure_daily data is unavailable or inaccessible,
Phase 5 halts entries (fail-closed) instead of defaulting to permissive entry.
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase5_signal_generation import _check_market_regime


def test_market_regime_no_data_failclosed():
    """
    CRITICAL TEST: Market regime must fail-closed when no data available.
    Simulates case where market_exposure_daily table is empty or hasn't been populated.
    """
    print("\n" + "=" * 80)
    print("TEST: Market Regime - Fail-Closed When No Data Available")
    print("=" * 80)

    test_date = date(2026, 6, 19)

    with patch("algo.orchestrator.phase5_signal_generation.DatabaseContext") as mock_db_context:
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No market_exposure_daily data

        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_cursor
        mock_context_manager.__exit__.return_value = None

        mock_db_context.return_value = mock_context_manager

        # Call the market regime check
        regime = _check_market_regime(test_date)

    print(f"Regime: {regime}")

    # Verify fail-closed behavior
    assert not regime["is_entry_allowed"], f"Expected is_entry_allowed=False, got {regime['is_entry_allowed']}"
    assert regime["exposure_pct"] == 0, f"Expected exposure_pct=0, got {regime['exposure_pct']}"
    assert regime["regime"] == "unknown", f"Expected regime='unknown', got {regime['regime']}"
    assert len(regime["halt_reasons"]) > 0, "halt_reasons should document why entries are halted"

    print("[OK] Market regime correctly defaults to fail-closed when data unavailable")
    print(f"[OK] halt_reasons: {regime['halt_reasons']}\n")


def test_market_regime_database_error_failclosed():
    """
    CRITICAL TEST: Market regime must fail-closed when database error occurs.
    Simulates infrastructure failure (network timeout, connection error, etc).
    """
    print("\n" + "=" * 80)
    print("TEST: Market Regime - Fail-Closed On Database Error")
    print("=" * 80)

    test_date = date(2026, 6, 19)

    with patch("algo.orchestrator.phase5_signal_generation.DatabaseContext") as mock_db_context:
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.side_effect = Exception("Connection timeout: no available servers")
        mock_context_manager.__exit__.return_value = None

        mock_db_context.return_value = mock_context_manager

        # Call the market regime check
        regime = _check_market_regime(test_date)

    print(f"Regime: {regime}")

    # Verify fail-closed behavior
    assert not regime["is_entry_allowed"], (
        f"Expected is_entry_allowed=False (fail-closed), got {regime['is_entry_allowed']}"
    )
    assert regime["exposure_pct"] == 0, f"Expected exposure_pct=0, got {regime['exposure_pct']}"
    assert regime["regime"] == "unknown", f"Expected regime='unknown', got {regime['regime']}"
    assert len(regime["halt_reasons"]) > 0, "halt_reasons should document the error"
    assert "Market regime read failed" in regime["halt_reasons"][0], (
        f"halt_reason should mention read failure, got: {regime['halt_reasons'][0]}"
    )

    print("[OK] Market regime correctly fails-closed on database error")
    print(f"[OK] halt_reasons: {regime['halt_reasons']}\n")


def test_market_regime_valid_data():
    """
    HAPPY PATH TEST: Market regime should pass through valid data correctly.
    This ensures the fail-closed fix doesn't break normal operation.
    """
    print("\n" + "=" * 80)
    print("TEST: Market Regime - Happy Path With Valid Data")
    print("=" * 80)

    test_date = date(2026, 6, 19)
    import json

    with patch("algo.orchestrator.phase5_signal_generation.DatabaseContext") as mock_db_context:
        mock_cursor = MagicMock()

        # Valid market_exposure_daily row
        mock_cursor.fetchone.return_value = (
            True,  # is_entry_allowed
            75.0,  # exposure_pct
            "normal",  # regime
            json.dumps(["No halt reasons"]),  # halt_reasons (JSON)
        )

        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_cursor
        mock_context_manager.__exit__.return_value = None

        mock_db_context.return_value = mock_context_manager

        # Call the market regime check
        regime = _check_market_regime(test_date)

    print(f"Regime: {regime}")

    # Verify valid data passes through correctly
    assert regime["is_entry_allowed"], f"Expected is_entry_allowed=True, got {regime['is_entry_allowed']}"
    assert regime["exposure_pct"] == 75.0, f"Expected exposure_pct=75.0, got {regime['exposure_pct']}"
    assert regime["regime"] == "normal", f"Expected regime='normal', got {regime['regime']}"

    print("[OK] Market regime correctly passes through valid database data")
    print("[OK] Happy path still works after fail-closed fix\n")


def main():
    """Run all market regime fail-closed tests."""
    print("\n" + "=" * 80)
    print("MARKET REGIME FAIL-CLOSED TEST SUITE (Issue #4)")
    print("Verifies market regime defaults to halt on unavailability/error")
    print("=" * 80)

    passed = 0
    failed = 0

    try:
        test_market_regime_no_data_failclosed()
        passed += 1
    except AssertionError as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        failed += 1

    try:
        test_market_regime_database_error_failclosed()
        passed += 1
    except AssertionError as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        failed += 1

    try:
        test_market_regime_valid_data()
        passed += 1
    except AssertionError as e:
        print(f"\n✗ FAIL: {e}")
        failed += 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        failed += 1

    print("\n" + "=" * 80)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("=" * 80 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

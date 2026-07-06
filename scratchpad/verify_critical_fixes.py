#!/usr/bin/env python3
"""Verification script for all critical fixes applied in this session.

Tests:
1. Dashboard scores panel is properly rendered
2. Position monitor handles halt check errors gracefully
3. Timezone is correctly set to Eastern (not UTC)
4. Growth score data flows through API to dashboard
"""

import sys
import os

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

def test_scores_panel_imports():
    """Verify render_scores is properly imported in pipeline."""
    try:
        from dashboard.renderers.pipeline import render_scores
        print("[OK] render_scores imported successfully in pipeline.py")
        return True
    except ImportError as e:
        print(f"[FAIL] render_scores import failed: {e}")
        return False


def test_scores_in_context():
    """Verify DashboardContext has scores property."""
    try:
        from dashboard.core.context import DashboardContext

        test_data = {
            "scores": {
                "top": [
                    {"symbol": "AAPL", "composite_score": 85.5, "growth_score": 88.2}
                ]
            }
        }
        ctx = DashboardContext(test_data)
        scores = ctx.scores
        assert scores is not None, "ctx.scores returned None"
        assert scores.get("top") is not None, "scores missing 'top' field"
        print("[OK] DashboardContext.scores property works correctly")
        return True
    except Exception as e:
        print(f"[FAIL] DashboardContext test failed: {e}")
        return False


def test_timezone_fix():
    """Verify Eastern timezone is set correctly (not UTC)."""
    try:
        from utils.validation.framework import EASTERN_TZ
        from zoneinfo import ZoneInfo
        from datetime import timezone

        # Check it's not UTC
        assert EASTERN_TZ != timezone.utc, "EASTERN_TZ is still set to UTC!"

        # Check it's the right timezone
        assert str(EASTERN_TZ) == "America/New_York", f"EASTERN_TZ is {EASTERN_TZ}, expected America/New_York"
        print(f"[OK] EASTERN_TZ correctly set to {EASTERN_TZ}")
        return True
    except AssertionError as e:
        print(f"[FAIL] Timezone check failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Timezone test error: {e}")
        return False


def test_phase3_error_handling():
    """Verify phase 3 error handling for halt checks."""
    try:
        with open("C:/Users/arger/code/algo/algo/orchestrator/phase3_position_monitor.py") as f:
            content = f.read()

        # Check for error handling
        checks = [
            ('if "error" in halt_check' in content, "Error detection for halt check responses"),
            ('halt_check_errors' in content, "Halt check errors tracking"),
            ('logger.warning(f"[PHASE 3] {len(halt_check_errors)} halt checks failed' in content, "Error logging"),
        ]

        all_passed = True
        for check, desc in checks:
            if check:
                print(f"[OK] Phase 3 has {desc}")
            else:
                print(f"[FAIL] Phase 3 missing {desc}")
                all_passed = False

        return all_passed
    except Exception as e:
        print(f"[FAIL] Phase 3 check failed: {e}")
        return False


def test_dashboard_layout():
    """Verify dashboard has scores layout section."""
    try:
        with open("C:/Users/arger/code/algo/dashboard/dashboard.py") as f:
            content = f.read()

        # Check for scores layout definition
        if 'Layout(name="scores"' in content:
            print("[OK] Dashboard has scores layout section")
            return True
        else:
            print("[FAIL] Dashboard missing scores layout section")
            return False
    except Exception as e:
        print(f"[FAIL] Dashboard layout check failed: {e}")
        return False


def test_growth_score_api_endpoint():
    """Verify /api/algo/scores endpoint is properly defined."""
    try:
        with open("C:/Users/arger/code/algo/api-pkg/routes/algo.py") as f:
            content = f.read()

        # Check for scores endpoint routing
        if '/api/algo/scores' in content and '_get_dashboard_scores' in content:
            print("[OK] /api/algo/scores endpoint is properly routed")
            return True
        else:
            print("[FAIL] /api/algo/scores endpoint routing check failed")
            return False
    except Exception as e:
        print(f"[FAIL] API endpoint check failed: {e}")
        return False


def main():
    """Run all verification tests."""
    print("=" * 70)
    print("VERIFYING CRITICAL FIXES")
    print("=" * 70)
    print()

    tests = [
        ("Scores Panel Import", test_scores_panel_imports),
        ("Scores in Context", test_scores_in_context),
        ("Timezone Fix", test_timezone_fix),
        ("Phase 3 Error Handling", test_phase3_error_handling),
        ("Dashboard Layout", test_dashboard_layout),
        ("Growth Score API", test_growth_score_api_endpoint),
    ]

    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            results.append((name, result))
        except Exception as e:
            print(f"[FAIL] {name} test crashed: {e}")
            results.append((name, False))
        print()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll critical fixes verified successfully!")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed. Review above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

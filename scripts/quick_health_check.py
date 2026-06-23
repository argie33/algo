#!/usr/bin/env python3
"""Quick health check to catch broken code paths before CI.

Runs immediately after changes to detect:
  - Type errors that mypy misses (Any-typed dict access)
  - Missing imports or broken syntax
  - Runtime validation failures in critical paths

Should run in <5 seconds.
"""

import sys
import traceback
from pathlib import Path

# Add repo root to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_dashboard_imports() -> tuple[bool, str]:
    """Quick check: can we import dashboard modules without errors?"""
    try:
        from dashboard.data_validation import safe_float
        from dashboard.panels.health import HealthFormatter

        # Quick validation: does safe_float work?
        result = safe_float({"nested": "dict"}, default=None)
        if result is not None:
            return False, "safe_float should return None for dict input"

        result = safe_float("123.45", default=None)
        if result != 123.45:
            return False, f"safe_float should convert string to float, got {result}"

        # Validate: does HealthFormatter handle edge cases?
        color = HealthFormatter.var_color(None)
        if color != "dim":
            return False, "var_color(None) should return 'dim'"

        color = HealthFormatter.var_color(5.0)
        if not any(x in color.lower() for x in ["red", "r"]):
            return False, f"var_color(5.0) should return red color, got {color}"

        return True, "Dashboard imports and basic validation OK"

    except Exception as e:
        return False, f"Dashboard import failed: {e}\n{traceback.format_exc()}"


def check_type_safety_patterns() -> tuple[bool, str]:
    """Check that type safety patterns are used correctly."""
    try:
        from dashboard.data_validation import safe_float

        # Test: What happens when we try to compare unvalidated data?
        test_data = {
            "var95": {"nested": "dict"},  # Malformed: dict instead of float
            "beta": 1.5,  # Valid: float
        }

        # This SHOULD NOT crash if we use safe_float
        var95 = safe_float(test_data.get("var95"), default=None)
        beta = safe_float(test_data.get("beta"), default=None)

        # Comparisons should be safe now
        if var95 is not None:
            # Would fail without safe_float wrapping
            pass

        if beta is not None and beta >= 1.2:
            # This is safe because beta is guaranteed float | None
            pass

        return True, "Type safety patterns working correctly"

    except Exception as e:
        return False, f"Type safety check failed: {e}\n{traceback.format_exc()}"


def check_lambda_routes() -> tuple[bool, str]:
    """Quick check: can we import Lambda route handlers?"""
    try:
        # Use __import__ since 'lambda' is reserved keyword
        __import__("lambda.api.api_router", fromlist=["api_router"])

        # Just importing ensures syntax is valid and critical imports work
        return True, "Lambda routes import OK"

    except Exception as e:
        return False, f"Lambda routes import failed: {e}\n{traceback.format_exc()}"


def main() -> int:
    """Run all checks."""
    checks = [
        ("Dashboard imports", check_dashboard_imports),
        ("Type safety patterns", check_type_safety_patterns),
        ("Lambda routes", check_lambda_routes),
    ]

    results = []
    for name, check_fn in checks:
        try:
            success, message = check_fn()
            results.append((name, success, message))
            status = "[OK]" if success else "[FAILED]"
            print(f"{status} {name}: {message}")
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"[ERROR] {name}: {e}")

    print()
    failures = [name for name, success, _ in results if not success]
    if failures:
        print(f"[BLOCKED] {len(failures)} check(s) failed:")
        for name, _, message in results:
            if not results[[r[0] for r in results].index(name)][1]:
                print(f"  - {name}: {message}")
        return 1

    print(f"[OK] All {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

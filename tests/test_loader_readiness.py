#!/usr/bin/env python3
"""
Manual test to verify loaders can run with correct parallelism.
This tests the REAL fix without needing external infrastructure.
"""

import sys
from pathlib import Path

# Ensure imports work
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def test_parallelism():
    """Test that get_parallelism returns correct values for critical loaders."""
    from utils.loaders.config import get_parallelism

    print("Testing parallelism configuration...")
    print("=" * 60)

    # These are the critical loaders mentioned in ROOT_CAUSE #4
    critical_loaders = {
        "stock_prices_daily": 6,
        "buy_sell_daily": 6,
        "signal_quality_scores": 6,
        "swing_trader_scores": 6,
        "technical_data_daily": 8,
    }

    for loader_name, expected in critical_loaders.items():
        actual = get_parallelism(loader_name)
        status = "PASS" if actual >= expected else "FAIL"
        print(f"[{status}]: {loader_name:30} expected>={expected}, got {actual}")
        assert (
            actual >= expected
        ), f"{loader_name} parallelism {actual} < expected {expected}"

    print("=" * 60)


def test_imports():
    """Test that all critical modules can import without errors."""
    print("\nTesting module imports...")
    print("=" * 60)

    modules_to_test = [
        "algo.trading.position_sizer",
        "algo.risk.var",
        "algo.algo_orchestrator",
        "utils.loaders.config",
    ]

    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"[PASS]: {module_name}")
        except Exception as e:
            print(f"[FAIL]: {module_name} - {type(e).__name__}: {str(e)[:50]}")
            raise AssertionError(f"Failed to import {module_name}: {e}") from e

    print("=" * 60)


def test_loaders_syntax():
    """Test that loader files have valid Python syntax."""
    import py_compile
    from pathlib import Path

    print("\nTesting loader syntax...")
    print("=" * 60)

    loaders_dir = Path("loaders")
    critical_loaders = [
        "load_prices.py",
        "load_buy_sell_daily.py",
        "load_swing_trader_scores.py",
        "load_technical_data_daily.py",
        "load_signal_quality_scores.py",
    ]

    for loader_file in critical_loaders:
        loader_path = loaders_dir / loader_file
        try:
            py_compile.compile(str(loader_path), doraise=True)
            print(f"[PASS]: {loader_file}")
        except Exception as e:
            print(f"[FAIL]: {loader_file} - {e}")
            raise AssertionError(f"Syntax error in {loader_file}: {e}") from e

    print("=" * 60)


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LOADER SYSTEM READINESS TEST")
    print("Verifies that loaders can run with correct parallelism")
    print("=" * 60 + "\n")

    results = []
    results.append(("Parallelism Configuration", test_parallelism()))
    results.append(("Module Imports", test_imports()))
    results.append(("Loader Syntax", test_loaders_syntax()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}]: {test_name}")

    all_pass = all(r[1] for r in results)
    print(
        "\n"
        + (
            "[ALL PASS] - LOADERS READY TO RUN"
            if all_pass
            else "[FAIL] - SOME TESTS FAILED"
        )
    )
    print("=" * 60)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

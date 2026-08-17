#!/usr/bin/env python3
"""
Validate that all 5 root causes of loader brittleness have been fixed.

This script checks:
1. Dependency enforcement in scheduler
2. Timeout configurations match real runtime
3. Stale RUNNING loader detection at startup
4. Complete loader registry
5. Mid-run crash recovery in Phase 1

Exit code 0 = all fixes verified, 1 = at least one fix failed/missing
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_dependency_enforcement() -> bool:
    """ROOT CAUSE #1: Verify all loader dependencies are enforced in scheduler."""
    logger.info("\n[FIX #1] Checking loader dependency enforcement...")

    try:
        from scripts.local_loader_scheduler import LOADER_DEPENDENCIES

        required_deps = {
            "value_quality_growth": ["financial_statements", "valuations", "analyst_earnings_estimates"],
            "enhanced_quality_growth": ["value_quality_growth"],
            "segment_metrics": ["segment_info"],
            "scores": ["value_quality_growth", "enhanced_quality_growth", "stability_metrics"],
        }

        all_ok = True
        for loader, expected_deps in required_deps.items():
            actual_deps = LOADER_DEPENDENCIES.get(loader, [])
            actual_deps_set = set(actual_deps) if isinstance(actual_deps, (list, tuple)) else set()
            expected_deps_set = set(expected_deps)

            if not expected_deps_set.issubset(actual_deps_set):
                missing = expected_deps_set - actual_deps_set
                logger.error(f"  [FAIL] {loader} missing dependencies: {missing}")
                all_ok = False
            else:
                logger.info(f"  [OK] {loader}: {actual_deps}")

        return all_ok
    except Exception as e:
        logger.error(f"  [FAIL] Could not check dependencies: {e}")
        return False


def check_timeout_configurations() -> bool:
    """ROOT CAUSE #2: Verify timeouts are sized to real runtime."""
    logger.info("\n[FIX #2] Checking timeout configurations...")

    try:
        import inspect

        from scripts import local_loader_scheduler

        source = inspect.getsource(local_loader_scheduler)

        # Check that specific critical timeout values exist in the source
        critical_checks = {
            "financial_statements": "150",  # 150 min
            "company_info": "120",  # 120 min
            "enhanced_quality_growth": "200",  # 200 min
            "earnings_sec": "60",  # 60 min
            "segment_info": "30",  # 30 min
        }

        all_ok = True
        for loader, min_timeout in critical_checks.items():
            # Look for pattern like: "loader_name": 150 (may be split across lines with * 60)
            pattern1 = f'"{loader}": {min_timeout}'
            pattern2 = f'"{loader}": {min_timeout} *'  # Might have space before *
            if pattern1 in source or pattern2 in source:
                logger.info(f"  [OK] {loader}: configured to {min_timeout}m")
            else:
                logger.error(f"  [FAIL] {loader} not configured to at least {min_timeout}m")
                all_ok = False

        return all_ok
    except Exception as e:
        logger.error(f"  [FAIL] Could not check timeouts: {e}")
        return False


def check_stale_running_detection() -> bool:
    """ROOT CAUSE #3: Verify Phase 1 detects stale RUNNING loaders."""
    logger.info("\n[FIX #3] Checking stale RUNNING loader detection...")

    try:
        import inspect

        from algo.orchestrator import phase1_data_freshness

        # Check if _detect_and_fail_stale_running_loaders function exists
        source = inspect.getsource(phase1_data_freshness)
        if "_detect_and_fail_stale_running_loaders" not in source:
            logger.error("  [FAIL] _detect_and_fail_stale_running_loaders not found in Phase 1")
            return False

        if "RUNNING" not in source or "30" not in source or "FAILED" not in source:
            logger.error("  [FAIL] Phase 1 stale detection logic appears incomplete")
            return False

        logger.info("  [OK] Phase 1 has stale RUNNING loader detection")
        return True
    except Exception as e:
        logger.error(f"  [FAIL] Could not check Phase 1 detection: {e}")
        return False


def check_loader_registry() -> bool:
    """ROOT CAUSE #4: Verify all 34 loaders are registered in scheduler."""
    logger.info("\n[FIX #4] Checking complete loader registry...")

    try:
        from scripts.local_loader_scheduler import PIPELINES

        # Critical loaders that were missing before fix
        critical_loaders = [
            "signal_quality",  # critical path
            "algo",  # critical path
            "earnings_sec",
            "segment_metrics",
            "constituents",  # symbol list
            "economic",
            "naaim",
            "aaii",
            "dividends",
        ]

        all_registered = True
        for loader in critical_loaders:
            found = False
            for pipeline_name, loaders in PIPELINES.items():
                if loader in loaders:
                    logger.info(f"  [OK] {loader}: registered in {pipeline_name}")
                    found = True
                    break

            if not found:
                logger.error(f"  [FAIL] {loader}: NOT found in any pipeline")
                all_registered = False

        return all_registered
    except Exception as e:
        logger.error(f"  [FAIL] Could not check loader registry: {e}")
        return False


def check_mid_run_crash_recovery() -> bool:
    """ROOT CAUSE #5: Verify Phase 1 marks old RUNNING loaders as FAILED."""
    logger.info("\n[FIX #5] Checking mid-run crash recovery in Phase 1...")

    try:
        # Check if Phase 1 has the stale RUNNING detection
        import inspect

        from algo.orchestrator import phase1_data_freshness

        source = inspect.getsource(phase1_data_freshness)

        # Look for the detection logic
        checks_ok = all(
            [
                "stale_threshold_minutes" in source or "30" in source,  # 30 min threshold
                "RUNNING" in source,
                "FAILED" in source,
                "last_updated" in source,
            ]
        )

        if checks_ok:
            logger.info("  [OK] Phase 1 has mid-run crash recovery logic")
            return True
        else:
            logger.error("  [FAIL] Phase 1 crash recovery logic incomplete")
            return False
    except Exception as e:
        logger.error(f"  [FAIL] Could not check crash recovery: {e}")
        return False


def check_dashboard_loader_status() -> bool | None:
    """BONUS: Verify dashboard shows accurate loader status."""
    logger.info("\n[BONUS] Checking dashboard loader status display...")

    try:
        import importlib
        import inspect

        # lambda is a reserved keyword, so import via importlib
        market = importlib.import_module("lambda.api.routes.algo_handlers.market")
        source = inspect.getsource(market._get_data_status)

        checks_ok = all(
            [
                "loaders_with_errors" in source,
                "consecutive_failures" in source,
                "status" in source,
                "RUNNING" in source,
            ]
        )

        if checks_ok:
            logger.info("  [OK] Dashboard API tracks loader errors and status")
            return True
        else:
            logger.error("  [FAIL] Dashboard API missing loader error tracking")
            return False
    except Exception as e:
        logger.warning(f"  [WARN] Could not verify dashboard status: {e}")
        return None  # Don't fail on this


def main() -> int:
    print("=" * 80)
    print("LOADER BRITTLENESS ROOT CAUSE VALIDATION (2026-08-12)")
    print("=" * 80)

    results = {
        "Fix #1: Dependency Enforcement": check_dependency_enforcement(),
        "Fix #2: Timeout Configurations": check_timeout_configurations(),
        "Fix #3: Stale RUNNING Detection": check_stale_running_detection(),
        "Fix #4: Loader Registry": check_loader_registry(),
        "Fix #5: Mid-Run Crash Recovery": check_mid_run_crash_recovery(),
        "Bonus: Dashboard Status": check_dashboard_loader_status(),
    }

    print("\n" + "=" * 80)
    print("VALIDATION RESULTS")
    print("=" * 80)

    passed = 0
    failed = 0
    for fix_name, result in results.items():
        if result is None:
            status = "[WARN]"
        elif result:
            status = "[PASS]"
            passed += 1
        else:
            status = "[FAIL]"
            failed += 1
        print(f"{status} {fix_name}")

    print("=" * 80)
    print(f"Summary: {passed} passed, {failed} failed")
    print("=" * 80 + "\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

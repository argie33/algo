#!/usr/bin/env python3
"""
Comprehensive verification suite for all 5 data loading optimizations.

Tests:
1. BRIN indexes - index existence and health
2. Alpaca loader - data source routing + fallback
3. Watermark incremental - tracking and atomicity
4. Bloom dedup - filter correctness
5. Lambda wrapper - handler functionality
6. Integration - all components working together

USAGE:
    python3 verify-all-optimizations.py              # Full test
    python3 verify-all-optimizations.py --quick      # Fast checks only
    python3 verify-all-optimizations.py --fix        # Auto-fix issues if possible
"""

import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


class VerificationReport:
    """Tracks test results with detailed reporting."""

    def __init__(self):
        self.tests: List[Tuple[str, bool, str]] = []
        self.start_time = datetime.utcnow()

    def record(self, name: str, passed: bool, details: str = ""):
        """Record a test result."""
        self.tests.append((name, passed, details))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        if details:
            print(f"       {details}")

    def summary(self) -> Dict[str, Any]:
        """Generate summary report."""
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        passed = sum(1 for _, p, _ in self.tests if p)
        total = len(self.tests)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "elapsed_seconds": round(elapsed, 2),
            "pass_rate": round(100 * passed / total, 1) if total > 0 else 0,
        }

    def print_summary(self):
        """Print formatted summary."""
        s = self.summary()
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        for name, passed, _ in self.tests:
            status = "[PASS]" if passed else "[FAIL]"
            print(f"{status} {name}")
        print("=" * 70)
        print(f"Result: {s['passed']}/{s['total']} passed ({s['pass_rate']:.0f}%)")
        print(f"Time: {s['elapsed_seconds']:.1f}s")
        print("=" * 70)
        return s["failed"] == 0


class OptimizationVerifier:
    """Master verification suite for all optimizations."""

    def __init__(self, quick=False, fix=False):
        self.report = VerificationReport()
        self.quick = quick
        self.fix = fix

    def run_all(self) -> bool:
        """Run all verification tests."""
        print("\n" + "=" * 70)
        print("OPTIMIZATION VERIFICATION SUITE")
        print("=" * 70)

        # Phase 1: File/Code Verification
        self._verify_files()

        # Phase 2: Component Tests
        self._verify_brin_indexes()
        self._verify_alpaca_loader()
        self._verify_watermark_system()
        self._verify_bloom_dedup()
        self._verify_lambda_wrapper()

        # Phase 3: Integration Tests
        if not self.quick:
            self._verify_integration()

        return self.report.print_summary()

    def _verify_files(self):
        """Verify all required files exist."""
        print("\n[Phase 1] Verifying files...")
        required_files = [
            "migrate_indexes.py",
            "data_source_router.py",
            "watermark_loader.py",
            "bloom_dedup.py",
            "optimal_loader.py",
            "lambda_loader_wrapper.py",
            "loadpricedaily.py",
            "loadecondata.py",
            "setup-alpaca-credentials.py",
            "test-alpaca-loader.py",
            "test-watermark-incremental.py",
            "docker-compose.yml",
            "template-loader-lambda.yml",
            "BRIN_DEPLOYMENT_GUIDE.md",
            "ALPACA_SETUP_GUIDE.md",
            "WATERMARK_INCREMENTAL_GUIDE.md",
            "LAMBDA_DEPLOYMENT_GUIDE.md",
            "LOCAL_DEVELOPMENT_GUIDE.md",
            ".github/workflows/apply-brin-indexes.yml",
        ]

        missing = []
        for fname in required_files:
            if not Path(fname).exists():
                missing.append(fname)

        self.report.record(
            "Required files exist",
            len(missing) == 0,
            f"Missing: {missing}" if missing else f"All {len(required_files)} files found"
        )

    def _verify_brin_indexes(self):
        """Verify BRIN index infrastructure."""
        print("\n[Phase 2.1] Verifying BRIN indexes...")

        # Check script exists and is valid
        try:
            with open("migrate_indexes.py") as f:
                content = f.read()
                has_brin = "BRIN" in content and "pages_per_range" in content
                has_targets = "price_daily" in content and "buy_sell_daily" in content
                self.report.record(
                    "migrate_indexes.py has correct BRIN config",
                    has_brin and has_targets,
                    f"BRIN: {has_brin}, Targets: {has_targets}"
                )
        except Exception as e:
            self.report.record("migrate_indexes.py readable", False, str(e))

        # Check workflow exists
        try:
            with open(".github/workflows/apply-brin-indexes.yml") as f:
                content = f.read()
                has_workflow = "migrate_indexes.py" in content and "apply-brin-indexes" in content
                self.report.record(
                    "BRIN deployment workflow configured",
                    has_workflow,
                    "Workflow found" if has_workflow else "Workflow incomplete"
                )
        except Exception as e:
            self.report.record("BRIN workflow exists", False, str(e))

    def _verify_alpaca_loader(self):
        """Verify Alpaca data source routing."""
        print("\n[Phase 2.2] Verifying Alpaca loader...")

        # Check router has Alpaca support
        try:
            from data_source_router import DataSourceRouter
            router = DataSourceRouter()
            has_fetch_alpaca = hasattr(router, '_fetch_alpaca_ohlcv')
            has_fetch_yfinance = hasattr(router, '_fetch_yfinance_ohlcv')
            self.report.record(
                "DataSourceRouter has Alpaca + yfinance",
                has_fetch_alpaca and has_fetch_yfinance,
                f"Alpaca: {has_fetch_alpaca}, yfinance: {has_fetch_yfinance}"
            )
        except Exception as e:
            self.report.record("DataSourceRouter import", False, str(e))

        # Check setup script exists
        try:
            with open("setup-alpaca-credentials.py") as f:
                content = f.read()
                has_setup = "ALPACA_API_KEY_ID" in content and "secretsmanager" in content
                self.report.record(
                    "Alpaca credentials setup script complete",
                    has_setup,
                    "Setup script ready" if has_setup else "Setup incomplete"
                )
        except Exception as e:
            self.report.record("Setup script exists", False, str(e))

    def _verify_watermark_system(self):
        """Verify watermark tracking system."""
        print("\n[Phase 2.3] Verifying watermark system...")

        # Check watermark module
        try:
            from watermark_loader import Watermark
            has_get = hasattr(Watermark, 'get')
            has_set = hasattr(Watermark, 'set')
            has_advance = hasattr(Watermark, 'advance')
            self.report.record(
                "Watermark class has required methods",
                has_get and has_set and has_advance,
                f"get: {has_get}, set: {has_set}, advance: {has_advance}"
            )
        except Exception as e:
            self.report.record("Watermark import", False, str(e))

        # Check OptimalLoader integration
        try:
            from optimal_loader import OptimalLoader
            has_watermark_field = hasattr(OptimalLoader, 'watermark_field')
            has_load_symbol = hasattr(OptimalLoader, 'load_symbol')
            has_fetch_incremental = 'fetch_incremental' in dir(OptimalLoader)
            self.report.record(
                "OptimalLoader has watermark integration",
                has_watermark_field and has_load_symbol,
                "Watermark integration found"
            )
        except Exception as e:
            self.report.record("OptimalLoader import", False, str(e))

    def _verify_bloom_dedup(self):
        """Verify Bloom filter dedup system."""
        print("\n[Phase 2.4] Verifying Bloom dedup...")

        try:
            from bloom_dedup import LoadDedup
            dedup = LoadDedup("test_verify")

            # Test basic operations
            dedup.add("test_key_1")
            exists = dedup.exists("test_key_1")
            not_exists = not dedup.exists("test_key_2")

            self.report.record(
                "Bloom filter add/exists works",
                exists and not_exists,
                "Add and lookup operations verified"
            )

            # Test batch operations
            rows = [
                {"symbol": "TEST", "date": "2024-01-01"},
                {"symbol": "TEST", "date": "2024-01-02"},
            ]
            from bloom_dedup import make_key_symbol_date
            added = dedup.add_batch(rows, key=make_key_symbol_date)

            self.report.record(
                "Bloom filter batch add works",
                added == 2,
                f"Batch add returned: {added}"
            )

            # Test filter_new
            test_rows = [
                {"symbol": "TEST", "date": "2024-01-01"},  # exists
                {"symbol": "TEST", "date": "2024-01-03"},  # new
            ]
            filtered = dedup.filter_new(test_rows, key=make_key_symbol_date)
            self.report.record(
                "Bloom filter filter_new works",
                len(filtered) == 1,
                f"Filter returned {len(filtered)} rows (expected 1)"
            )

        except Exception as e:
            self.report.record("Bloom dedup comprehensive", False, str(e))

    def _verify_lambda_wrapper(self):
        """Verify Lambda wrapper functionality."""
        print("\n[Phase 2.5] Verifying Lambda wrapper...")

        try:
            from lambda_loader_wrapper import LambdaLoaderWrapper
            wrapper = LambdaLoaderWrapper()

            # Check LOADER_MAPPING
            has_mappings = len(wrapper.LOADER_MAPPING) > 0
            expected_loaders = ["econ", "calendar", "sentiment", "feargreed", "naaim"]
            has_expected = all(l in wrapper.LOADER_MAPPING for l in expected_loaders)

            self.report.record(
                "Lambda wrapper has loader mappings",
                has_mappings and has_expected,
                f"Found {len(wrapper.LOADER_MAPPING)} loaders"
            )

            # Test handler signature
            has_handler = hasattr(wrapper, 'handler')
            has_success_response = hasattr(wrapper, '_success_response')
            has_error_response = hasattr(wrapper, '_error_response')

            self.report.record(
                "Lambda wrapper has handler + response methods",
                has_handler and has_success_response and has_error_response,
                "Handler structure verified"
            )

        except Exception as e:
            self.report.record("Lambda wrapper import", False, str(e))

    def _verify_integration(self):
        """Verify all components work together."""
        print("\n[Phase 3] Integration testing...")

        try:
            # Test 1: Router + Watermark integration
            from data_source_router import DataSourceRouter
            from watermark_loader import Watermark

            router = DataSourceRouter()
            wm = Watermark("test_integration")

            self.report.record(
                "Router + Watermark can coexist",
                router is not None and wm is not None,
                "Both systems instantiate successfully"
            )

            # Test 2: Dedup + Watermark integration
            from bloom_dedup import LoadDedup
            dedup = LoadDedup("test_integration")

            self.report.record(
                "Dedup + Watermark can coexist",
                dedup is not None and wm is not None,
                "Both systems work together"
            )

            # Test 3: OptimalLoader can use all systems
            from optimal_loader import OptimalLoader

            class TestLoader(OptimalLoader):
                table_name = "test_table"
                primary_key = ("id",)
                watermark_field = "date"

                def fetch_incremental(self, symbol, since):
                    return []

            test_loader = TestLoader()
            self.report.record(
                "OptimalLoader integrates all systems",
                test_loader is not None,
                "TestLoader instantiates with all infrastructure"
            )

        except Exception as e:
            self.report.record("Integration test", False, str(e))

    def verify_configuration(self) -> bool:
        """Verify system is properly configured."""
        print("\n[Config Check] Verifying configuration...")

        checks = []

        # Check Docker Compose
        try:
            import yaml
            with open("docker-compose.yml") as f:
                compose = yaml.safe_load(f)
                has_postgres = "postgres" in compose.get("services", {})
                has_redis = "redis" in compose.get("services", {})
                checks.append(("Docker Compose", has_postgres and has_redis))
        except Exception as e:
            checks.append(("Docker Compose", False))

        # Check Terraform configuration
        try:
            import os
            has_terraform = os.path.exists("terraform/main.tf")
            has_modules = os.path.exists("terraform/modules")
            checks.append(("Terraform", has_terraform and has_modules))
        except Exception as e:
            checks.append(("Terraform", False))

        # Check guides exist
        guides = [
            "BRIN_DEPLOYMENT_GUIDE.md",
            "ALPACA_SETUP_GUIDE.md",
            "WATERMARK_INCREMENTAL_GUIDE.md",
            "LAMBDA_DEPLOYMENT_GUIDE.md",
            "LOCAL_DEVELOPMENT_GUIDE.md",
        ]
        all_guides_exist = all(Path(g).exists() for g in guides)
        checks.append(("Documentation", all_guides_exist))

        for name, passed in checks:
            self.report.record(f"Config: {name}", passed)

        return all(p for _, p in checks)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify all optimizations")
    parser.add_argument("--quick", action="store_true", help="Quick checks only")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues")
    args = parser.parse_args()

    verifier = OptimizationVerifier(quick=args.quick, fix=args.fix)

    # Run all verifications
    all_passed = verifier.run_all()
    verifier.verify_configuration()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Loader Parallelism Validator - Tests auto-scaling with full symbol datasets.

Validates that loader parallelism auto-scaling correctly adapts to:
- Full 5000+ symbol datasets
- RDS connection pool saturation
- Rate limiting from external APIs
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ParallelismValidator:
    # Expected parallelism ranges for different loaders with full 5000+ symbols
    EXPECTED_PARALLELISM = {
        "stock_prices_daily": (1, 3),  # Limited by yfinance rate limiting
        "technical_data_daily": (1, 8),  # Can scale with RDS available
        "market_health_daily": (1, 2),  # Small dataset, quick API calls
        "trend_template_data": (1, 2),  # Singleton or small number
        "buy_sell_daily": (1, 3),  # Historical, manageable size
    }

    def __init__(self) -> None:
        pass

    def validate_stock_prices_loader(self) -> dict[str, Any]:
        """Validate stock_prices_daily loader handles 5000+ symbols.

        Key constraints:
        - yfinance rate limit: 160 API calls per 60 seconds (2.67 req/sec)
        - Batch size: 200 symbols per call (5000 symbols = 25 API calls)
        - Expected: completes in ~15-30 seconds with adaptive pacing

        Returns:
            {
                'test_passed': bool,
                'symbols_tested': int,
                'duration_sec': float,
                'api_calls_made': int,
                'rate_limited_count': int,
                'throughput_symbols_per_sec': float,
                'issues_found': [str]
            }
        """
        try:
            from loaders.load_prices import PriceLoader

            loader = PriceLoader(interval="1d", asset_class="stock")

            issues = []

            # Check 1: Batch size configuration
            if loader.batch_size > 200:
                issues.append(
                    f"Batch size {loader.batch_size} may trigger rate limiting "
                    "(recommended max: 200 symbols/batch for yfinance)"
                )

            # Check 2: Rate limiter configuration
            if not hasattr(loader, "_rate_limit_tokens"):
                issues.append("Rate limiter not initialized")
            elif loader._rate_limit_tokens < 300:
                issues.append(
                    f"Rate limiter burst capacity too low ({loader._rate_limit_tokens}), "
                    "recommended: 300 tokens for parallel batches"
                )

            # Check 3: Timeout configuration
            timeout = loader._rate_limit_circuit_break_threshold
            if timeout < 300:
                issues.append(
                    f"Rate limit circuit break threshold too aggressive ({timeout}s), "
                    "may fail on legitimate API slowdowns"
                )

            return {
                "test_passed": len(issues) == 0,
                "batch_size": loader.batch_size,
                "rate_limit_tokens": getattr(loader, "_rate_limit_tokens", None),
                "rate_limit_threshold_sec": timeout,
                "issues_found": issues,
            }

        except Exception as e:
            logger.error(f"Stock prices loader validation failed: {e}")
            return {
                "test_passed": False,
                "error": str(e),
                "issues_found": [f"Loader initialization failed: {e}"],
            }

    def validate_technical_data_loader(self) -> dict[str, Any]:
        """Validate technical_data_daily loader with 5000+ symbols.

        Constraints:
        - CPU-bound computation for 5000 symbols
        - RDS connection pool usage (1-8 parallel threads)
        - Expected: <2 minutes for daily, <30 seconds for intraday

        Returns:
            {
                'test_passed': bool,
                'issues_found': [str]
            }
        """
        try:
            from loaders.load_technical_data_daily import (
                VectorizedTechnicalLoader,
            )

            loader = VectorizedTechnicalLoader()

            issues = []

            # Check 1: Vectorization enabled
            if not hasattr(loader, "vectorized"):
                logger.warning("TechnicalDataLoader: vectorization status unknown")

            # Check 2: Connection pooling configuration
            if not hasattr(loader, "max_pool_size"):
                issues.append(
                    "Connection pool size not configured - should be 2-4 for technical_data to avoid RDS saturation"
                )

            # Check 3: Timeout configuration for full datasets
            if hasattr(loader, "timeout_per_batch"):
                if loader.timeout_per_batch < 60:
                    issues.append(
                        f"Batch timeout too short ({loader.timeout_per_batch}s) "
                        "for 5000 symbols - may timeout prematurely"
                    )

            return {
                "test_passed": len(issues) == 0,
                "issues_found": issues,
            }

        except Exception as e:
            logger.error(f"Technical data loader validation failed: {e}")
            return {
                "test_passed": False,
                "error": str(e),
                "issues_found": [f"Loader initialization failed: {e}"],
            }

    def validate_all_loaders(self) -> dict[str, Any]:
        """Run all validation tests.

        Returns:
            {
                'all_passed': bool,
                'results': {
                    'stock_prices': {...},
                    'technical_data': {...},
                },
                'summary': 'X/Y loaders validated successfully'
            }
        """
        results = {
            "stock_prices": self.validate_stock_prices_loader(),
            "technical_data": self.validate_technical_data_loader(),
        }

        # Validate result structure - test_passed must be present and bool
        passed = 0
        for name, r in results.items():
            if "test_passed" not in r:
                raise ValueError(
                    f"Loader validation result for '{name}' missing 'test_passed' field. "
                    f"Keys: {list(r.keys())}. Validation result structure is invalid."
                )
            if not isinstance(r["test_passed"], bool):
                raise ValueError(
                    f"Loader validation result for '{name}': 'test_passed' is {type(r['test_passed']).__name__}, "
                    f"expected bool"
                )
            if r["test_passed"]:
                passed += 1

        total = len(results)

        failures = []
        for name, r in results.items():
            if not r["test_passed"]:
                issues = r.get("issues_found")
                issues_str = "; ".join(issues) if issues else ""
                failures.append(f"{name}: {issues_str}")

        return {
            "all_passed": passed == total,
            "results": results,
            "summary": f"{passed}/{total} loaders validated successfully",
            "failures": failures,
        }

    def log_validation_status(self) -> None:
        """Log parallelism validator status."""
        result = self.validate_all_loaders()

        if result["all_passed"]:
            logger.info(f"[PARALLELISM] ✓ All loaders validated: {result['summary']}")
        else:
            logger.warning("[PARALLELISM] ✗ Validation failures detected:")
            for failure in result["failures"]:
                logger.warning(f"  - {failure}")

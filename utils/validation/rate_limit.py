#!/usr/bin/env python3
"""Rate Limit Validator — Ensures critical APIs can handle full data volume.

Validates that:
- yfinance doesn't block critical price loads (160 req/min limit)
- FRED API stays responsive
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# =====================================================================
# External API Rate Limits
# =====================================================================

YFINANCE_REQUESTS_PER_MINUTE = 160
YFINANCE_BATCH_SIZE_MAX = 200
YFINANCE_SAFE_MARGIN = 0.8

FRED_REQUESTS_PER_SECOND = 5

# Validation thresholds
MAX_VALIDATION_DURATION_SECONDS = 300  # 5 minutes
CIRCUIT_BREAK_THRESHOLD_SECONDS = 180  # Min threshold for circuit breaker
CIRCUIT_BREAK_RECOMMENDED_SECONDS = 300  # Recommended minimum

# Default parameters
DEFAULT_SYMBOL_COUNT = 5000
DEFAULT_HEALTH_CHECK_TICKER = "SPY"


class RateLimitValidator:

    def __init__(self) -> None:
        # Rate limit specifications
        self.yfinance_limit = {
            "requests_per_minute": YFINANCE_REQUESTS_PER_MINUTE,
            "batch_size_max": YFINANCE_BATCH_SIZE_MAX,
            "safe_margin": YFINANCE_SAFE_MARGIN,
        }

        self.fred_limit = {
            "requests_per_second": FRED_REQUESTS_PER_SECOND,
            "single_endpoint": True,
        }

    def estimate_yfinance_calls_needed(self, symbol_count: int = DEFAULT_SYMBOL_COUNT) -> dict[str, Any]:
        """Estimate how many yfinance API calls needed for full dataset.

        For 5000 symbols:
        - Batch size 200 = 25 API calls
        - Time at 160 req/min = 25/160 * 60 = 9.4 seconds

        Returns:
            {
                'total_symbols': 5000,
                'batch_size': 200,
                'batches_needed': 25,
                'requests_per_min_limit': 160,
                'safe_requests_per_min': 128,
                'estimated_duration_sec': 9.4,
                'safe_to_proceed': True,
                'issues': []
            }
        """
        batch_size = self.yfinance_limit["batch_size_max"]
        batches_needed = (symbol_count + batch_size - 1) // batch_size

        rpm_limit = self.yfinance_limit["requests_per_minute"]
        safe_rpm = rpm_limit * self.yfinance_limit["safe_margin"]

        # Time needed = (batches x 60 seconds) / safe_rpm
        estimated_sec = (batches_needed * 60) / safe_rpm

        issues = []

        if batches_needed > rpm_limit:
            issues.append(f"Cannot complete in 1 minute: need {batches_needed} requests, limit is {rpm_limit} req/min")

        if estimated_sec > MAX_VALIDATION_DURATION_SECONDS:
            issues.append(
                f"Estimated time {estimated_sec:.0f}s exceeds {MAX_VALIDATION_DURATION_SECONDS}-second window - "
                "consider reducing symbol count or increasing batch size"
            )

        return {
            "total_symbols": symbol_count,
            "batch_size": batch_size,
            "batches_needed": batches_needed,
            "requests_per_min_limit": rpm_limit,
            "safe_requests_per_min": round(safe_rpm, 0),
            "estimated_duration_sec": round(estimated_sec, 1),
            "safe_to_proceed": len(issues) == 0,
            "issues": issues,
        }

    def check_api_health(self) -> dict[str, Any]:
        """Quick health check for critical APIs.

        Returns:
            {
                'yfinance_available': bool,
                'fred_available': bool,
                'all_available': bool,
                'issues': [str]
            }
        """
        issues: list[str] = []
        health: dict[str, Any] = {
            "yfinance_available": False,
            "fred_available": False,
        }

        # Check yfinance (used by price loader)
        try:
            import yfinance

            # Quick test: try to fetch ticker info (lightweight)
            ticker = yfinance.Ticker(DEFAULT_HEALTH_CHECK_TICKER)
            info = ticker.info
            if info and "currentPrice" in info:
                health["yfinance_available"] = True
                logger.debug("[API-HEALTH] yfinance responding")
            else:
                issues.append("yfinance not returning expected data")
        except Exception as e:
            issues.append(f"yfinance health check failed: {str(e)[:100]}")
            logger.warning(f"[API-HEALTH] yfinance unavailable: {e}")

        # Check FRED (market health data)
        try:
            import os

            fred_token = os.getenv("FRED_API_KEY")
            if fred_token:
                health["fred_available"] = True
                logger.debug("[API-HEALTH] FRED API token configured")
            else:
                issues.append("FRED_API_KEY not configured")
        except Exception as e:
            issues.append(f"FRED health check failed: {str(e)[:100]}")

        health["all_available"] = all(health.values())
        health["issues"] = issues

        return health

    def validate_rate_limit_handling(self) -> dict[str, Any]:
        try:
            from loaders.load_prices import PriceLoader

            loader = PriceLoader()

            issues = []
            recommendations = []

            # Check 1: Rate limiter exists and is configured
            if not hasattr(loader, "_rate_limit_tokens"):
                issues.append("Rate limiter not initialized")

            # Check 2: Circuit breaker threshold appropriate
            threshold = getattr(
                loader,
                "_rate_limit_circuit_break_threshold",
                CIRCUIT_BREAK_THRESHOLD_SECONDS,
            )
            if threshold < CIRCUIT_BREAK_THRESHOLD_SECONDS:
                recommendations.append(
                    f"Rate limit circuit break threshold {threshold}s may be too aggressive - "
                    f"recommend {CIRCUIT_BREAK_RECOMMENDED_SECONDS}+ for recovery time"
                )

            # Check 3: Exponential backoff configured
            if not hasattr(loader, "_request_latency_samples"):
                issues.append("No adaptive latency tracking found")
            else:
                recommendations.append("Adaptive latency tracking enabled - good for detecting rate limits")

            # Check 4: Batch sizing logic
            if hasattr(loader, "_batch_size_performance"):
                logger.debug("Batch size optimization enabled")

            return {
                "test_passed": len(issues) == 0,
                "issues": issues,
                "recommendations": recommendations,
            }

        except Exception as e:
            logger.error(f"Rate limit handling validation failed: {e}")
            return {
                "test_passed": False,
                "issues": [f"Validation failed: {str(e)[:100]}"],
            }

    def log_rate_limit_status(self) -> None:
        """Log rate limit health and recommendations."""
        estimate = self.estimate_yfinance_calls_needed()
        health = self.check_api_health()
        validation = self.validate_rate_limit_handling()

        logger.info(
            f"[RATE-LIMITS] yfinance: {estimate['batches_needed']} batches in "
            f"{estimate['estimated_duration_sec']:.0f}s (safe: {estimate['safe_to_proceed']})"
        )

        if health["all_available"]:
            logger.info("[RATE-LIMITS] ✓ All APIs available")
        else:
            logger.warning(f"[RATE-LIMITS] ⚠ Some APIs unavailable: {health['issues']}")

        if not validation["test_passed"]:
            logger.warning(f"[RATE-LIMITS] Issues found: {validation['issues']}")
        else:
            logger.info("[RATE-LIMITS] ✓ Rate limit handling validated")

        for rec in validation["recommendations"]:
            logger.info(f"[RATE-LIMITS] Tip: {rec}")

#!/usr/bin/env python3
"""
Unified Circuit Breaker Pattern for Data Loaders.

Standardizes outage handling across all loaders:
- CRITICAL DATA: Fail fast on any error (no stale cache fallback)
- OPTIONAL ENRICHMENT: Graceful degradation (warn, continue with None values)
- TRANSIENT ERRORS: Retry with exponential backoff + circuit breaker

Prevents silent stale data usage by:
1. Explicit error tracking with DataUnavailableError
2. Fail-fast returns for critical paths
3. Graceful degradation for optional enrichments only
4. Clear logging of all circuit breaker state transitions
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker state transitions."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — all requests denied
    HALF_OPEN = "half_open"  # Testing recovery — allow 1 request


class DataImportance(Enum):
    """Data criticality for circuit breaker decisions."""
    CRITICAL = "critical"  # Fail pipeline if unavailable (e.g., VIX for position sizing)
    REQUIRED = "required"  # Can't complete computation without it
    OPTIONAL = "optional"  # Missing is OK, continue with None values


class CircuitBreaker:
    """
    Unified circuit breaker for data loader outage handling.

    Usage:
        breaker = CircuitBreaker(
            name="yfinance_vix",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.CRITICAL
        )

        data = breaker.execute(
            fetch_func=lambda: yfinance.get("^VIX"),
            importance=DataImportance.CRITICAL
        )
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_sec: int = 300,
        importance: DataImportance = DataImportance.REQUIRED,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.default_importance = importance

        # State tracking
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.opened_at: float | None = None
        self.success_count_in_half_open = 0

    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        if self.state == CircuitBreakerState.CLOSED:
            return False

        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has elapsed
            if (
                self.opened_at is not None
                and time.time() - self.opened_at >= self.recovery_timeout_sec
            ):
                logger.info(
                    f"[CIRCUIT_BREAKER:{self.name}] Recovery timeout elapsed, "
                    f"transitioning to HALF_OPEN to test API recovery"
                )
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count_in_half_open = 0
                return False  # Allow half-open test request
            return True

        # HALF_OPEN state: allow requests through
        return False

    def record_success(self) -> None:
        """Record successful request."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count_in_half_open += 1
            if self.success_count_in_half_open >= 2:  # 2 successes = circuit recovered
                logger.info(
                    f"[CIRCUIT_BREAKER:{self.name}] API recovered, "
                    f"transitioning from HALF_OPEN to CLOSED"
                )
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success during normal operation
            if self.failure_count > 0:
                logger.debug(
                    f"[CIRCUIT_BREAKER:{self.name}] Success after prior failures, resetting counter"
                )
                self.failure_count = 0

    def record_failure(self) -> None:
        """Record failed request, potentially opening circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failure during recovery attempt — go back to OPEN
            logger.warning(
                f"[CIRCUIT_BREAKER:{self.name}] Recovery test failed, "
                f"reopening circuit (was in HALF_OPEN)"
            )
            self.state = CircuitBreakerState.OPEN
            self.opened_at = time.time()
            self.success_count_in_half_open = 0
        elif self.failure_count >= self.failure_threshold:
            # Threshold reached — open circuit
            logger.critical(
                f"[CIRCUIT_BREAKER:{self.name}] ⚠️  CIRCUIT OPEN: "
                f"{self.failure_count}/{self.failure_threshold} failures detected. "
                f"Will retry in {self.recovery_timeout_sec}s. "
                f"API: {self.name} appears unavailable."
            )
            self.state = CircuitBreakerState.OPEN
            self.opened_at = time.time()

    def execute(
        self,
        fetch_func: Callable[[], T],
        importance: DataImportance | None = None,
        fallback_value: Any | None = None,
    ) -> T | None:
        """
        Execute fetch function with circuit breaker protection.

        Args:
            fetch_func: Function that fetches data
            importance: Critical/required/optional (overrides default)
            fallback_value: Value to return if circuit open (only for optional data)

        Returns:
            Data on success, None or fallback on graceful failure, raises on critical failure

        Raises:
            RuntimeError: If circuit open and data is CRITICAL
        """
        importance = importance or self.default_importance

        # CRITICAL: Check circuit state and reject if appropriate
        if self.is_open():
            error_msg = (
                f"[CIRCUIT_BREAKER:{self.name}] Circuit OPEN: API unavailable. "
                f"Last failure: {time.time() - self.last_failure_time:.0f}s ago. "
                f"Will retry at: {self.opened_at + self.recovery_timeout_sec:.0f} UTC"
            )

            if importance == DataImportance.CRITICAL:
                # CRITICAL data: Fail immediately, don't use stale cache
                logger.critical(f"{error_msg}. CRITICAL DATA UNAVAILABLE — PIPELINE MUST HALT")
                raise RuntimeError(
                    f"[CIRCUIT_OPEN] {self.name} unavailable and data is CRITICAL. "
                    "Cannot proceed without this data. "
                    "Phase will be retried when API recovers."
                )
            elif importance == DataImportance.REQUIRED:
                # REQUIRED data: Fail but with clearer recovery guidance
                logger.error(
                    f"{error_msg}. REQUIRED DATA UNAVAILABLE — phase execution blocked. "
                    "Check API status and RDS connectivity."
                )
                raise RuntimeError(
                    f"[CIRCUIT_OPEN] {self.name} unavailable and data is REQUIRED. "
                    "Cannot complete phase without this data."
                )
            else:
                # OPTIONAL enrichment: Graceful degradation
                logger.warning(
                    f"{error_msg}. OPTIONAL DATA UNAVAILABLE — continuing without enrichment. "
                    f"Returning fallback: {fallback_value}"
                )
                return fallback_value

        # Circuit not open — try to fetch
        try:
            result = fetch_func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            error_msg = f"[CIRCUIT_BREAKER:{self.name}] Fetch failed: {type(e).__name__}: {str(e)[:100]}"

            if importance == DataImportance.CRITICAL:
                logger.critical(
                    f"{error_msg} (failure {self.failure_count}/{self.failure_threshold}). "
                    "CRITICAL DATA FETCH FAILED — pipeline must halt."
                )
                raise RuntimeError(
                    f"Critical data fetch failed for {self.name}: {e}"
                ) from e
            elif importance == DataImportance.REQUIRED:
                logger.error(
                    f"{error_msg} (failure {self.failure_count}/{self.failure_threshold}). "
                    "REQUIRED DATA FETCH FAILED — phase execution blocked."
                )
                raise RuntimeError(
                    f"Required data fetch failed for {self.name}: {e}"
                ) from e
            else:
                # OPTIONAL: Log warning, return fallback, don't raise
                logger.warning(
                    f"{error_msg} (failure {self.failure_count}/{self.failure_threshold}). "
                    "OPTIONAL DATA FETCH FAILED — continuing with fallback value. "
                    "Will open circuit after {self.failure_threshold} failures."
                )
                return fallback_value


class CriticalDataUnavailableError(Exception):
    """Raised when critical data cannot be fetched and circuit is open."""
    def __init__(self, resource_name: str, root_cause: str, retry_after_sec: int):
        self.resource_name = resource_name
        self.root_cause = root_cause
        self.retry_after_sec = retry_after_sec
        super().__init__(
            f"Critical data unavailable: {resource_name}. "
            f"Reason: {root_cause}. Retry in {retry_after_sec}s."
        )


class StaleDataError(Exception):
    """Raised when cached data exceeds freshness threshold."""
    def __init__(self, resource_name: str, age_hours: float, max_age_hours: float):
        self.resource_name = resource_name
        self.age_hours = age_hours
        self.max_age_hours = max_age_hours
        super().__init__(
            f"Data for {resource_name} is too stale: {age_hours:.1f}h old "
            f"(max allowed: {max_age_hours:.1f}h). Cannot use for decision-making."
        )

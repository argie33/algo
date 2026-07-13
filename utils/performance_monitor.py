#!/usr/bin/env python3
"""Performance monitoring for daily refresh optimization work.

Tracks metrics for Phase 1-4 optimizations:
- Cache hit rates (Phase 3.1-3.2)
- API call efficiency (Phase 2, 3)
- Refresh cycle timing (all phases)
- Data quality (Phase 1)
- Circuit breaker activity (Phase 2)
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class RefreshMetrics:
    """Metrics for a single refresh run."""

    run_date: str
    total_symbols: int
    api_calls: int
    cache_hits: int
    elapsed_seconds: float
    circuit_breaker_activations: int
    data_coverage_pct: float
    errors: int = 0

    @property
    def cache_hit_rate_pct(self) -> float:
        """Percentage of symbols that used cache."""
        if self.total_symbols == 0:
            return 0.0
        return (self.cache_hits / self.total_symbols) * 100

    @property
    def api_efficiency_pct(self) -> float:
        """Percentage of symbols that didn't require API calls."""
        if self.total_symbols == 0:
            return 0.0
        return ((self.total_symbols - self.api_calls) / self.total_symbols) * 100

    def log_summary(self) -> None:
        """Log refresh metrics summary."""
        logger.info(
            f"[REFRESH_METRICS] {self.run_date}: "
            f"symbols={self.total_symbols}, "
            f"api_calls={self.api_calls} ({self.api_efficiency_pct:.1f}% efficient), "
            f"cache_hits={self.cache_hits} ({self.cache_hit_rate_pct:.1f}%), "
            f"time={self.elapsed_seconds:.1f}s, "
            f"circuit_breaker_activations={self.circuit_breaker_activations}, "
            f"coverage={self.data_coverage_pct:.1f}%, "
            f"errors={self.errors}"
        )


class PerformanceMonitor:
    """Monitor and track optimization performance metrics."""

    def __init__(self) -> None:
        self.run_start_time: float = 0
        self.api_calls: int = 0
        self.cache_hits: int = 0
        self.circuit_breaker_activations: int = 0
        self.errors: int = 0

    def start_run(self) -> None:
        """Mark the start of a refresh run."""
        self.run_start_time = time.time()
        self.api_calls = 0
        self.cache_hits = 0
        self.circuit_breaker_activations = 0
        self.errors = 0

    def record_cache_hit(self, symbol: str) -> None:
        """Record a cache hit for a symbol."""
        self.cache_hits += 1
        logger.debug(f"[CACHE_HIT] {symbol}")

    def record_api_call(self, symbol: str) -> None:
        """Record an API call for a symbol."""
        self.api_calls += 1
        logger.debug(f"[API_CALL] {symbol}")

    def record_circuit_breaker_activation(self) -> None:
        """Record a circuit breaker activation (rate limit response)."""
        self.circuit_breaker_activations += 1
        logger.warning("[CIRCUIT_BREAKER] Rate limit response - exponential backoff initiated")

    def record_error(self, symbol: str, error_msg: str) -> None:
        """Record an error during fetch."""
        self.errors += 1
        logger.warning(f"[FETCH_ERROR] {symbol}: {error_msg}")

    def end_run(
        self,
        total_symbols: int,
        data_coverage_pct: float,
    ) -> RefreshMetrics:
        """Mark the end of a refresh run and return metrics."""
        elapsed_seconds = time.time() - self.run_start_time
        run_date = datetime.now(timezone.utc).isoformat()

        metrics = RefreshMetrics(
            run_date=run_date,
            total_symbols=total_symbols,
            api_calls=self.api_calls,
            cache_hits=self.cache_hits,
            elapsed_seconds=elapsed_seconds,
            circuit_breaker_activations=self.circuit_breaker_activations,
            data_coverage_pct=data_coverage_pct,
            errors=self.errors,
        )

        metrics.log_summary()
        return metrics

    @staticmethod
    def log_optimization_status() -> None:
        """Log current optimization phase status."""
        logger.info(
            "[OPTIMIZATION_STATUS] "
            "Phase 1: ✅ Schema integrity (complete), "
            "Phase 2: ✅ Rate limiting (0.3s interval), "
            "Phase 3.1: ✅ 7-day cache (70% reduction), "
            "Phase 3.2: ✅ Cache pre-warming (top 500 symbols), "
            "Phase 4: ⏳ Differential refresh (planned 2026-07-19)"
        )


# Global monitor instance
_global_monitor = PerformanceMonitor()


def get_monitor() -> PerformanceMonitor:
    return _global_monitor

#!/usr/bin/env python3
"""
Timing instrumentation context manager for critical operation profiling.

Usage:
    with TimeBlock("signal_computation"):
        compute_signals()  # Logs duration automatically

The context manager tracks duration and logs to logger. Integration points:
  - CloudWatch metrics (if AWS SDK available)
  - Local logging (always available)
  - Slow operation detection (>500ms for signals, >2s for filtering)
"""

import logging
import time
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Global metrics buffer (persisted per session or sent to CloudWatch)
_metrics_buffer: Dict[str, list] = {}


class TimeBlock:
    """Context manager for operation timing and alerting on slow operations."""

    SLOW_THRESHOLDS = {
        "signal_computation": 0.5,      # 500ms
        "filter_pipeline": 2.0,          # 2s
        "position_sizing": 1.0,          # 1s
        "order_execution": 3.0,          # 3s (includes API round-trip)
        "data_loading": 5.0,             # 5s (loader timeout warning)
        "default": 2.0,                  # 2s generic threshold
    }

    def __init__(self, operation_name: str, log_level: str = "info", raise_on_slow: bool = False):
        """
        Initialize timing context.

        Args:
            operation_name: Name of the operation being timed (e.g., "signal_computation")
            log_level: Logging level ("debug", "info", "warning")
            raise_on_slow: If True, raise exception if operation exceeds threshold
        """
        self.operation_name = operation_name
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.raise_on_slow = raise_on_slow
        self.start_time = None
        self.end_time = None
        self.duration_ms = None

    def __enter__(self):
        self.start_time = time.time()
        logger.log(self.log_level, f"[START] {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000

        # Determine if operation was slow
        threshold_ms = self.SLOW_THRESHOLDS.get(self.operation_name, self.SLOW_THRESHOLDS["default"]) * 1000
        is_slow = self.duration_ms > threshold_ms

        # Log result
        status = "SLOW" if is_slow else "OK"
        log_fn = logger.warning if is_slow else logger.log
        log_fn(
            self.log_level if not is_slow else logging.WARNING,
            f"[{status}] {self.operation_name:30s} | {self.duration_ms:7.1f}ms"
        )

        # Record metric
        if self.operation_name not in _metrics_buffer:
            _metrics_buffer[self.operation_name] = []
        _metrics_buffer[self.operation_name].append({
            "duration_ms": self.duration_ms,
            "timestamp": datetime.now().isoformat(),
            "is_slow": is_slow,
        })

        # Raise if configured and slow
        if self.raise_on_slow and is_slow:
            raise TimeoutError(f"{self.operation_name} exceeded threshold: {self.duration_ms:.1f}ms > {threshold_ms:.1f}ms")

        return False  # Don't suppress exceptions


@contextmanager
def time_operation(operation_name: str, log_level: str = "info"):
    """
    Shorthand for timing an operation block.

    Usage:
        with time_operation("my_operation"):
            do_something()
    """
    with TimeBlock(operation_name, log_level) as timer:
        yield timer


def get_metrics_summary() -> Dict[str, Dict[str, Any]]:
    """
    Get summary statistics of all recorded operations.

    Returns:
        {
            'operation_name': {
                'count': int,
                'total_ms': float,
                'avg_ms': float,
                'min_ms': float,
                'max_ms': float,
                'slow_count': int,
                'slow_pct': float,
            },
            ...
        }
    """
    summary = {}
    for op_name, samples in _metrics_buffer.items():
        if not samples:
            continue
        durations = [s["duration_ms"] for s in samples]
        slow_count = sum(1 for s in samples if s["is_slow"])
        summary[op_name] = {
            "count": len(samples),
            "total_ms": sum(durations),
            "avg_ms": sum(durations) / len(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "slow_count": slow_count,
            "slow_pct": (slow_count / len(samples) * 100) if samples else 0,
        }
    return summary


def log_metrics_summary():
    """Log a summary of all recorded metrics."""
    summary = get_metrics_summary()
    if not summary:
        logger.info("No metrics recorded")
        return

    logger.info("=" * 80)
    logger.info("PERFORMANCE METRICS SUMMARY")
    logger.info("=" * 80)
    for op_name in sorted(summary.keys()):
        stats = summary[op_name]
        logger.info(
            f"{op_name:30s} | "
            f"count={stats['count']:3d} | "
            f"avg={stats['avg_ms']:7.1f}ms | "
            f"min={stats['min_ms']:7.1f}ms | "
            f"max={stats['max_ms']:7.1f}ms | "
            f"slow={stats['slow_count']:2d}/{stats['count']} ({stats['slow_pct']:5.1f}%)"
        )
    logger.info("=" * 80)


def clear_metrics_buffer():
    """Clear all recorded metrics."""
    global _metrics_buffer
    _metrics_buffer = {}

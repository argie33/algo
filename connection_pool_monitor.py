#!/usr/bin/env python3
"""
Connection Pool Monitoring & Health Checks

Monitors database connection pool health:
- Active connections
- Connection wait times
- Failed connection attempts
- Pool exhaustion events
- Connection leaks

Publishes metrics to CloudWatch for alerting.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
from threading import Lock, Thread

import boto3

log = logging.getLogger(__name__)


class ConnectionPoolMonitor:
    """Monitor database connection pool health."""

    def __init__(self, source_name: str = "default", cloudwatch_namespace: str = None):
        """
        Initialize connection pool monitor.

        Args:
            source_name: Name of connection pool (e.g., 'loader_pool', 'worker_pool')
            cloudwatch_namespace: CloudWatch namespace for metrics (auto-determined if None)
        """
        self.source_name = source_name
        self.namespace = cloudwatch_namespace or f"algo/ConnectionPool/{source_name}"

        # Metrics
        self.active_connections = 0
        self.max_connections = 0
        self.failed_attempts = 0
        self.connection_wait_times = []  # Track last 100 wait times
        self.exhaustion_events = 0

        # State tracking
        self._lock = Lock()
        self._cloudwatch = None
        self._last_publish = datetime.utcnow()
        self._publish_interval = timedelta(minutes=1)

        log.info(f"Connection pool monitor initialized: {self.source_name}")

    def _get_cloudwatch(self):
        """Lazy-load CloudWatch client."""
        if self._cloudwatch is None:
            try:
                self._cloudwatch = boto3.client("cloudwatch")
            except Exception as e:
                log.warning(f"CloudWatch not available: {e}")
                self._cloudwatch = False  # Sentinel: tried and failed
        return self._cloudwatch if self._cloudwatch else None

    def record_active_connections(self, count: int, max_connections: int) -> None:
        """Record current active connections."""
        with self._lock:
            self.active_connections = count
            self.max_connections = max_connections

            # Check if approaching limit (80%+)
            if max_connections > 0:
                ratio = (count / max_connections) * 100
                if ratio >= 80:
                    log.warning(f"⚠ Connection pool at {ratio:.1f}% capacity ({count}/{max_connections})")

    def record_connection_wait(self, wait_time_ms: float) -> None:
        """Record time spent waiting for connection from pool."""
        with self._lock:
            self.connection_wait_times.append(wait_time_ms)

            # Keep only last 100 measurements
            if len(self.connection_wait_times) > 100:
                self.connection_wait_times.pop(0)

            # Alert if wait time is excessive (> 5 seconds)
            if wait_time_ms > 5000:
                log.warning(f"⚠ Excessive connection wait time: {wait_time_ms:.0f}ms")

    def record_failed_connection(self, error: str) -> None:
        """Record failed connection attempt."""
        with self._lock:
            self.failed_attempts += 1
            log.error(f"✗ Failed to get connection (attempt #{self.failed_attempts}): {error}")

            # Alert after 3+ failures
            if self.failed_attempts >= 3:
                log.critical(f"✗ Multiple connection failures detected ({self.failed_attempts} attempts)")

    def record_pool_exhaustion(self) -> None:
        """Record connection pool exhaustion event."""
        with self._lock:
            self.exhaustion_events += 1
            log.error(f"✗ Connection pool exhausted (event #{self.exhaustion_events})")

    def get_stats(self) -> Dict:
        """Get current pool statistics."""
        with self._lock:
            stats = {
                "source": self.source_name,
                "active_connections": self.active_connections,
                "max_connections": self.max_connections,
                "utilization_percent": round(
                    (self.active_connections / self.max_connections * 100) if self.max_connections > 0 else 0, 1
                ),
                "failed_attempts": self.failed_attempts,
                "exhaustion_events": self.exhaustion_events,
            }

            # Add wait time statistics
            if self.connection_wait_times:
                wait_times = self.connection_wait_times
                stats["avg_wait_ms"] = round(sum(wait_times) / len(wait_times), 1)
                stats["max_wait_ms"] = round(max(wait_times), 1)
                stats["p95_wait_ms"] = round(sorted(wait_times)[int(len(wait_times) * 0.95)], 1)
            else:
                stats["avg_wait_ms"] = 0
                stats["max_wait_ms"] = 0
                stats["p95_wait_ms"] = 0

            return stats

    def publish_metrics(self) -> None:
        """Publish metrics to CloudWatch."""
        now = datetime.utcnow()

        # Only publish every N seconds to avoid API throttling
        if (now - self._last_publish) < self._publish_interval:
            return

        with self._lock:
            stats = self.get_stats()
            self._publish_to_cloudwatch(stats)
            self._last_publish = now

    def _publish_to_cloudwatch(self, stats: Dict) -> None:
        """Send metrics to CloudWatch."""
        try:
            client = self._get_cloudwatch()
            if not client:
                return

            client.put_metric_data(
                Namespace=self.namespace,
                MetricData=[
                    {
                        "MetricName": "ActiveConnections",
                        "Value": stats["active_connections"],
                        "Unit": "Count",
                        "Timestamp": datetime.utcnow(),
                    },
                    {
                        "MetricName": "UtilizationPercent",
                        "Value": stats["utilization_percent"],
                        "Unit": "Percent",
                        "Timestamp": datetime.utcnow(),
                    },
                    {
                        "MetricName": "FailedAttempts",
                        "Value": stats["failed_attempts"],
                        "Unit": "Count",
                        "Timestamp": datetime.utcnow(),
                    },
                    {
                        "MetricName": "ExhaustionEvents",
                        "Value": stats["exhaustion_events"],
                        "Unit": "Count",
                        "Timestamp": datetime.utcnow(),
                    },
                    {
                        "MetricName": "AvgWaitTime",
                        "Value": stats["avg_wait_ms"],
                        "Unit": "Milliseconds",
                        "Timestamp": datetime.utcnow(),
                    },
                    {
                        "MetricName": "P95WaitTime",
                        "Value": stats["p95_wait_ms"],
                        "Unit": "Milliseconds",
                        "Timestamp": datetime.utcnow(),
                    },
                ],
            )

            log.debug(f"Published pool metrics: {stats['source']} (util: {stats['utilization_percent']}%)")

        except Exception as e:
            log.warning(f"Failed to publish metrics: {e}")

    def reset(self) -> None:
        """Reset metrics (useful after detecting and fixing issues)."""
        with self._lock:
            self.failed_attempts = 0
            self.exhaustion_events = 0
            self.connection_wait_times = []
            log.info(f"Reset metrics for {self.source_name}")


class PoolHealthChecker:
    """Background health check for connection pools."""

    def __init__(self, monitor: ConnectionPoolMonitor, check_interval: int = 60):
        """
        Initialize health checker.

        Args:
            monitor: ConnectionPoolMonitor instance
            check_interval: Seconds between health checks
        """
        self.monitor = monitor
        self.check_interval = check_interval
        self._running = False
        self._thread = None

    def start(self) -> None:
        """Start background health check thread."""
        if self._running:
            return

        self._running = True
        self._thread = Thread(target=self._health_check_loop, daemon=True)
        self._thread.start()
        log.info(f"Health checker started for {self.monitor.source_name}")

    def stop(self) -> None:
        """Stop background health check thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info(f"Health checker stopped for {self.monitor.source_name}")

    def _health_check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            try:
                self._check_pool_health()
                time.sleep(self.check_interval)
            except Exception as e:
                log.error(f"Health check error: {e}")
                time.sleep(5)  # Brief wait before retry

    def _check_pool_health(self) -> None:
        """Check pool health and log warnings."""
        stats = self.monitor.get_stats()

        # Check utilization
        util = stats["utilization_percent"]
        if util >= 90:
            log.critical(
                f"🚨 CRITICAL: Pool at {util:.1f}% capacity - consider scaling or reducing load"
            )
        elif util >= 80:
            log.warning(f"⚠ WARNING: Pool at {util:.1f}% capacity")

        # Check wait times
        if stats["max_wait_ms"] > 10000:
            log.warning(f"⚠ WARNING: Max wait time {stats['max_wait_ms']:.0f}ms (> 10s)")

        # Check failure rate
        if stats["failed_attempts"] > 5:
            log.error(f"✗ ERROR: {stats['failed_attempts']} failed connection attempts")

        # Publish metrics
        self.monitor.publish_metrics()


# Module-level monitors (singleton-like)
_monitors = {}
_monitors_lock = Lock()


def get_pool_monitor(name: str = "default") -> ConnectionPoolMonitor:
    """Get or create connection pool monitor."""
    global _monitors

    with _monitors_lock:
        if name not in _monitors:
            _monitors[name] = ConnectionPoolMonitor(name)
        return _monitors[name]


def get_health_checker(name: str = "default", auto_start: bool = True) -> PoolHealthChecker:
    """Get or create health checker."""
    monitor = get_pool_monitor(name)
    checker = PoolHealthChecker(monitor)

    if auto_start:
        checker.start()

    return checker


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create monitor
    monitor = get_pool_monitor("my_pool")
    monitor.record_active_connections(45, 100)
    monitor.record_connection_wait(125)
    monitor.record_connection_wait(150)

    # Start health check
    checker = get_health_checker("my_pool", auto_start=True)

    # Simulate activity
    try:
        for i in range(10):
            monitor.record_active_connections(50 + i * 5, 100)
            stats = monitor.get_stats()
            print(f"\nStats: {stats}")
            time.sleep(2)
    finally:
        checker.stop()

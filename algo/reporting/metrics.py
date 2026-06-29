#!/usr/bin/env python3

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

NAMESPACE = "AlgoTrading"
REGION = os.getenv("AWS_REGION", "us-east-1")


class MetricsPublisher:
    """Thin wrapper around CloudWatch put_metric_data with batching."""

    def __init__(self, dry_run: bool = False):
        self._dry_run = dry_run
        self._client: Any = None
        self._batch: list[dict[str, Any]] = []

    def _cw(self) -> Any:
        """Get or initialize CloudWatch client. Raises on initialization failure."""
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client("cloudwatch", region_name=REGION)
            except ImportError as e:
                raise RuntimeError(f"Failed to import boto3 for CloudWatch client: {e}") from e
            except Exception as e:
                raise RuntimeError(f"Failed to initialize CloudWatch client (region={REGION}): {e}") from e
        return self._client

    def _emit(
        self,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: dict[str, str] | None = None,
    ) -> None:
        datum: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.now(timezone.utc),
        }
        if dimensions:
            datum["Dimensions"] = [{"Name": k, "Value": v} for k, v in dimensions.items()]

        if self._dry_run:
            logger.info(
                "metrics.dry_run metric=%s value=%s unit=%s dims=%s",
                metric_name,
                value,
                unit,
                dimensions,
            )
            return

        self._batch.append(datum)
        if len(self._batch) >= 20:  # CloudWatch max per call
            self._flush()

    def _flush(self) -> None:
        """Flush buffered metrics to CloudWatch. Non-fatal on auth/permission errors."""
        if not self._batch:
            return

        batch_count = len(self._batch)
        cw = self._cw()

        try:
            cw.put_metric_data(Namespace=NAMESPACE, MetricData=self._batch)
            logger.debug("metrics.flushed count=%d", batch_count)
        except Exception as e:
            error_str = str(e)
            if "not authorized" in error_str.lower() or "accessdenied" in error_str.lower():
                logger.warning(
                    "metrics.skipped (insufficient CloudWatch permission) count=%d error=%s",
                    batch_count,
                    error_str,
                )
            else:
                logger.error(
                    "metrics.flush_failed (unable to publish metrics) count=%d error=%s",
                    batch_count,
                    error_str,
                )
        finally:
            self._batch.clear()

    # ── Public API ────────────────────────────────────────────────────────────

    def put_orchestrator_result(self, success: bool, phase_results: dict[str, Any]) -> None:
        """Publish overall run success/failure + per-phase breakdown.

        Args:
            success: Whether the orchestrator run succeeded
            phase_results: Dict mapping phase_num -> result dict with 'status' key

        Raises:
            ValueError: If phase_results is not a dict or missing required structure
        """
        if not isinstance(phase_results, dict):
            raise ValueError(f"phase_results must be a dict, got {type(phase_results).__name__}")

        self._emit("OrchestratorSuccess", 1 if success else 0)
        self._emit("OrchestratorFailure", 0 if success else 1)

        for phase_num, result in phase_results.items():
            if not isinstance(result, dict):
                raise ValueError(f"phase_results[{phase_num}] must be dict, got {type(result).__name__}")
            if "status" not in result:
                raise ValueError(f"phase_results[{phase_num}] missing 'status' key. Got: {list(result.keys())}")

            phase_ok = result.get("status") in ("success", "halt")
            self._emit(
                "PhaseSuccess",
                1 if phase_ok else 0,
                dimensions={"Phase": str(phase_num)},
            )
            self._emit(
                "PhaseFailure",
                0 if phase_ok else 1,
                dimensions={"Phase": str(phase_num)},
            )

    def put_signal_count(self, signals: int, signal_type: str = "BUY") -> None:
        """How many signals generated today.

        Args:
            signals: Number of signals (must be non-negative)
            signal_type: Signal type label (e.g., 'BUY', 'SELL')

        Raises:
            ValueError: If signals is negative or signal_type is empty
        """
        if not isinstance(signals, int) or signals < 0:
            raise ValueError(f"signals must be non-negative int, got {signals}")
        if not signal_type or not isinstance(signal_type, str):
            raise ValueError(f"signal_type must be non-empty string, got {signal_type!r}")

        self._emit("SignalsGenerated", signals, dimensions={"SignalType": signal_type})

    def put_trade_count(self, trades: int) -> None:
        """How many trades placed in this orchestrator run.

        Args:
            trades: Number of trades executed (must be non-negative)

        Raises:
            ValueError: If trades is negative
        """
        if not isinstance(trades, int) or trades < 0:
            raise ValueError(f"trades must be non-negative int, got {trades}")

        self._emit("TradesExecuted", trades)

    def put_open_positions(self, count: int) -> None:
        """Current open position count.

        Args:
            count: Number of open positions (must be non-negative)

        Raises:
            ValueError: If count is negative
        """
        if not isinstance(count, int) or count < 0:
            raise ValueError(f"count must be non-negative int, got {count}")

        self._emit("OpenPositions", count)

    def put_data_freshness(self, table: str, age_days: float) -> None:
        """Staleness of a critical data table in days.

        Args:
            table: Name of the data table
            age_days: Age of data in days (must be non-negative)

        Raises:
            ValueError: If table is empty or age_days is negative
        """
        if not table or not isinstance(table, str):
            raise ValueError(f"table must be non-empty string, got {table!r}")
        if not isinstance(age_days, (int, float)) or age_days < 0:
            raise ValueError(f"age_days must be non-negative number, got {age_days}")

        self._emit("DataFreshnessAgeDays", age_days, unit="None", dimensions={"Table": table})

    def put_loader_duration(self, loader: str, seconds: float) -> None:
        """Wall-clock seconds for a loader run.

        Args:
            loader: Name of the loader
            seconds: Duration in seconds (must be non-negative)

        Raises:
            ValueError: If loader is empty or seconds is negative
        """
        if not loader or not isinstance(loader, str):
            raise ValueError(f"loader must be non-empty string, got {loader!r}")
        if not isinstance(seconds, (int, float)) or seconds < 0:
            raise ValueError(f"seconds must be non-negative number, got {seconds}")

        self._emit(
            "LoaderDurationSeconds",
            seconds,
            unit="Seconds",
            dimensions={"Loader": loader},
        )

    def put_loader_result(self, loader: str, stats: dict[str, Any]) -> None:
        """Publish OptimalLoader run stats (rows_inserted, symbols_failed, duration_sec)."""
        # Validate required fields are present
        required_fields = ["rows_inserted", "symbols_failed", "duration_sec"]
        missing = [f for f in required_fields if f not in stats]
        if missing:
            raise ValueError(
                f"Loader stats for '{loader}' missing required fields: {missing}. "
                f"Cannot publish incomplete metrics. Available: {list(stats.keys())}"
            )

        dims = {"Loader": loader}
        rows_inserted = stats["rows_inserted"]
        symbols_failed = stats["symbols_failed"]
        duration_sec = stats["duration_sec"]

        # Validate types
        if not isinstance(rows_inserted, (int, float)):
            raise ValueError(f"Loader stats 'rows_inserted' must be numeric, got {type(rows_inserted).__name__}")
        if not isinstance(symbols_failed, (int, float)):
            raise ValueError(f"Loader stats 'symbols_failed' must be numeric, got {type(symbols_failed).__name__}")
        if not isinstance(duration_sec, (int, float)):
            raise ValueError(f"Loader stats 'duration_sec' must be numeric, got {type(duration_sec).__name__}")

        self._emit(
            "LoaderRowsInserted",
            rows_inserted,
            unit="Count",
            dimensions=dims,
        )
        self._emit(
            "LoaderSymbolsFailed",
            symbols_failed,
            unit="Count",
            dimensions=dims,
        )
        self._emit(
            "LoaderDurationSeconds",
            duration_sec,
            unit="Seconds",
            dimensions=dims,
        )

    def add_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: dict[str, str] | None = None,
    ) -> None:
        """Emit a single metric immediately (no batching).

        Args:
            metric_name: Name of the metric (must be non-empty)
            value: Metric value (numeric)
            unit: Measurement unit (default: "Count")
            dimensions: Optional dict of dimension key-value pairs

        Raises:
            ValueError: If metric_name is empty or dimensions is not a dict
        """
        if not metric_name or not isinstance(metric_name, str):
            raise ValueError(f"metric_name must be non-empty string, got {metric_name!r}")
        if not isinstance(value, (int, float)):
            raise ValueError(f"value must be numeric, got {type(value).__name__}")
        if dimensions is not None and not isinstance(dimensions, dict):
            raise ValueError(f"dimensions must be dict or None, got {type(dimensions).__name__}")

        self._emit(metric_name, value, unit, dimensions)
        self._flush()

    def put_circuit_breaker(self, breaker_name: str, fired: bool) -> None:
        """Whether a circuit breaker fired (1=fired, 0=ok).

        Args:
            breaker_name: Name of the circuit breaker (must be non-empty)
            fired: Whether the breaker fired

        Raises:
            ValueError: If breaker_name is empty
        """
        if not breaker_name or not isinstance(breaker_name, str):
            raise ValueError(f"breaker_name must be non-empty string, got {breaker_name!r}")
        if not isinstance(fired, bool):
            raise ValueError(f"fired must be bool, got {type(fired).__name__}")

        self._emit(
            "CircuitBreakerFired",
            1 if fired else 0,
            dimensions={"Breaker": breaker_name},
        )

    def flush(self) -> None:
        """Call at end of run to send any remaining buffered metrics."""
        self._flush()

    def __enter__(self) -> "MetricsPublisher":
        return self

    def __exit__(self, *_: Any) -> None:
        self.flush()

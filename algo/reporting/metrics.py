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
        self._client = None
        self._batch: list[dict] = []

    def _cw(self):
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client("cloudwatch", region_name=REGION)
            except Exception as e:
                raise RuntimeError(f"Operation failed: {e}") from e
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
            datum["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]

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
        if not self._batch:
            return
        cw = self._cw()
        if cw is None:
            self._batch.clear()
            return
        try:
            cw.put_metric_data(Namespace=NAMESPACE, MetricData=self._batch)
            logger.debug(f"metrics.flushed count={len(self._batch)}")
        except Exception as e:
            # Log error but don't fail—metrics are non-critical
            if "not authorized" in str(e) or "AccessDenied" in str(e):
                logger.debug(
                    "metrics.skipped (no CloudWatch permission) count=%d",
                    len(self._batch),
                )
            else:
                logger.warning(
                    "metrics.flush_failed error=%s count=%d", e, len(self._batch)
                )
        finally:
            self._batch.clear()

    # ── Public API ────────────────────────────────────────────────────────────

    def put_orchestrator_result(self, success: bool, phase_results: dict) -> None:
        """Publish overall run success/failure + per-phase breakdown."""
        self._emit("OrchestratorSuccess", 1 if success else 0)
        self._emit("OrchestratorFailure", 0 if success else 1)

        for phase_num, result in phase_results.items():
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
        """How many signals generated today."""
        self._emit("SignalsGenerated", signals, dimensions={"SignalType": signal_type})

    def put_trade_count(self, trades: int) -> None:
        """How many trades placed in this orchestrator run."""
        self._emit("TradesExecuted", trades)

    def put_open_positions(self, count: int) -> None:
        """Current open position count."""
        self._emit("OpenPositions", count)

    def put_data_freshness(self, table: str, age_days: float) -> None:
        """Staleness of a critical data table in days."""
        self._emit(
            "DataFreshnessAgeDays", age_days, unit="None", dimensions={"Table": table}
        )

    def put_loader_duration(self, loader: str, seconds: float) -> None:
        """Wall-clock seconds for a loader run."""
        self._emit(
            "LoaderDurationSeconds",
            seconds,
            unit="Seconds",
            dimensions={"Loader": loader},
        )

    def put_loader_result(self, loader: str, stats: dict) -> None:
        """Publish OptimalLoader run stats (rows_inserted, symbols_failed, duration_sec)."""
        dims = {"Loader": loader}
        self._emit(
            "LoaderRowsInserted",
            stats.get("rows_inserted", 0),
            unit="Count",
            dimensions=dims,
        )
        self._emit(
            "LoaderSymbolsFailed",
            stats.get("symbols_failed", 0),
            unit="Count",
            dimensions=dims,
        )
        self._emit(
            "LoaderDurationSeconds",
            stats.get("duration_sec", 0.0),
            unit="Seconds",
            dimensions=dims,
        )

    def add_metric(self, metric_name: str, value: float, unit: str = "Count", dimensions: dict[str, str] | None = None) -> None:
        """Emit a single metric immediately (no batching)."""
        self._emit(metric_name, value, unit, dimensions)
        self._flush()

    def put_circuit_breaker(self, breaker_name: str, fired: bool) -> None:
        """Whether a circuit breaker fired (1=fired, 0=ok)."""
        self._emit(
            "CircuitBreakerFired",
            1 if fired else 0,
            dimensions={"Breaker": breaker_name},
        )

    def flush(self) -> None:
        """Call at end of run to send any remaining buffered metrics."""
        self._flush()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.flush()

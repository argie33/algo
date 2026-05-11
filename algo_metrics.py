#!/usr/bin/env python3
"""
CloudWatch metrics publisher for the algo trading platform.

Publishes a consistent set of metrics after each orchestrator run so that
CloudWatch Alarms can page on failures without anyone needing to read logs.

Namespace: AlgoTrading

Key metrics:
    OrchestratorSuccess     Count   1=success, 0=failure
    PhaseSuccess            Count   1=ok, 0=fail; Dimension: Phase=1..7
    SignalsGenerated        Count   Raw BUY signal count for the day
    TradesExecuted          Count   Trades placed in this run
    OpenPositions           Count   Current open position count
    DataFreshnessAgeDays    Gauge   Max staleness across critical tables
    LoaderDurationSeconds   Gauge   Wall-clock time for each loader

Alarm targets (Terraform should wire these up):
    OrchestratorSuccess < 1 for 1 datapoint  → page on-call
    DataFreshnessAgeDays > 3 for 2 datapoints → notify data team
    SignalsGenerated = 0 for 3 consecutive days → notify algo team

Usage:
    from algo_metrics import MetricsPublisher
    m = MetricsPublisher()
    m.put_orchestrator_result(success=True, phase_results={...})
    m.put_signal_count(signals=142)
    m.put_trade_count(trades=3)
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

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
                log.warning("CloudWatch client unavailable: %s", e)
                return None
        return self._client

    def _emit(self, metric_name: str, value: float, unit: str = "Count",
              dimensions: Optional[Dict[str, str]] = None) -> None:
        datum: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.now(timezone.utc),
        }
        if dimensions:
            datum["Dimensions"] = [{"Name": k, "Value": v} for k, v in dimensions.items()]

        if self._dry_run:
            log.info("metrics.dry_run metric=%s value=%s unit=%s dims=%s",
                     metric_name, value, unit, dimensions)
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
            log.debug("metrics.flushed count=%d", len(self._batch))
        except Exception as e:
            log.error("metrics.flush_failed error=%s count=%d", e, len(self._batch))
        finally:
            self._batch.clear()

    # ── Public API ────────────────────────────────────────────────────────────

    def put_orchestrator_result(self, success: bool, phase_results: Dict) -> None:
        """Publish overall run success/failure + per-phase breakdown."""
        self._emit("OrchestratorSuccess", 1 if success else 0)
        self._emit("OrchestratorFailure", 0 if success else 1)

        for phase_num, result in phase_results.items():
            phase_ok = result.get("status") in ("success", "halt")
            self._emit("PhaseSuccess", 1 if phase_ok else 0,
                       dimensions={"Phase": str(phase_num)})
            self._emit("PhaseFailure", 0 if phase_ok else 1,
                       dimensions={"Phase": str(phase_num)})

    def put_signal_count(self, signals: int, signal_type: str = "BUY") -> None:
        """How many signals generated today."""
        self._emit("SignalsGenerated", signals,
                   dimensions={"SignalType": signal_type})

    def put_trade_count(self, trades: int) -> None:
        """How many trades placed in this orchestrator run."""
        self._emit("TradesExecuted", trades)

    def put_open_positions(self, count: int) -> None:
        """Current open position count."""
        self._emit("OpenPositions", count)

    def put_data_freshness(self, table: str, age_days: float) -> None:
        """Staleness of a critical data table in days."""
        self._emit("DataFreshnessAgeDays", age_days, unit="None",
                   dimensions={"Table": table})

    def put_loader_duration(self, loader: str, seconds: float) -> None:
        """Wall-clock seconds for a loader run."""
        self._emit("LoaderDurationSeconds", seconds, unit="Seconds",
                   dimensions={"Loader": loader})

    def put_circuit_breaker(self, breaker_name: str, fired: bool) -> None:
        """Whether a circuit breaker fired (1=fired, 0=ok)."""
        self._emit("CircuitBreakerFired", 1 if fired else 0,
                   dimensions={"Breaker": breaker_name})

    def flush(self) -> None:
        """Call at end of run to send any remaining buffered metrics."""
        self._flush()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.flush()

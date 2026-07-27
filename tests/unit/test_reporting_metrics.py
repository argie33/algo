#!/usr/bin/env python3
"""Regression coverage for MetricsPublisher.put_orchestrator_result's phase-status
classification (algo/reporting/metrics.py).

Bug: phase_ok only recognized "ok"/"degraded" as successful, diverging from
PhaseResult.ok (algo/orchestrator/phase_result.py) which also treats "skipped" and
"blocked" as successful outcomes. Result: CloudWatch reported PhaseFailure=1 and
OrchestratorFailure=1 for a perfectly healthy run whenever a phase was correctly
"blocked" (e.g. Phase 8's market-hours guard) or "skipped" (a downstream phase after
an upstream halt) - a false page waiting to happen in production alerting.
"""

from algo.orchestrator.phase_result import PhaseResult
from algo.reporting.metrics import MetricsPublisher


def _publisher(monkeypatch):
    monkeypatch.delenv("LOCAL_MODE", raising=False)
    publisher = MetricsPublisher(dry_run=False)
    assert publisher._dry_run is False
    return publisher


def _phase_failure_value(batch, phase):
    matches = [
        d["Value"]
        for d in batch
        if d["MetricName"] == "PhaseFailure" and {"Name": "Phase", "Value": str(phase)} in d.get("Dimensions", [])
    ]
    assert matches, f"No PhaseFailure metric emitted for phase {phase}"
    return matches[0]


def test_blocked_phase_is_not_reported_as_failure(monkeypatch):
    """Phase 8 correctly blocked by the market-hours guard must not emit PhaseFailure=1."""
    publisher = _publisher(monkeypatch)
    phase_results = {
        8: {"status": "blocked", "phase": 8, "name": "entry_execution", "summary": "market hours guard"},
        9: {"status": "ok", "phase": 9, "name": "reconciliation", "summary": "ok"},
    }
    publisher.put_orchestrator_result(True, phase_results)

    assert _phase_failure_value(publisher._batch, 8) == 0
    assert PhaseResult(status="blocked").ok is True


def test_skipped_phase_is_not_reported_as_failure(monkeypatch):
    """A phase intentionally skipped after an upstream halt must not emit PhaseFailure=1."""
    publisher = _publisher(monkeypatch)
    phase_results = {
        4: {"status": "skipped", "phase": 4, "name": "reconciliation", "summary": "skipped after halt"},
    }
    publisher.put_orchestrator_result(False, phase_results)

    assert _phase_failure_value(publisher._batch, 4) == 0
    assert PhaseResult(status="skipped").ok is True


def test_error_phase_is_still_reported_as_failure(monkeypatch):
    """A genuine error must still emit PhaseFailure=1 - the fix must not paper over real failures."""
    publisher = _publisher(monkeypatch)
    phase_results = {
        1: {"status": "error", "phase": 1, "name": "data_freshness", "summary": "boom"},
    }
    publisher.put_orchestrator_result(False, phase_results)

    assert _phase_failure_value(publisher._batch, 1) == 1
    assert PhaseResult(status="error").ok is False


def test_halted_phase_is_still_reported_as_failure(monkeypatch):
    """A circuit-breaker halt must still emit PhaseFailure=1."""
    publisher = _publisher(monkeypatch)
    phase_results = {
        2: {"status": "halted", "phase": 2, "name": "circuit_breakers", "summary": "halted"},
    }
    publisher.put_orchestrator_result(False, phase_results)

    assert _phase_failure_value(publisher._batch, 2) == 1
    assert PhaseResult(status="halted").ok is False

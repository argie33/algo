#!/usr/bin/env python3
"""Regression test: /api/algo/circuit-breakers 503 (stale/missing data) must fail fast.

Reproduces the live bug (2026-08-17): when today's `circuit_breaker_status` row hasn't
been computed yet by the orchestrator, the endpoint fail-closes with a 503 whose
errorType is one of the circuit-breaker "data not ready" reasons (e.g.
stale_circuit_breaker_data). This condition cannot resolve within a retry window - it
only clears once the orchestrator finishes its run. Before the fix, api_call() retried
it 4 times with exponential backoff (~12s), then set `_is_transient_503`, triggering a
*second* retry loop in dashboard/fetchers.py's one() wrapper - burning real seconds on
every dashboard load/refresh for a condition retrying can never fix. Observed live as:
"[DATA_QUALITY] cb: api_call/api_error - API error 503 after 4 attempts".
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from dashboard.api_data_layer import api_call


@pytest.fixture(autouse=True)
def reset_circuit_breaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset circuit breaker state before each test."""
    import dashboard.api_data_layer as api_layer

    monkeypatch.setattr(api_layer, "_circuit_breaker_state", "closed")
    monkeypatch.setattr(api_layer, "_circuit_breaker_failures", 0)
    monkeypatch.setattr(api_layer, "_circuit_breaker_reset_time", None)


@pytest.mark.parametrize(
    "error_type",
    [
        "missing_critical_tables",
        "missing_circuit_breaker_data",
        "stale_circuit_breaker_data",
        "incomplete_circuit_breaker_data",
        "circuit_breaker_computation_error",
        "missing_vix_data",
        "vix_computation_error",
        "missing_spy_price_data",
        "market_health_computation_error",
    ],
)
def test_circuit_breaker_non_transient_503_fails_fast_no_retry(error_type: str) -> None:
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:3001"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            with patch("dashboard.api_data_layer.time.sleep") as mock_sleep:
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.text = "Service Unavailable"
                mock_resp.json.return_value = {
                    "statusCode": 503,
                    "breakers": [],
                    "any_triggered": True,
                    "triggered_count": 0,
                    "errorType": error_type,
                    "message": "Circuit breaker data unavailable. Trading disabled.",
                    "_error": "Circuit breaker data unavailable. Trading disabled.",
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/circuit-breakers")

                # Exactly one attempt - no retry loop for a condition that can't resolve mid-retry
                assert mock_get.call_count == 1
                mock_sleep.assert_not_called()

                # Must NOT be marked transient, or fetchers.py's own retry wrapper would
                # add a second (redundant) retry loop on top
                assert result.get("_is_transient_503") is not True
                assert "_error" in result
                assert "503" in result["_error"]


def test_circuit_breaker_stale_503_error_message_not_the_after_4_attempts_form() -> None:
    """The old bug's exact symptom string must not reappear for this errorType."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:3001"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            with patch("dashboard.api_data_layer.time.sleep"):
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.text = "Service Unavailable"
                mock_resp.json.return_value = {
                    "statusCode": 503,
                    "breakers": [],
                    "any_triggered": True,
                    "triggered_count": 0,
                    "errorType": "stale_circuit_breaker_data",
                    "message": "Circuit breaker data is for 2026-08-14 but expected 2026-08-17.",
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/circuit-breakers")

                assert "after 4 attempts" not in result.get("_error", "")


def test_generic_503_without_recognized_error_type_still_retries() -> None:
    """A genuinely transient 5xx (unknown/absent errorType) must keep the existing retry behavior."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:3001"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            with patch("dashboard.api_data_layer.time.sleep") as mock_sleep:
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.text = "Service Unavailable"
                mock_resp.json.return_value = {"statusCode": 503, "message": "Lambda cold start"}
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/circuit-breakers")

                # Unrecognized errorType (or none) - retries as before (4 total attempts)
                assert mock_get.call_count == 4
                assert mock_sleep.call_count == 3
                assert result.get("_is_transient_503") is True
                assert "after 4 attempts" in result["_error"]


def test_deprecated_endpoint_still_flagged_and_fails_fast() -> None:
    """Pre-existing deprecated_endpoint fail-fast behavior must be preserved."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:3001"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            with patch("dashboard.api_data_layer.time.sleep") as mock_sleep:
                mock_resp = MagicMock()
                mock_resp.status_code = 503
                mock_resp.text = "Service Unavailable"
                mock_resp.json.return_value = {
                    "statusCode": 503,
                    "errorType": "deprecated_endpoint",
                    "message": "Use /api/algo/v2/foo instead",
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/old-endpoint")

                assert mock_get.call_count == 1
                mock_sleep.assert_not_called()
                assert result.get("_endpoint_deprecated") is True
                assert result.get("_is_transient_503") is not True

#!/usr/bin/env python3
"""Regression tests for CircuitBreaker._check_market_stage's own halt-decision logic -
continuing the 2026-08-24 test-coverage-completeness sweep onto the circuit breaker layer.

The underlying _resolve_current_market_stage() (stage/trend lookup + staleness handling) is
already exercised by test_circuit_breaker.py, but the wrapper that actually decides whether
Stage 4 halts new entries (_check_market_stage) had no dedicated test of its own decision logic.
"""

from datetime import date
from unittest.mock import Mock, patch

import pytest

from algo.risk import CircuitBreaker


@pytest.fixture
def circuit_breaker():
    return CircuitBreaker(config={"circuit_breaker_enabled": True})


class TestCheckMarketStage:
    def test_stage_4_halts(self, circuit_breaker):
        with patch.object(circuit_breaker, "_resolve_current_market_stage", return_value=(4, "downtrend", None)):
            result = circuit_breaker._check_market_stage(date(2026, 8, 24), Mock())
        assert result["halted"] is True
        assert "Stage 4" in result["reason"]
        assert result["value"] == 4

    @pytest.mark.parametrize("stage", [1, 2, 3])
    def test_stages_1_through_3_do_not_halt(self, circuit_breaker, stage):
        with patch.object(circuit_breaker, "_resolve_current_market_stage", return_value=(stage, "uptrend", None)):
            result = circuit_breaker._check_market_stage(date(2026, 8, 24), Mock())
        assert result["halted"] is False
        assert result["value"] == stage

    def test_upstream_halt_reason_propagates_and_halts(self, circuit_breaker):
        """When _resolve_current_market_stage itself fail-closed halts (stale/missing data),
        _check_market_stage must halt too, not silently proceed with stage=None."""
        with patch.object(
            circuit_breaker,
            "_resolve_current_market_stage",
            return_value=(None, "unknown", "Market calendar unavailable"),
        ):
            result = circuit_breaker._check_market_stage(date(2026, 8, 24), Mock())
        assert result["halted"] is True
        assert result["reason"] == "Market calendar unavailable"

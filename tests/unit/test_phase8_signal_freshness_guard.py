"""Regression test: Phase 8 entry execution must block new entries when signals are stale.

algo/risk/stale_signal_circuit_breaker.py's StaleSignalCircuitBreaker was written
("ROOT CAUSE #4 fix") specifically to catch trading on signals computed from stale price
data, but was never actually called from anywhere in the orchestrator - it existed purely
as dead code. Phase 1 validates price_daily/market_health/market_exposure freshness but
explicitly excludes buy_sell_daily (not generated yet at that point in the run); nothing
downstream ever verified the signals Phase 8 trades on are fresh relative to the price
data they were computed from. Wired into Phase 8 as a guard, mirroring the existing
market-hours/pending-orders guard pattern (block this run, don't halt orchestration).
"""

from datetime import date, datetime, time
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import run


def _base_kwargs(execution_mode="paper"):
    return {
        "config": {"execution_mode": execution_mode},
        "run_date": date(2026, 7, 26),
        "dry_run": True,
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
    }


def test_blocks_entries_when_signals_stale():
    market_hours_now = datetime.combine(date(2026, 7, 27), time(11, 0))

    with (
        patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt,
        patch(
            "algo.risk.stale_signal_circuit_breaker.StaleSignalCircuitBreaker.check_signal_freshness",
            return_value=(False, "Signals lag price data by 2d (signals from old data)"),
        ),
    ):
        mock_dt.now.return_value = market_hours_now
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs())

    assert result.status == "blocked"
    assert result.halted is False
    assert result.data["entered"] == 0
    assert "stale" in result.error.lower() or "lag" in result.error.lower()


def test_does_not_block_when_signals_fresh():
    """Sanity check: a fresh-signals result must NOT short-circuit via the new guard -
    the run must proceed past it (verified by reaching a later, different failure point
    rather than immediately returning "blocked" for signal freshness)."""
    market_hours_now = datetime.combine(date(2026, 7, 27), time(11, 0))

    with (
        patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt,
        patch(
            "algo.risk.stale_signal_circuit_breaker.StaleSignalCircuitBreaker.check_signal_freshness",
            return_value=(True, "Signals FRESH"),
        ),
    ):
        mock_dt.now.return_value = market_hours_now
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs())

    # Must NOT be blocked for signal-freshness reasons specifically.
    assert not (result.status == "blocked" and "freshness" in (result.error or "").lower())

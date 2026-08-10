"""Regression test for a live-money fail-open bug in _compute_performance_metrics()
(algo/orchestrator/phase9_reconciliation.py), found 2026-08-10 alongside the identical
pattern already fixed in algo/risk/circuit_breaker.py's consecutive-losses check.

The live-Sharpe circuit breaker (the check that halts real-money trading when rolling
Sharpe falls below min_live_sharpe_ratio) only evaluates when `is_live_trading` is True,
computed as `execution_mode == "auto" and not alpaca_paper_trading`. `alpaca_paper_trading`
used to be read via `config.get("alpaca_paper_trading", True)` - if that key were ever
missing while actually running live (execution_mode="auto"), this would silently compute
alpaca_paper_trading=True, so is_live_trading=False, and the entire live-Sharpe safety
gate would be skipped - not loosened, skipped - even though real capital was at risk.

Every other consumer of this config key in the codebase fails fast instead of guessing
(see phase6_exit_execution.py, phase8_entry_execution.py, alpaca_broker_adapter.py,
execution_config.py, alpaca_sync_manager.py, infrastructure/reconciliation.py, and
circuit_breaker.py's own consecutive-losses check). Fixed to match: missing
alpaca_paper_trading now raises ValueError instead of defaulting to "paper" (safe-looking
but actually disables the gate for live runs).
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase9_reconciliation import _compute_performance_metrics

LOW_SHARPE_WARNING_REPORT = {
    "status": "warning",
    "rolling_sharpe_252d": 0.1,
    "win_rate_50t": 40.0,
    "expectancy": 1.0,
    "warning": "Sharpe below 70% of backtest",
}


def _run(config):
    log_calls = []

    def fake_log(*args, **kwargs):
        log_calls.append((args, kwargs))

    with patch("algo.reporting.LivePerformance") as mock_perf_cls:
        mock_perf_cls.return_value.generate_daily_report.return_value = LOW_SHARPE_WARNING_REPORT
        _compute_performance_metrics(config, date(2026, 8, 10), fake_log)
    return log_calls


class TestSharpeHaltRequiresExplicitPaperFlag:
    def test_missing_alpaca_paper_trading_key_fails_fast_not_silently_skips_gate(self):
        config = {
            "execution_mode": "auto",
            "min_live_sharpe_ratio": "1.0",
            # alpaca_paper_trading deliberately absent
        }
        # _compute_performance_metrics wraps ValueError/RuntimeError into a RuntimeError
        # ("[PHASE 9] Data quality error...") before it propagates - see its own
        # `except (RuntimeError, ValueError) as rv_e` block. Still fails loud, just a
        # different exception type at the boundary; assert on the wrapped message instead.
        with pytest.raises(RuntimeError, match="alpaca_paper_trading"):
            _run(config)

    def test_explicit_live_mode_with_bad_sharpe_still_halts(self):
        """Existing behavior preserved: execution_mode=auto + alpaca_paper_trading=False +
        Sharpe below threshold must still raise the CRITICAL RuntimeError."""
        config = {
            "execution_mode": "auto",
            "alpaca_paper_trading": False,
            "min_live_sharpe_ratio": "1.0",
        }
        with pytest.raises(RuntimeError, match="LIVE TRADING MODE"):
            _run(config)

    def test_explicit_paper_mode_with_bad_sharpe_does_not_halt(self):
        """Existing behavior preserved: paper mode never triggers the live-money halt,
        even with a bad Sharpe ratio."""
        config = {
            "execution_mode": "auto",
            "alpaca_paper_trading": True,
            "min_live_sharpe_ratio": "1.0",
        }
        _run(config)  # must not raise

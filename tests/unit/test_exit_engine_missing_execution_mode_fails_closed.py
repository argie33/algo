"""Regression test for a fail-open bug in ExitEngine._fetch_alpaca_quote's 401/404 handlers
(algo/trading/exit_engine.py), found 2026-08-10 - same bug class as the Phase 9 live-Sharpe
fail-open fix (algo/orchestrator/phase9_reconciliation.py) fixed alongside it.

Both handlers used `self.config.get("execution_mode", "paper")`: if execution_mode were ever
missing, this silently took the "paper/dry sandbox" branch - falling back to stale database
prices - instead of the live-trading hard-stop, for the highest-stakes call site in the
codebase (real-time stop-loss/exit pricing). Phase 6 validates execution_mode is present
before invoking any exit check (phase6_exit_execution.py), so this should be unreachable
through the real orchestrator path, but ExitEngine is a shared class not guaranteed to only
ever be called through Phase 6. Fixed to raise RuntimeError instead of guessing.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config_missing_execution_mode():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        # execution_mode deliberately absent
        "alpaca_paper_trading": True,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


class TestMissingExecutionModeFailsClosed:
    def test_401_with_missing_execution_mode_raises_not_silently_paper(
        self, mock_config_missing_execution_mode
    ):
        engine = _engine(mock_config_missing_execution_mode)
        unauthorized = MagicMock(status_code=401, text="unauthorized")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.exit_engine.requests.get", return_value=unauthorized),
        ):
            with pytest.raises(RuntimeError, match="execution_mode config missing"):
                engine._fetch_alpaca_quote("AAPL")

    def test_404_with_missing_execution_mode_raises_not_silently_paper(
        self, mock_config_missing_execution_mode
    ):
        engine = _engine(mock_config_missing_execution_mode)
        not_found = MagicMock(status_code=404, text="not found")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.exit_engine.requests.get", return_value=not_found),
        ):
            with pytest.raises(RuntimeError, match="execution_mode config missing"):
                engine._fetch_alpaca_quote("AAPL")

    def test_401_explicit_paper_mode_still_falls_back(self):
        """Existing behavior preserved: explicit paper mode still degrades gracefully."""
        config = {
            "min_hold_days": 1,
            "max_hold_days": 60,
            "eight_week_rule_threshold_pct": 20.0,
            "eight_week_rule_window_days": 21,
            "exit_on_distribution_day": False,
            "max_distribution_days": 3,
            "move_be_at_r": 1.0,
            "chandelier_atr_mult": 3.0,
            "use_chandelier_trail": False,
            "exit_on_td_sequential": False,
            "exit_on_rs_line_break_50dma": False,
            "require_target_pullback": True,
            "execution_mode": "paper",
            "alpaca_paper_trading": True,
        }
        engine = _engine(config)
        unauthorized = MagicMock(status_code=401, text="unauthorized")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.exit_engine.requests.get", return_value=unauthorized),
        ):
            result = engine._fetch_alpaca_quote("AAPL")

        assert isinstance(result, dict)
        assert result.get("data_unavailable") is True

    def test_401_explicit_live_mode_still_hard_stops(self):
        """Existing behavior preserved: explicit live mode still hard-stops on 401."""
        config = {
            "min_hold_days": 1,
            "max_hold_days": 60,
            "eight_week_rule_threshold_pct": 20.0,
            "eight_week_rule_window_days": 21,
            "exit_on_distribution_day": False,
            "max_distribution_days": 3,
            "move_be_at_r": 1.0,
            "chandelier_atr_mult": 3.0,
            "use_chandelier_trail": False,
            "exit_on_td_sequential": False,
            "exit_on_rs_line_break_50dma": False,
            "require_target_pullback": True,
            "execution_mode": "auto",
            "alpaca_paper_trading": False,
        }
        engine = _engine(config)
        unauthorized = MagicMock(status_code=401, text="unauthorized")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.exit_engine.requests.get", return_value=unauthorized),
        ):
            with pytest.raises(RuntimeError, match="LIVE trading mode"):
                engine._fetch_alpaca_quote("AAPL")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

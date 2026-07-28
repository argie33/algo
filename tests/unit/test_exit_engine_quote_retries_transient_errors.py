"""Regression test: ExitEngine._fetch_alpaca_quote made exactly one attempt - same bug class
as order_manager.py's send/cancel fixes and position_monitor.py's cancel/qty fixes. A
transient Alpaca 429/503 fell into the generic `else: raise` branch immediately, and this
quote feeds real-time stop-loss/exit evaluation directly - the highest-stakes instance of this
bug class, since a retryable API blip could silently cost a real exit check for one symbol
this cycle.

Fixed by giving the quote fetch the same up-to-3-attempt retry loop already used elsewhere.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config():
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
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _quote_response(status_code, bp=100.0, ap=100.5):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {"quotes": {"AAPL": {"bp": bp, "ap": ap}}}
    return resp


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


class TestFetchAlpacaQuoteRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_midpoint(self, mock_config):
        engine = _engine(mock_config)
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.trading.exit_engine.requests.get",
                side_effect=[rate_limited, _quote_response(200)],
            ),
            patch("algo.trading.exit_engine.time.sleep") as mock_sleep,
        ):
            price = engine._fetch_alpaca_quote("AAPL")

        assert price == 100.25
        mock_sleep.assert_called_once()

    def test_503_exhausts_retries_then_raises(self, mock_config):
        engine = _engine(mock_config)
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.trading.exit_engine.requests.get", return_value=unavailable
            ) as mock_get,
            patch("algo.trading.exit_engine.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="503"):
                engine._fetch_alpaca_quote("AAPL")

        assert mock_get.call_count == 3

    def test_404_does_not_retry(self, mock_config):
        engine = _engine(mock_config)
        not_found = MagicMock(status_code=404, text="not found")

        with (
            patch(
                "algo.trading.exit_engine.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch("algo.trading.exit_engine.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.exit_engine.requests.get", return_value=not_found) as mock_get,
        ):
            price = engine._fetch_alpaca_quote("AAPL")

        assert price is None
        assert mock_get.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

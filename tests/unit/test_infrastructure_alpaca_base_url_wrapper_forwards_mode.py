"""Regression test: algo.infrastructure.config.main.get_alpaca_base_url() (re-exported as
algo.infrastructure.get_alpaca_base_url - a natural top-level import path) must forward
execution_mode to config.api_endpoints.get_alpaca_base_url() rather than silently dropping it.

Found live 2026-07-28: this wrapper previously called the delegate with zero arguments,
always hitting its weakest fallback branch (bare APCA_API_BASE_URL-presence check, no
ALGO_LIVE_TRADING acknowledgment required) regardless of the caller's actual execution_mode.
No current caller reaches this exact import path, but it sat as a live footgun for real-money
account routing on a common top-level import surface.
"""

from unittest.mock import patch

from algo.infrastructure.config.main import get_alpaca_base_url


class TestAlpacaBaseUrlWrapperForwardsExecutionMode:
    def test_forwards_execution_mode_to_delegate(self):
        with patch("algo.config.api_endpoints.get_alpaca_base_url") as mock_delegate:
            mock_delegate.return_value = "https://paper-api.alpaca.markets"
            get_alpaca_base_url("auto")
            mock_delegate.assert_called_once_with("auto")

    def test_forwards_none_when_omitted(self):
        with patch("algo.config.api_endpoints.get_alpaca_base_url") as mock_delegate:
            mock_delegate.return_value = "https://paper-api.alpaca.markets"
            get_alpaca_base_url()
            mock_delegate.assert_called_once_with(None)

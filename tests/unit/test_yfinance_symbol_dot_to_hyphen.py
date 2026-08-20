"""Regression test for the 2026-08-19 fix (goal session continuation - "which factor inputs
are missing the most" audit): yfinance-backed loaders silently lost real analyst/financials
coverage for every dot-suffixed multi-class share ticker (BRK.B, BF.B, HEI.A, LEN.B, ...).

Live-verified directly against yfinance: `yf.Ticker("BRK.B").earnings_estimate` returns an
empty DataFrame (indistinguishable from "no analyst coverage") while
`yf.Ticker("BRK-B").earnings_estimate` returns real, current consensus data - yfinance expects
a hyphen for multi-class share tickers, not this codebase's own NYSE/NASDAQ dot convention.
23 active symbols affected, including large, well-covered names (BRK.A/BRK.B, HEI.A, LEN.B,
MOG.A/MOG.B, TAP.A, GEF.B, WSO.B).
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.external.yfinance_symbol import to_yfinance_symbol


class TestToYfinanceSymbol:
    @pytest.mark.parametrize(
        ("internal_symbol", "expected"),
        [
            ("BRK.B", "BRK-B"),
            ("BRK.A", "BRK-A"),
            ("BF.B", "BF-B"),
            ("HEI.A", "HEI-A"),
            ("AAPL", "AAPL"),  # no dot - unchanged
            ("MSFT", "MSFT"),
        ],
    )
    def test_dot_converted_to_hyphen(self, internal_symbol, expected):
        assert to_yfinance_symbol(internal_symbol) == expected


class TestFetchWithCircuitBreakerUsesConvertedSymbol:
    """The conversion must actually reach the yf.Ticker() call, not just exist as an
    unused helper - asserts the real argument yfinance receives."""

    def test_dot_suffixed_symbol_is_converted_before_reaching_yf_ticker(self):
        from utils.external.yfinance_analyst_ratings import _fetch_with_circuit_breaker

        mock_ticker_instance = MagicMock()
        mock_ticker_instance.upgrades_downgrades = None

        with (
            patch("utils.external.yfinance_analyst_ratings.get_circuit_breaker") as mock_get_cb,
            patch("utils.loaders.retry_helper.time.sleep"),
            patch("yfinance.Ticker", return_value=mock_ticker_instance) as mock_ticker_class,
        ):
            mock_get_cb.return_value = MagicMock()
            _fetch_with_circuit_breaker("BRK.B", "upgrades_downgrades")

        mock_ticker_class.assert_called_once_with("BRK-B")

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


class TestToYfinanceSymbolPreferredShares:
    """FIXED 2026-08-21 (goal session): to_yfinance_symbol only handled the '.'-suffix
    (multi-class share) case, silently dropping the '$'-suffix (preferred/depositary
    share) conversion that utils/data/source_router.py's independent copy of this same
    logic already had since 2026-08-03. Every '$'-suffix symbol reaching yf.Ticker() via
    this function's 6 call sites (analyst ratings, analyst estimates, financials, the
    quality/growth-metrics yfinance fallback, sec_valuations' sanity check) 404'd/returned
    empty, indistinguishable from genuine "no coverage" - live-confirmed for SCE$L (SCE
    Trust VI), which is `active=true` in the local DB with no name-based exclusion.
    """

    @pytest.mark.parametrize(
        ("internal_symbol", "expected"),
        [
            ("MET$E", "MET-PE"),
            ("BAC$E", "BAC-PE"),
            ("SCE$L", "SCE-PL"),
            ("AHL$D", "AHL-PD"),
        ],
    )
    def test_dollar_suffix_converted_to_dash_p(self, internal_symbol, expected):
        assert to_yfinance_symbol(internal_symbol) == expected

    def test_matches_source_router_normalization(self):
        """The two call sites must never drift apart again - see the module docstring."""
        from utils.data.source_router import _normalize_yfinance_symbol

        for symbol in ("BRK.B", "MET$E", "SCE$L", "AAPL"):
            assert to_yfinance_symbol(symbol) == _normalize_yfinance_symbol(symbol)


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

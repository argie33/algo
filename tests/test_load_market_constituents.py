#!/usr/bin/env python3
"""Regression test: real NYSE dual-class common stock must not be dropped from the
tradable universe by the dot-suffix symbol regex.

`_fetch_nasdaq_symbols` used to reject any symbol matching `^[A-Z]+\\.[A-Z]$` on the
theory that a single-letter dot suffix meant "preferred share". Live-verified against
nasdaqtrader.com's own otherlisted.txt feed: this pattern actually matches BRK.A/BRK.B
(Berkshire Hathaway), BF.A/BF.B (Brown-Forman), HEI.A (Heico), MOG.A/MOG.B (Moog), and
~20 other genuine, actively-traded common stocks - all silently excluded from
stock_symbols with no log line, no data_unavailable marker, nothing. The one real
preferred-share symbol using this exact dot pattern (PBR.A, Petrobras ADS) has
"Preferred Shares" directly in its Security Name and was already being caught by the
separate `\\bpreferred\\b` name-text exclusion - the regex was actively harmful and
caught nothing the name-based check didn't already catch correctly.
"""

from unittest.mock import MagicMock, patch

from loaders.load_market_constituents import MarketConstituentsLoader

_HEADER = "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol"
_NASDAQ_HEADER = "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares"


def _row(symbol: str, name: str, test_issue: str = "N") -> str:
    return f"{symbol}|{name}|N|{symbol}|N|100|{test_issue}|{symbol}"


def _nasdaq_row(symbol: str, name: str, test_issue: str = "N") -> str:
    return f"{symbol}|{name}|Q|{test_issue}|N|100|N|N"


def _make_loader() -> MarketConstituentsLoader:
    return MarketConstituentsLoader.__new__(MarketConstituentsLoader)


def test_dual_class_common_stock_is_not_excluded() -> None:
    other_text = "\n".join(
        [
            _HEADER,
            _row("BRK.A", "Berkshire Hathaway Inc. Common Stock"),
            _row("BF.A", "Brown Forman Inc Class A Common Stock"),
        ]
    )
    nasdaq_response = MagicMock(text=_HEADER)
    other_response = MagicMock(text=other_text)

    loader = _make_loader()
    with patch(
        "loaders.load_market_constituents.requests.get",
        side_effect=[nasdaq_response, other_response],
    ), patch("loaders.load_market_constituents.validate_url", return_value=(True, "")):
        rows = loader._fetch_nasdaq_symbols()

    symbols = {r["symbol"] for r in rows}
    assert "BRK.A" in symbols
    assert "BF.A" in symbols


def test_preferred_share_still_excluded_by_name_not_symbol_shape() -> None:
    other_text = "\n".join(
        [
            _HEADER,
            _row("PBR.A", "Petroleo Brasileiro S.A. Petrobras American Depositary Shares representing Preferred Shares"),
            _row("BRK.A", "Berkshire Hathaway Inc. Common Stock"),
        ]
    )
    nasdaq_response = MagicMock(text=_HEADER)
    other_response = MagicMock(text=other_text)

    loader = _make_loader()
    with patch(
        "loaders.load_market_constituents.requests.get",
        side_effect=[nasdaq_response, other_response],
    ), patch("loaders.load_market_constituents.validate_url", return_value=(True, "")):
        rows = loader._fetch_nasdaq_symbols()

    symbols = {r["symbol"] for r in rows}
    assert "PBR.A" not in symbols
    assert "BRK.A" in symbols


def test_known_etf_misclassification_override_survives_upstream_flag() -> None:
    """JHDV/JVAL are flagged ETF='N' by NASDAQ's own otherlisted.txt feed (confirmed live,
    see migration 069) - without the KNOWN_ETF_MISCLASSIFICATIONS override, they'd land in
    stock_symbols as ordinary stocks and get silently dropped from etf_symbols on every
    TRUNCATE+rebuild in _upsert_etf_symbols, undoing migration 069's one-time DB patch
    again on the very next loader run.
    """
    other_text = "\n".join(
        [
            _HEADER,
            _row("JHDV", "Janus Henderson U.S. Dividend Factor ETF"),
            _row("JVAL", "Janus Henderson U.S. Deep Value ETF"),
            _row("REAL", "Some Real Company Common Stock"),
        ]
    )
    nasdaq_response = MagicMock(text=_HEADER)
    other_response = MagicMock(text=other_text)

    loader = _make_loader()
    with patch(
        "loaders.load_market_constituents.requests.get",
        side_effect=[nasdaq_response, other_response],
    ), patch("loaders.load_market_constituents.validate_url", return_value=(True, "")), patch.object(
        MarketConstituentsLoader, "_upsert_etf_symbols"
    ) as mock_upsert:
        rows = loader._fetch_nasdaq_symbols()

    stock_symbols = {r["symbol"] for r in rows}
    assert "JHDV" not in stock_symbols
    assert "JVAL" not in stock_symbols
    assert "REAL" in stock_symbols

    assert mock_upsert.call_count == 1
    etf_symbols = {r["symbol"] for r in mock_upsert.call_args[0][0]}
    assert etf_symbols == {"JHDV", "JVAL"}


def test_test_issue_flag_still_excludes_dot_suffix_test_symbols() -> None:
    nasdaq_text = "\n".join(
        [
            _NASDAQ_HEADER,
            _nasdaq_row("ZXYZ.A", "Nasdaq Symbology Test Common Stock", test_issue="Y"),
            _nasdaq_row("REAL", "Some Real Company Common Stock"),
        ]
    )
    other_response = MagicMock(text=_HEADER)
    nasdaq_response = MagicMock(text=nasdaq_text)

    loader = _make_loader()
    with patch(
        "loaders.load_market_constituents.requests.get",
        side_effect=[nasdaq_response, other_response],
    ), patch("loaders.load_market_constituents.validate_url", return_value=(True, "")):
        rows = loader._fetch_nasdaq_symbols()

    symbols = {r["symbol"] for r in rows}
    assert "ZXYZ.A" not in symbols
    assert "REAL" in symbols

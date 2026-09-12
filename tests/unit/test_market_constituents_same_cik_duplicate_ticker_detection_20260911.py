"""Regression: _detect_same_cik_duplicate_active_symbols must flag an unreconciled ticker
rename (old and new tickers both active=true, same CIK) while NOT flagging a legitimate
multi-class share structure (GOOG/GOOGL-shaped) that happens to share a CIK too.

Bug this guards against (live-confirmed 2026-09-11): Galmed Pharmaceuticals (GLMD) renamed to
Eocene Ltd. (EOCN) - both tickers active=true, same CIK, but GLMD carries all the real
history while EOCN was a same-day-inserted empty row inflating the "Missing SEC/XBRL data"
coverage count. Detection-only (never mutates stock_symbols) - see the method's own docstring
in loaders/load_market_constituents.py for why a real fix (cross-table data migration) isn't
attempted automatically here.
"""

from unittest.mock import MagicMock, patch

from loaders.load_market_constituents import MarketConstituentsLoader


def _make_loader():
    return MarketConstituentsLoader.__new__(MarketConstituentsLoader)


class TestSameCikDuplicateActiveSymbolDetection:
    def test_flags_unreconciled_rename_pair(self):
        loader = _make_loader()
        mock_client = MagicMock()
        mock_client.get_full_ticker_cik_mapping.return_value = {
            "GLMD": "0001595353",
            "EOCN": "0001595353",
            "AAPL": "0000320193",
        }
        # submissions.json still only lists the pre-rename ticker, same as the real live
        # GLMD/EOCN case two days after the announcement.
        mock_client.get_submissions.return_value = {"tickers": ["GLMD"]}

        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=mock_client),
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("GLMD",), ("EOCN",), ("AAPL",)]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._detect_same_cik_duplicate_active_symbols()

        assert mock_notify.called
        details = mock_notify.call_args.kwargs["details"]
        assert details["duplicates"] == {"0001595353": ["EOCN", "GLMD"]}

    def test_does_not_flag_legitimate_multi_class_structure(self):
        """GOOG/GOOGL-shaped: both tickers share a CIK AND both are persistently listed in
        the company's own submissions.json tickers field - must not be treated as a rename."""
        loader = _make_loader()
        mock_client = MagicMock()
        mock_client.get_full_ticker_cik_mapping.return_value = {
            "GOOG": "0001652044",
            "GOOGL": "0001652044",
            "AAPL": "0000320193",
        }
        mock_client.get_submissions.return_value = {"tickers": ["GOOGL", "GOOG", "GOOGM", "GOOGN"]}

        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=mock_client),
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("GOOG",), ("GOOGL",), ("AAPL",)]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._detect_same_cik_duplicate_active_symbols()

        assert not mock_notify.called

    def test_no_active_symbols_share_a_cik_is_a_silent_noop(self):
        loader = _make_loader()
        mock_client = MagicMock()
        mock_client.get_full_ticker_cik_mapping.return_value = {
            "AAPL": "0000320193",
            "MSFT": "0000789019",
        }

        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=mock_client),
            patch("algo.reporting.notify") as mock_notify,
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("AAPL",), ("MSFT",)]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._detect_same_cik_duplicate_active_symbols()

        assert not mock_notify.called
        mock_client.get_submissions.assert_not_called()

    def test_never_raises_on_sec_client_failure(self):
        """A network/refresh failure here must never break the real stock_symbols load this
        runs alongside - detection is best-effort, not on the critical path."""
        loader = _make_loader()

        with (
            patch("loaders.load_market_constituents.DatabaseContext") as mock_db_ctx,
            patch(
                "utils.external.sec_edgar_client.SecEdgarClient",
                side_effect=RuntimeError("SEC ticker cache unavailable"),
            ),
        ):
            mock_read_cur = MagicMock()
            mock_read_cur.fetchall.return_value = [("AAPL",)]
            mock_db_ctx.return_value.__enter__.return_value = mock_read_cur

            loader._detect_same_cik_duplicate_active_symbols()  # must not raise

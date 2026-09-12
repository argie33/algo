"""Regression test: a successful dividend extraction must retract any stale marker row.

Migration 1214 (2026-08-20) cleaned up a one-time backlog of data_unavailable marker rows
(fetch_error:*, cik_not_found) coexisting with real dividend_per_share history for the same
symbol, and 2026-08-21 fixes made the two failure branches in fetch_incremental() retract
such a marker once real history is confirmed. But the ordinary successful-extraction path
(fetch_incremental's `if unique_results: return unique_results`, and the custom-extension
fallback) never called `_retract_stale_marker()` - so a symbol with an old marker from before
those fixes, which later succeeds normally, kept its stale marker forever. Live-confirmed
2026-09-12: 13 such symbols still coexisting post-1214, cleaned up by migration 1286.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_dividend_data import DividendDataLoader


class TestSuccessPathRetractsStaleMarker:
    def test_unique_results_success_path_retracts_stale_marker(self):
        loader = DividendDataLoader.__new__(DividendDataLoader)
        real_record = {
            "symbol": "ADNT",
            "declaration_date": None,
            "ex_dividend_date": date(2026, 8, 1),
            "record_date": None,
            "payment_date": None,
            "dividend_per_share": 0.25,
            "dividend_yield_pct": None,
            "total_dividend_amount": None,
            "dividend_type": "regular",
            "currency": "USD",
            "data_unavailable": False,
            "data_unavailable_reason": None,
            "source": "SEC_XBRL",
        }

        with (
            patch.object(
                loader,
                "_fetch_sec_data_with_timeout",
                return_value={"facts_response": {"facts": {"us-gaap": {"SomeConcept": {"units": {}}}}}},
            ),
            patch.object(
                loader,
                "_extract_dividends_from_xbrl_concept",
                side_effect=lambda symbol, facts, concept: (
                    [real_record] if concept == "CommonStockDividendsPerShareDeclared" else []
                ),
            ),
            patch.object(loader, "_extract_total_dividends_from_xbrl_concept", return_value=[]),
            patch.object(loader, "_retract_stale_marker") as mock_retract,
        ):
            result = loader.fetch_incremental("ADNT", since=None)

        assert result == [real_record]
        mock_retract.assert_called_once_with("ADNT")

    def test_custom_extension_success_path_retracts_stale_marker(self):
        loader = DividendDataLoader.__new__(DividendDataLoader)
        real_record = {
            "symbol": "PAYP",
            "declaration_date": None,
            "ex_dividend_date": date(2026, 8, 1),
            "record_date": None,
            "payment_date": None,
            "dividend_per_share": 0.10,
            "dividend_yield_pct": None,
            "total_dividend_amount": None,
            "dividend_type": "regular",
            "currency": "USD",
            "data_unavailable": False,
            "data_unavailable_reason": None,
            "source": "SEC_XBRL_CUSTOM_EXTENSION",
        }

        with (
            patch.object(
                loader,
                "_fetch_sec_data_with_timeout",
                return_value={"facts_response": {"facts": {}}},
            ),
            patch.object(loader, "_extract_custom_extension_dividends", return_value=[real_record]),
            patch.object(loader, "_retract_stale_marker") as mock_retract,
        ):
            result = loader.fetch_incremental("PAYP", since=None)

        assert result == [real_record]
        mock_retract.assert_called_once_with("PAYP")

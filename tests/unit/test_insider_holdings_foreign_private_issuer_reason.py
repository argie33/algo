"""Regression test (2026-08-19, "no SEC data" audit - sibling fix to
load_insider_transaction_velocity.py): insider_holdings_sec labeled foreign private
issuers (20-F/40-F filers, exempt from SEC Section 16 insider reporting under Exchange Act
Rule 3a12-3) with the same "no_form345_filings_in_lookback_window" reason as a domestic
filer with a genuine gap in the SEC bulk Form 3/4/5 data set. Both read identically from
Form345BulkAggregator's perspective (get_symbol_summary returns None), so they must be
distinguished via a live SEC submissions form-type check, not conflated as one generic
"missing data" reason.
"""

from datetime import datetime
from types import SimpleNamespace

from loaders.load_insider_holdings_sec import InsiderHoldingsSECLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _make_loader(aggregator_summary, is_fpi):
    loader = InsiderHoldingsSECLoader.__new__(InsiderHoldingsSECLoader)
    loader._aggregator = SimpleNamespace(get_symbol_summary=lambda symbol: aggregator_summary)
    loader.sec_client = None
    loader._is_foreign_private_issuer = lambda symbol: is_fpi
    return loader


class TestForeignPrivateIssuerReason:
    def test_foreign_filer_with_no_summary_gets_exempt_reason(self):
        loader = _make_loader(aggregator_summary=None, is_fpi=True)
        result = loader.fetch_incremental("ASML", since=None)
        assert result[0]["reason"] == "foreign_private_issuer_exempt"
        assert result[0]["data_unavailable"] is True

    def test_domestic_filer_with_no_summary_keeps_generic_reason(self):
        loader = _make_loader(aggregator_summary=None, is_fpi=False)
        result = loader.fetch_incremental("ZZZZ", since=None)
        assert result[0]["reason"] == "no_form345_filings_in_lookback_window"

    def test_real_summary_never_calls_fpi_check(self):
        summary = SimpleNamespace(
            total_shares=1000,
            number_of_insiders=5,
            recent_buys=2,
            recent_sells=1,
            latest_filing_date=datetime.now(EASTERN_TZ).date(),
            sec_filing_url="https://example.com",
        )
        loader = InsiderHoldingsSECLoader.__new__(InsiderHoldingsSECLoader)
        loader._aggregator = SimpleNamespace(get_symbol_summary=lambda symbol: summary)
        loader._get_shares_outstanding = staticmethod(lambda symbol: 10000)
        called = []
        loader._is_foreign_private_issuer = lambda symbol: called.append(symbol) or True
        result = loader.fetch_incremental("AAPL", since=None)
        assert called == []
        assert result[0]["data_unavailable"] is False


class TestIsForeignPrivateIssuer:
    def test_symbol_with_20f_filing_is_classified_as_fpi(self):
        loader = InsiderHoldingsSECLoader.__new__(InsiderHoldingsSECLoader)
        loader.sec_client = SimpleNamespace(
            symbol_to_cik=lambda symbol: "1",
            get_submissions=lambda cik: {"filings": {"recent": {"form": ["6-K", "20-F"]}}},
        )
        assert loader._is_foreign_private_issuer("ASML") is True

    def test_domestic_10k_filer_is_not_classified_as_fpi(self):
        loader = InsiderHoldingsSECLoader.__new__(InsiderHoldingsSECLoader)
        loader.sec_client = SimpleNamespace(
            symbol_to_cik=lambda symbol: "1",
            get_submissions=lambda cik: {"filings": {"recent": {"form": ["10-K", "4"]}}},
        )
        assert loader._is_foreign_private_issuer("AAPL") is False

    def test_lookup_failure_fails_open_returns_false(self):
        loader = InsiderHoldingsSECLoader.__new__(InsiderHoldingsSECLoader)

        def _raise(symbol):
            raise ValueError("Symbol not found in SEC ticker cache")

        loader.sec_client = SimpleNamespace(symbol_to_cik=_raise, get_submissions=lambda cik: {})
        assert loader._is_foreign_private_issuer("ZZZZ") is False

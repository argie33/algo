"""Regression test (2026-08-19, "no SEC data" audit): insider_transaction_velocity labeled
foreign private issuers (20-F/40-F filers, exempt from SEC Section 16 insider reporting
under Exchange Act Rule 3a12-3) with the same "no_insider_transactions_in_lookback" reason
as a domestic filer with a genuine (if unusual) multi-year gap in real Form 3/4/5 activity.
Live-confirmed: AMX, ASML, SHEL, BCS, VOD, SAP, NVS - among the largest symbols in this
bucket - are all confirmed 20-F filers. Both cases read identically from
Form345TransactionVelocityAggregator's perspective (an empty transaction list), so they must
be distinguished via a live SEC submissions form-type check, not conflated as one generic
"missing data" reason.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from loaders.load_insider_transaction_velocity import InsiderTransactionVelocityLoader


def _metrics(data_unavailable=True, reason="no_insider_transactions_in_lookback"):
    return SimpleNamespace(
        data_unavailable=data_unavailable,
        reason=reason,
        buy_transactions_30d=0,
        sell_transactions_30d=0,
        buy_transactions_90d=0,
        sell_transactions_90d=0,
        total_buy_shares_30d=0,
        total_sell_shares_30d=0,
        total_buy_shares_90d=0,
        total_sell_shares_90d=0,
    )


def _make_loader(monkeypatch, metrics, is_fpi):
    loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)
    loader._aggregator = SimpleNamespace(get_velocity_metrics=lambda *a, **kw: metrics)
    loader.sec_client = None
    monkeypatch.setattr(loader, "_is_foreign_private_issuer", lambda symbol: is_fpi)
    return loader


class TestForeignPrivateIssuerReason:
    def test_foreign_filer_with_zero_transactions_gets_exempt_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, _metrics(), is_fpi=True)
        result = loader.fetch_incremental("ASML", since=date(2026, 8, 19))
        assert result[0]["data_unavailable_reason"] == "foreign_private_issuer_exempt"

    def test_domestic_filer_with_zero_transactions_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, _metrics(), is_fpi=False)
        result = loader.fetch_incremental("ZZZZ", since=date(2026, 8, 19))
        assert result[0]["data_unavailable_reason"] == "no_insider_transactions_in_lookback"

    def test_other_unavailable_reasons_are_not_relabeled(self, monkeypatch):
        # The FPI check must only fire for the specific "no_insider_transactions_in_lookback"
        # reason - a different failure reason (e.g. a bulk-data parse error) must never be
        # silently reclassified as "foreign private issuer".
        loader = _make_loader(monkeypatch, _metrics(reason="some_other_reason"), is_fpi=True)
        result = loader.fetch_incremental("X", since=date(2026, 8, 19))
        assert result[0]["data_unavailable_reason"] == "some_other_reason"

    def test_real_data_available_never_calls_fpi_check(self, monkeypatch):
        loader = _make_loader(monkeypatch, _metrics(data_unavailable=False), is_fpi=True)
        with patch.object(loader, "_is_foreign_private_issuer") as fpi_check:
            result = loader.fetch_incremental("AAPL", since=date(2026, 8, 19))
        fpi_check.assert_not_called()
        assert result[0]["data_unavailable"] is False


class TestIsForeignPrivateIssuer:
    def test_symbol_with_20f_filing_is_classified_as_fpi(self):
        loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)
        loader.sec_client = SimpleNamespace(
            symbol_to_cik=lambda symbol: "1",
            get_submissions=lambda cik: {"filings": {"recent": {"form": ["6-K", "20-F", "6-K"]}}},
        )
        assert loader._is_foreign_private_issuer("ASML") is True

    def test_domestic_10k_filer_is_not_classified_as_fpi(self):
        loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)
        loader.sec_client = SimpleNamespace(
            symbol_to_cik=lambda symbol: "1",
            get_submissions=lambda cik: {"filings": {"recent": {"form": ["10-K", "4", "8-K"]}}},
        )
        assert loader._is_foreign_private_issuer("AAPL") is False

    def test_old_one_off_form_3_does_not_veto_fpi_classification(self):
        # Live-confirmed via AMX/BCS/VOD: a confirmed 20-F filer can still carry a handful
        # of old/one-off Form 3/4 entries in its filing history (e.g. a since-departed
        # officer's initial filing years ago) - the classification must be based on the
        # presence of a 20-F/40-F alone, not also require a total absence of Form 3/4/5.
        loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)
        loader.sec_client = SimpleNamespace(
            symbol_to_cik=lambda symbol: "1",
            get_submissions=lambda cik: {"filings": {"recent": {"form": ["20-F", "3", "6-K"]}}},
        )
        assert loader._is_foreign_private_issuer("AMX") is True

    def test_lookup_failure_fails_open_returns_false(self):
        loader = InsiderTransactionVelocityLoader.__new__(InsiderTransactionVelocityLoader)

        def _raise(symbol):
            raise ValueError("Symbol not found in SEC ticker cache")

        loader.sec_client = SimpleNamespace(symbol_to_cik=_raise, get_submissions=lambda cik: {})
        assert loader._is_foreign_private_issuer("ZZZZ") is False

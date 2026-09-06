"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, sibling to
test_unsupported_currency_ocf_recategorize_20260906.py's cash-flow-side fix): a foreign
private issuer that tags Assets/Equity only under a hyperinflationary/unsupported local
currency (e.g. ARS - GGAL/BBAR/BSAC/SUPV/TEO/TKC/TGS/TV, live-confirmed via real SEC
companyfacts) has a real, non-fabricatable stockholders_equity=None, so the row-level "all
core ratios missing" early return must recognize it via
_get_unsupported_currency_balance_sheet_symbols() and stamp "unsupported_currency_no_fx_rate"
instead of falling through to the generic "no_recent_balance_sheet_data_reported" bucket -
same class of fix as the ETF-trust row-level reason
(test_etf_trust_no_gaap_financials_row_level_reason_20260905.py), checked at the same
priority.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _empty_quality_row(fiscal_year=2024):
    row = [None] * 34
    row[8] = fiscal_year
    return row


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, unsupported_currency_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(
        loader,
        "_get_unsupported_currency_balance_sheet_symbols",
        lambda: unsupported_currency_symbols,
        raising=False,
    )
    return loader


class TestUnsupportedCurrencyBalanceSheetRowLevelReason:
    def test_fpi_shaped_symbol_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"GGAL"}))

        metrics = loader._compute_quality_metrics("GGAL", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "unsupported_currency_no_fx_rate"
        assert metrics["roe_unavailable_reason"] == "unsupported_currency_no_fx_rate"
        assert metrics["debt_to_equity_unavailable_reason"] == "unsupported_currency_no_fx_rate"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"GGAL"}))

        metrics = loader._compute_quality_metrics("NORMALCO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] != "unsupported_currency_no_fx_rate"

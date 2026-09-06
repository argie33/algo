"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to the quality_metrics blank-check broad-loop fix): fcf_yield's reason chain already
checks royalty-trust/RIC/ETF-trust status (the "no real cash-flow-statement concepts" family)
but never checked blank-check (SIC 6770, pre-merger SPAC) status - a SPAC has no real operating
business (trust-account interest income only), so it has no capex/FCF concept to tag either,
same structural fact. Live-confirmed via a company_info_sec join: 16 active blank-check symbols
stuck on "capex_never_tagged_in_recent_filings" and 8 more on "missing_sec_data" for fcf_yield
alone (symbols with SOME other real value computed - e.g. pe_ratio from trust interest income -
so they never reached the whole-row all_valuation_metrics_null fallback fixed earlier this
session).
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RecordingCursor:
    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def _run(monkeypatch, symbol, blank_check_symbols=frozenset(), no_recent_capex_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor()

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols, raising=False)
    monkeypatch.setattr(loader, "_get_unsupported_currency_ocf_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_no_recent_free_cash_flow_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_never_tagged_free_cash_flow_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_no_recent_capex_symbols", lambda: no_recent_capex_symbols, raising=False)
    monkeypatch.setattr(loader, "_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS", frozenset(), raising=False)
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


_BASE_ROW = {
    "pe_ratio": 15.0,
    "pb_ratio": 2.0,
    "ps_ratio": 3.0,
    "ev_revenue": None,
    "ev_ebitda": None,
    "ebitda": None,
    "enterprise_value": None,
    "market_cap": 20_000_000.0,
    "total_debt": None,
    "total_cash": None,
    "fcf_yield": None,
}


class TestFcfYieldBlankCheckRecategorize:
    def test_blank_check_symbol_reports_no_revenue_reported(self, monkeypatch):
        result = _run(
            monkeypatch,
            "SPACX",
            blank_check_symbols=frozenset({"SPACX"}),
            no_recent_capex_symbols=frozenset({"SPACX"}),
            **_BASE_ROW,
        )

        assert result["fcf_yield_unavailable_reason"] == "no_revenue_reported"

    def test_non_blank_check_keeps_capex_never_tagged_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "NORMALCO",
            blank_check_symbols=frozenset({"SPACX"}),
            no_recent_capex_symbols=frozenset({"NORMALCO"}),
            **_BASE_ROW,
        )

        assert result["fcf_yield_unavailable_reason"] == "capex_never_tagged_in_recent_filings"

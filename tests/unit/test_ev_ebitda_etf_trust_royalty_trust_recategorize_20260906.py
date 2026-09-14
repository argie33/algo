"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to test_ev_ebitda_ric_recategorize_20260906.py): ev_ebitda's reason chain only ever
checked registered-investment-company (RIC) status, never the sibling physical commodity/
currency/crypto trust (etf_trust) or royalty-trust checks fcf_yield_reason_str/quality_metrics.
ebitda already have - a trust with no operating business has no EBITDA concept to tag either,
same structural fact. The RIC/etf-trust/royalty-trust check was also placed AFTER the
ebitda_raw is None/<=0 checks, so a structural symbol whose ebitda_raw happened to be None (the
common case - these trusts rarely tag any EBITDA-shaped concept) was silently outranked by the
generic "ebitda_not_extracted" instead of ever reaching the structural check at all.

Live-confirmed 37 active etf_symbols tickers (GLDM/BITW/CPER/USCI-class) stuck on
"missing_sec_data"/"ebitda_not_extracted" for ev_ebitda instead of "etf_trust_no_gaap_
financials".
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


def _run(monkeypatch, symbol, ebitda=None, etf_trust_symbols=frozenset(), royalty_trust_symbols=frozenset()):
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
    monkeypatch.setattr(
        loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: etf_trust_symbols, raising=False
    )
    monkeypatch.setattr(loader, "_get_no_recent_debt_components_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS", royalty_trust_symbols, raising=False)
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(
            symbol,
            _FakeSecValRow(
                {
                    "pe_ratio": 15.0,
                    "pb_ratio": 2.0,
                    "ps_ratio": 3.0,
                    "ev_revenue": None,
                    "ev_ebitda": None,
                    "ebitda": ebitda,
                    "enterprise_value": None,
                    "market_cap": 20_000_000.0,
                    "total_debt": None,
                    "total_cash": None,
                    "fcf_yield": 6.0,
                }
            ),
        )


class TestEvEbitdaEtfTrustRoyaltyTrustRecategorize:
    def test_etf_trust_symbol_with_no_ebitda_reports_etf_trust_reason(self, monkeypatch):
        # ebitda_raw is None (the common case for these trusts) - this is the priority-order
        # part of the fix: the structural check must still win over "ebitda_not_extracted".
        result = _run(monkeypatch, "GLDM", ebitda=None, etf_trust_symbols=frozenset({"GLDM"}))

        assert result["ev_ebitda_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_etf_trust_symbol_with_real_ebitda_still_reports_etf_trust_reason(self, monkeypatch):
        result = _run(monkeypatch, "GLDM", ebitda=5_000_000.0, etf_trust_symbols=frozenset({"GLDM"}))

        assert result["ev_ebitda_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_royalty_trust_symbol_reports_reit_special_entity_reason(self, monkeypatch):
        result = _run(monkeypatch, "SJT", ebitda=None, royalty_trust_symbols=frozenset({"SJT"}))

        assert result["ev_ebitda_unavailable_reason"] == "reit_special_entity"

    def test_non_structural_symbol_with_no_ebitda_keeps_generic_reason(self, monkeypatch):
        result = _run(monkeypatch, "NORMALCO", ebitda=None)

        assert result["ev_ebitda_unavailable_reason"] == "ebitda_not_extracted"

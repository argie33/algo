"""Regression test (2026-09-07, goal: "SEC/XBRL missing data to zero" sweep): current_ratio/
quick_ratio's reason chains never checked the ETF-trust/RIC gates every other metric's chain
in this file already has (fcf_margin, free_cash_flow, operating_cash_flow, etc.) - physical
commodity/currency/crypto trusts (BTC/ETH/XRP/GSOL/BSOL-class) file a "Statement of Assets
and Liabilities" with no current/non-current split at all, same structural fact
_get_etf_trust_no_stockholders_equity_symbols() already exists for. Live-confirmed:
BTC/ETH/XRP/GSOL/BSOL and 9 more universe symbols have real annual_balance_sheet history but
zero current_assets ever, landing on the generic "no_recent_current_assets_reported"
("Missing SEC/XBRL data") instead of the correct "etf_trust_no_gaap_financials"
("Legitimate / not applicable").
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(current_assets=None):
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = None  # revenue
    row[6] = current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    """All windowed/never-tagged gates return empty - only the 2 gates under test (patched
    separately via patch.object) return anything, same isolation approach as the sibling
    test_current_ratio_quick_ratio_never_tagged_gates_added_20260903.py."""

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


def _make_loader(monkeypatch) -> ValueQualityGrowthMetricsLoader:
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestCurrentRatioQuickRatioEtfTrustRicGates:
    def test_etf_trust_symbol_reports_etf_trust_no_gaap_financials(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=None)
        with patch.object(
            type(loader), "_get_etf_trust_no_stockholders_equity_symbols", return_value=frozenset({"BTC"})
        ):
            metrics = loader._compute_quality_metrics("BTC", row, ev_metrics=None)

        assert metrics["current_ratio"] is None
        assert metrics["current_ratio_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert metrics["quick_ratio_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_registered_investment_company_symbol_reports_ric_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=None)
        with patch.object(
            type(loader), "_get_registered_investment_company_symbols", return_value=frozenset({"CEFCO"})
        ):
            metrics = loader._compute_quality_metrics("CEFCO", row, ev_metrics=None)

        assert metrics["current_ratio_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_symbol_outside_both_gates_keeps_generic_reason(self, monkeypatch):
        """Identical missing current_assets, but the symbol is in neither the ETF-trust nor
        RIC gate - must fall through to the pre-existing never-tagged gate/generic reason,
        not be swept up by this fix."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["current_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["quick_ratio_unavailable_reason"] == "missing_sec_data"

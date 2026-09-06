"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): total_debt's own
ternary chain never had a registered-investment-company (RIC) or ETF-trust check, unlike its
downstream dependents roic_pct/roce_pct/debt_to_equity (all built from the same total_debt_ev
value, fixed 2026-09-05 in test_roic_pct_debt_to_equity_ric_recategorize_20260905.py) and its
fcf_margin/fcf_to_net_income/ocf_to_net_income/accruals_ratio siblings.

A RIC (closed-end fund/investment trust) files a "Statement of Changes in Net Assets" with no
debt-component concepts to tag at all - live-confirmed 82 active-universe RIC symbols (GGN, BLW,
BGY, and siblings) report total_debt_unavailable_reason='total_debt_not_itemized' ("Missing
SEC/XBRL data" in /api/scores/coverage) for the exact same structural absence already correctly
bucketed "Legitimate / not applicable" for roic_pct/roce_pct/debt_to_equity on the same rows.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_roic_pct_debt_to_equity_ric_recategorize_20260905.py's fixture.
    base = [
        5_000_000_000.0,  # 0 stockholders_equity - real, GGN-shaped
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt - structurally absent, a RIC has no debt concept
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    ]
    return tuple(base)


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, ric_symbols=frozenset(), etf_trust_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: ric_symbols, raising=False)
    monkeypatch.setattr(
        loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: etf_trust_symbols, raising=False
    )
    return loader


class TestTotalDebtRicRecategorize:
    def test_ggn_shaped_ric_reports_registered_investment_company_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_etf_trust_reports_etf_trust_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, etf_trust_symbols=frozenset({"GLDM"}))
        metrics = loader._compute_quality_metrics("GLDM", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_non_ric_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["total_debt_unavailable_reason"] not in (
            "registered_investment_company_no_xbrl",
            "etf_trust_no_gaap_financials",
        )

    def test_ric_recategorize_does_not_clobber_real_total_debt(self, monkeypatch):
        # total_debt is sourced straight from ev_metrics[0] (sec_valuations' own total_debt),
        # not from long_term_debt_bs - a real ev_metrics total_debt must be left untouched even
        # for a RIC-flagged symbol.
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(1_000_000_000.0, None, None, None))

        assert metrics.get("total_debt") is not None
        assert metrics.get("total_debt_unavailable_reason") is None

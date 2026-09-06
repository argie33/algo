"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to test_total_debt_ric_recategorize_20260906.py): interest_coverage's own ternary
chain can produce "interest_expense_not_itemized" for a registered investment company (RIC) -
a closed-end fund/investment trust files a "Statement of Changes in Net Assets" with no
interest-expense concept to tag at all, same structural absence already correctly bucketed
"Legitimate / not applicable" for total_debt/roic_pct/roce_pct/debt_to_equity on the same rows.

Root cause: "interest_expense_not_itemized" was already listed in the RIC recategorization
loop's own `_ric_source_reasons` set as a reason this loop should catch, but "interest_coverage"
itself was never added to the `_ric_recategorize_fields` tuple the loop iterates over, so the
catch never fired - a half-wired fix, not a deliberate omission (the sibling royalty-trust
block already includes "interest_coverage" in its own recategorize-fields tuple).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_total_debt_ric_recategorize_20260906.py's fixture - a
    # GGN-shaped RIC with no interest_expense concept tagged at all (index 10, None).
    base = [
        5_000_000_000.0,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense - structurally absent, a RIC has no interest-expense concept
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
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


def _make_loader(monkeypatch, ric_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: ric_symbols, raising=False)
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset(), raising=False)
    return loader


class TestInterestCoverageRicRecategorize:
    def test_ggn_shaped_ric_reports_registered_investment_company_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["interest_coverage_unavailable_reason"] != "registered_investment_company_no_xbrl"

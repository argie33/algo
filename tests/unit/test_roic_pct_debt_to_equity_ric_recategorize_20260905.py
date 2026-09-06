"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up):
roic_pct/debt_to_equity (and their _etf_trust_recategorize_fields siblings) never had a
registered-investment-company (RIC) recategorization pass, unlike the ETF-trust block right
above it in this file (which only covers physical commodity/currency trusts like GLD/GBTC, a
different gate: _get_etf_trust_no_stockholders_equity_symbols()).

A RIC (closed-end fund/investment trust) files a "Statement of Changes in Net Assets" with no
stockholders_equity/total_debt concepts to tag at all - same root fact already established for
fcf_margin/fcf_yield/accruals_ratio/ocf_to_net_income elsewhere in this file.

Live-confirmed GGN (GAMCO Global Gold, Natural Resources & Income Trust): roe computes a real
value (its only denominator, stockholders_equity, IS available), but roic_pct/debt_to_equity
(which also need debt_for_roic, structurally absent for a RIC) fell all the way through their
own ternary chains to generic "missing_sec_data" - broader than the ETF-trust block's single
"stockholders_equity_not_reported" check, since a RIC can hit any of several different
missing-denominator reasons depending on which concept it happens to lack first.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_royalty_trust_no_balance_sheet_reason_20260904.py's fixture.
    base = [
        5_000_000_000.0,  # 0 stockholders_equity - real, GGN-shaped (roe computes fine)
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


def _make_loader(monkeypatch, ric_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: ric_symbols, raising=False)
    return loader


class TestRoicPctDebtToEquityRicRecategorize:
    def test_ggn_shaped_ric_reports_registered_investment_company_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        # roe's only denominator (stockholders_equity) is real, so it computes normally.
        assert metrics.get("roe") is not None
        assert metrics.get("roe_unavailable_reason") is None
        # roic_pct/debt_to_equity need debt_for_roic too, structurally absent for a RIC.
        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "registered_investment_company_no_xbrl"
        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["roic_pct_unavailable_reason"] != "registered_investment_company_no_xbrl"
        assert metrics["debt_to_equity_unavailable_reason"] != "registered_investment_company_no_xbrl"

    def test_ric_recategorize_only_fires_when_field_is_none(self, monkeypatch):
        # The recategorize loop's own guard (`metrics.get(_field) is None`) must never clobber
        # a real value - same protection the pre-existing ETF-trust block relies on. debt_to_
        # equity has a real value here (from real stockholders_equity + total_liabilities), so
        # it must be left completely untouched even for a RIC-flagged symbol.
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        row = list(_quality_row())
        row[20] = 1_000_000_000.0  # long_term_debt - real, makes debt_for_roic resolvable
        metrics = loader._compute_quality_metrics("GGN", tuple(row), ev_metrics=(None, None, None, None))

        assert metrics.get("debt_to_equity") is not None
        assert metrics.get("debt_to_equity_unavailable_reason") is None

"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to test_etf_trust_stockholders_equity_reason_wired_to_all_fields_20260905.py): that
fix only wired the ETF-trust gate (`_get_etf_trust_no_stockholders_equity_symbols`) into a
NARROW loop keyed on the single "stockholders_equity_not_reported" reason (roe/debt_to_equity/
roic_pct/roce_pct/operating_profitability/sustainable_growth_rate) - but a physical/commodity/
currency/crypto trust (GLD/GLDM/GBTC/ETHE/BITB/the FX*-class currency trusts/the commodity-pool
ETFs) files ONLY total_assets/total_liabilities (a "Statement of Assets and Liabilities" - see
`_get_etf_trust_no_stockholders_equity_symbols`'s own docstring), so every other field
(payout_ratio/gross_profitability/asset_turnover/roa/operating_margin/net_margin/current_ratio/
quick_ratio/interest_coverage/debt_to_assets/gross_margin/ebitda_margin/accruals_ratio/
total_cash/cash_per_share/ebitda) structurally has no revenue/net_income/operating_income/debt/
cash/interest-expense concept to tag either - the exact same "Statement of Assets and
Liabilities" shape the RIC/royalty-trust broad recategorization loops already handle with a
7-reason set, just never extended to this population.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_etf_trust_stockholders_equity_reason_wired_to_all_fields_
    # 20260905.py's fixture.
    base = [
        None,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        None,  # 3 net_income
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


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEtfTrustBroadFieldWiring:
    def test_etf_trust_symbol_gets_recategorized_across_all_newly_wired_fields(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with (
            patch.object(loader, "_get_etf_trust_no_stockholders_equity_symbols", return_value=frozenset({"GLDM"})),
            patch.object(loader, "_get_never_tagged_stockholders_equity_symbols", return_value=frozenset({"GLDM"})),
        ):
            metrics = loader._compute_quality_metrics("GLDM", _quality_row(), ev_metrics=(None, None, None, None))

        for field in (
            "payout_ratio",
            "gross_profitability",
            "asset_turnover",
            "roa",
            "operating_margin",
            "net_margin",
            "current_ratio",
            "quick_ratio",
            "interest_coverage",
            "debt_to_assets",
            "gross_margin",
            "ebitda_margin",
            "accruals_ratio",
            "total_cash",
            "cash_per_share",
            "ebitda",
        ):
            assert metrics[field] is None, f"{field} unexpectedly computed a real value"
            assert metrics[f"{field}_unavailable_reason"] == "etf_trust_no_gaap_financials", (
                f"{field}_unavailable_reason was {metrics[f'{field}_unavailable_reason']!r}"
            )

    def test_non_etf_trust_symbol_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = list(_quality_row())
        row[3] = 50_000_000.0  # net_income - avoid the "ALL metrics null" early return
        with patch.object(
            loader, "_get_never_tagged_stockholders_equity_symbols", return_value=frozenset({"NORMALCO"})
        ):
            metrics = loader._compute_quality_metrics("NORMALCO", tuple(row), ev_metrics=(None, None, None, None))

        for field in ("current_ratio", "gross_margin", "ebitda", "total_cash"):
            assert metrics[f"{field}_unavailable_reason"] != "etf_trust_no_gaap_financials"

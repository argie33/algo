"""Regression test (2026-09-05, goal session: "SEC/XBRL missing data to zero" sweep,
follow-up to the same-day etf_trust_no_gaap_financials fix): roe/debt_to_equity/roic_pct/
roce_pct/operating_profitability/sustainable_growth_rate must report "etf_trust_no_gaap_
financials" (not the generic "stockholders_equity_not_reported") for a physical commodity/
currency/crypto trust ticker (GLDM/USO/UNG/FXA/GBTC-class), same as current_ratio/quick_ratio
already do via the earlier fix.

Found live: that earlier fix only wired the ETF-trust gate into _compute_quality_metrics's
single "ALL metrics null" early return - a scoped rerun of the 43 real etf_symbols matching
this gate found 38/43 never hit that early return (some other field, e.g. current_ratio,
legitimately computes without stockholders_equity) and fell through to the normal per-field
`stockholders_equity_not_reported` ternary branches instead, which never checked the ETF-trust
gate at all. Same fix pattern as the existing royalty-trust recategorization block
(test_royalty_trust_no_balance_sheet_reason_20260904.py) - reused here for the ETF-trust case.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as the royalty-trust test's fixture.
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


class TestEtfTrustStockholdersEquityReasonWiredToAllFields:
    def test_etf_trust_symbol_gets_recategorized_across_all_affected_fields(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with (
            patch.object(loader, "_get_etf_trust_no_stockholders_equity_symbols", return_value=frozenset({"GLDM"})),
            patch.object(loader, "_get_never_tagged_stockholders_equity_symbols", return_value=frozenset({"GLDM"})),
        ):
            metrics = loader._compute_quality_metrics("GLDM", _quality_row(), ev_metrics=(None, None, None, None))

        for field in (
            "roe",
            "debt_to_equity",
            "roic_pct",
            "roce_pct",
            "operating_profitability",
            "sustainable_growth_rate",
        ):
            assert metrics[field] is None
            assert metrics[f"{field}_unavailable_reason"] == "etf_trust_no_gaap_financials", field

    def test_non_etf_trust_symbol_keeps_generic_reason(self, monkeypatch):
        # A row with SOME real data (net_income) so this doesn't hit the "ALL metrics null"
        # early return - isolates the per-field ternary branches this fix actually targets.
        loader = _make_loader(monkeypatch)
        row = list(_quality_row())
        row[3] = 50_000_000.0  # net_income
        with patch.object(
            loader, "_get_never_tagged_stockholders_equity_symbols", return_value=frozenset({"NORMALCO"})
        ):
            metrics = loader._compute_quality_metrics("NORMALCO", tuple(row), ev_metrics=(None, None, None, None))

        assert metrics["roe_unavailable_reason"] == "stockholders_equity_not_reported"
        assert metrics["debt_to_equity_unavailable_reason"] == "stockholders_equity_not_reported"

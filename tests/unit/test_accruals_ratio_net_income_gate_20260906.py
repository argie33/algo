"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): accruals_ratio
= (net_income - operating_cash_flow) / total_assets, but its reason chain only ever gated on
the operating_cash_flow and total_assets inputs, never on net_income - the same
never-tagged/anchor-year gate pair fcf_to_net_income/ocf_to_net_income already have for their
own net_income denominator. A symbol with real net_income on file (either never tagged at all,
or just missing for the current anchor year) fell straight through to the generic
"missing_sec_data" (Missing SEC/XBRL data) instead of "net_income_not_reported" or
"net_income_absent_from_anchor_year" (Legitimate / not applicable for the anchor-year case).
"""

from contextlib import ExitStack
from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    # net_income (index 3) is None; operating_cash_flow (13) and total_assets (2) are real so
    # accruals_ratio fails ONLY on the net_income input, not the OCF/total_assets ones already
    # gated. current_assets/current_liabilities set so the row doesn't hit the row-level "ALL
    # metrics null" early return before reaching accruals_ratio's own per-field ternary.
    return (
        500_000_000.0,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        None,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        50_000_000.0,  # 13 operating_cash_flow
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
    )


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


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _base_patches(loader):
    return (
        patch.object(loader, "_get_registered_investment_company_symbols", return_value=frozenset()),
        patch.object(loader, "_get_etf_trust_no_stockholders_equity_symbols", return_value=frozenset()),
        patch.object(loader, "_get_no_recent_operating_cash_flow_symbols", return_value=frozenset()),
        patch.object(loader, "_get_never_tagged_operating_cash_flow_symbols", return_value=frozenset()),
        patch.object(loader, "_get_operating_cash_flow_available_elsewhere_symbols", return_value=frozenset()),
        patch.object(loader, "_get_no_recent_total_assets_symbols", return_value=frozenset()),
        patch.object(loader, "_get_never_tagged_total_assets_symbols", return_value=frozenset()),
    )


class TestAccrualsRatioNetIncomeGate:
    def test_never_tagged_net_income_gets_net_income_not_reported(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with ExitStack() as stack:
            for cm in _base_patches(loader):
                stack.enter_context(cm)
            stack.enter_context(patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()))
            stack.enter_context(
                patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset({"NEVERCO"}))
            )
            metrics = loader._compute_quality_metrics("NEVERCO", _quality_row(), ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "net_income_not_reported"

    def test_net_income_available_elsewhere_gets_anchor_year_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with ExitStack() as stack:
            for cm in _base_patches(loader):
                stack.enter_context(cm)
            stack.enter_context(patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()))
            stack.enter_context(patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()))
            stack.enter_context(
                patch.object(
                    loader, "_get_net_income_available_elsewhere_symbols", return_value=frozenset({"ANCHORCO"})
                )
            )
            metrics = loader._compute_quality_metrics("ANCHORCO", _quality_row(), ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "net_income_absent_from_anchor_year"

    def test_symbol_in_no_gate_keeps_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with ExitStack() as stack:
            for cm in _base_patches(loader):
                stack.enter_context(cm)
            stack.enter_context(patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()))
            stack.enter_context(patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()))
            stack.enter_context(
                patch.object(loader, "_get_net_income_available_elsewhere_symbols", return_value=frozenset())
            )
            metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "missing_sec_data"

"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep):
interest_coverage's reason chain checked interest_expense and operating_income's
never-tagged/no-recent gates, but never the anchor-year sibling
(_get_operating_income_available_elsewhere_symbols()) that operating_profitability/
operating_margin already have for the same operating_income_for_margin-shaped input
(interest_coverage_operating_income is the identical EBIT-fallback-aware value, just
computed separately for this field). A symbol with real operating income on file in an
earlier fiscal year - just not the current anchor year - fell through to the generic
"missing_sec_data" (Missing SEC/XBRL data) instead of the correct
"operating_income_absent_from_anchor_year" (Legitimate / not applicable).
"""

from contextlib import ExitStack
from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    # operating_income (index 5) is None; interest_expense (10) is real and positive so
    # interest_coverage fails ONLY on the operating_income input. current_assets/
    # current_liabilities set so the row doesn't hit the row-level "ALL metrics null" early
    # return before reaching interest_coverage's own per-field ternary.
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
        5_000_000.0,  # 10 interest_expense
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
        patch.object(loader, "_get_no_recent_interest_expense_symbols", return_value=frozenset()),
        patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset()),
        patch.object(loader, "_get_never_tagged_borrowed_debt_symbols", return_value=frozenset()),
        patch.object(loader, "_get_no_tax_concept_symbols", return_value=frozenset()),
        patch.object(loader, "_get_no_recent_operating_income_symbols", return_value=frozenset()),
        patch.object(loader, "_get_never_tagged_operating_income_symbols", return_value=frozenset()),
    )


class TestInterestCoverageOperatingIncomeAnchorYearGate:
    def test_operating_income_available_elsewhere_gets_anchor_year_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with ExitStack() as stack:
            for cm in _base_patches(loader):
                stack.enter_context(cm)
            stack.enter_context(
                patch.object(
                    loader, "_get_operating_income_available_elsewhere_symbols", return_value=frozenset({"ANCHORCO"})
                )
            )
            metrics = loader._compute_quality_metrics("ANCHORCO", _quality_row(), ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "operating_income_absent_from_anchor_year"

    def test_symbol_not_in_anchor_year_gate_keeps_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        with ExitStack() as stack:
            for cm in _base_patches(loader):
                stack.enter_context(cm)
            stack.enter_context(
                patch.object(loader, "_get_operating_income_available_elsewhere_symbols", return_value=frozenset())
            )
            metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "missing_sec_data"

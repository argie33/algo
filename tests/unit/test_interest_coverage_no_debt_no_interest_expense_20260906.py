"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): interest_coverage
(operating_income / interest_expense) is mathematically undefined - not missing - for a symbol
double-confirmed structurally debt-free (never tagged ANY debt component across full
balance-sheet history AND never reports nonzero interest_expense - the same evidentiary bar
this session's total_debt zero-coercion fix uses). Unlike total_debt (a real 0), operating_
income / $0 has no meaningful value, so this gets its own "Legitimate / not applicable" reason
(`no_debt_no_interest_expense`) instead of a coerced number - same "mathematically undefined for
real business reasons, not a data gap" class as `no_revenue_reported`/`unprofitable_stock`.

This is narrower than test_interest_coverage_never_tagged_full_history_reason_20260902.py's
existing "never tagged interest expense alone" population - it only fires when the symbol is
ALSO double-confirmed debt-free, so that test's RECENTIPO case (interest-expense gate only, no
debt gate) is correctly unaffected and keeps the generic "interest_expense_not_itemized" label.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(operating_income=17_000_000.0, interest_expense=None):
    row = [None] * 34
    row[0] = 500_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[5] = operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[10] = interest_expense
    return row


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


class TestInterestCoverageNoDebtNoInterestExpense:
    def test_double_confirmed_debt_free_symbol_gets_legitimate_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(interest_expense=None)
        with (
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"DEBTFREE1"})),
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset({"DEBTFREE1"})),
        ):
            metrics = loader._compute_quality_metrics("DEBTFREE1", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "no_debt_no_interest_expense"

    def test_interest_expense_gate_alone_keeps_generic_reason(self, monkeypatch):
        """Not confirmed debt-free (only the interest-expense gate matched) - stays the
        existing, more conservative label."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(interest_expense=None)
        with (
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"PARTIAL1"})),
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset()),
        ):
            metrics = loader._compute_quality_metrics("PARTIAL1", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "interest_expense_not_itemized"

    def test_lease_only_liability_symbol_also_gets_legitimate_reason(self, monkeypatch):
        """Broader borrowed-debt-only gate (2026-09-06 follow-up): a symbol with real
        operating/finance lease liabilities but zero borrowed debt (AMBA/Ambarella shape) is
        NOT in the strict all-four-components gate (it fails the lease-liability=0 requirement)
        but IS in the narrower borrowed-debt-only gate, and should still get the legitimate
        reason rather than falling through to the generic "interest_expense_not_itemized"."""
        loader = _make_loader(monkeypatch)
        row = _quality_row(interest_expense=None)
        with (
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"LEASEONLY1"})),
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset()),
            patch.object(loader, "_get_never_tagged_borrowed_debt_symbols", return_value=frozenset({"LEASEONLY1"})),
        ):
            metrics = loader._compute_quality_metrics("LEASEONLY1", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "no_debt_no_interest_expense"

    def test_real_interest_expense_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=100_000_000.0, interest_expense=10_000_000.0)
        with (
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"HASDEBT1"})),
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset({"HASDEBT1"})),
        ):
            metrics = loader._compute_quality_metrics("HASDEBT1", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 10.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

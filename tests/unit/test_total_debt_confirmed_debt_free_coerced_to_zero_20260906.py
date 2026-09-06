"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): debt_for_roic
(used internally by debt_to_equity/roic_pct/roce_pct) already coerces to 0.0 for a symbol
double-confirmed structurally debt-free (never tagged ANY debt component across full
balance-sheet history AND never reports nonzero interest_expense - see
_get_never_tagged_debt_components_symbols/_get_never_tagged_interest_expense_symbols) - but the
raw total_debt metric itself never got the same treatment, so it stayed
"total_debt_not_itemized" (counted as "Missing SEC/XBRL data" in /api/scores/coverage) even
when its absence is confirmed, not unknown. A confirmed zero is a real value, not missing data -
same philosophy already applied to capex for banks/insurers/BDCs.

This is narrower than test_total_debt_not_itemized_reason.py's existing "no recent debt
components" (3-year window) population - it only fires for the stricter, double-confirmed
"never tagged, ever" + "never reports interest expense" gates, so that test's SPAC1 case (which
only satisfies the weaker 3-year gate) is correctly unaffected.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    row = [None] * 34
    row[0] = 500_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[5] = 17_000_000.0  # operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
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


class TestTotalDebtConfirmedDebtFreeCoercedToZero:
    def test_double_confirmed_debt_free_symbol_gets_zero_not_missing(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset({"DEBTFREE1"})),
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"DEBTFREE1"})),
        ):
            metrics = loader._compute_quality_metrics("DEBTFREE1", row, ev_metrics=None)

        assert metrics["total_debt"] == 0.0
        assert metrics.get("total_debt_unavailable_reason") is None

    def test_only_debt_gate_without_interest_gate_stays_unavailable(self, monkeypatch):
        """Single-gate confirmation isn't strong enough evidence - matches debt_for_roic's own
        double-confirmation requirement exactly."""
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset({"PARTIAL1"})),
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset()),
        ):
            metrics = loader._compute_quality_metrics("PARTIAL1", row, ev_metrics=None)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "total_debt_not_itemized"

    def test_real_total_debt_still_wins_over_zero_coercion(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_never_tagged_debt_components_symbols", return_value=frozenset({"HASDEBT1"})),
            patch.object(loader, "_get_never_tagged_interest_expense_symbols", return_value=frozenset({"HASDEBT1"})),
        ):
            metrics = loader._compute_quality_metrics(
                "HASDEBT1", row, ev_metrics=(50_000_000.0, 10_000_000.0, 25_000_000.0)
            )

        assert metrics["total_debt"] == 50_000_000.0
        assert metrics.get("total_debt_unavailable_reason") is None

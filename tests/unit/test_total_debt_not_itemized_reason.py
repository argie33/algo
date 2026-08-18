"""Regression test: total_debt_unavailable_reason must distinguish a company that hasn't
reported any debt component (long_term_debt, short_term_debt, operating_lease_liability,
finance_lease_liability) in its 3 most recent fiscal years - most likely genuinely debt-free -
from a real SEC extraction gap.

Found live 2026-08-18 (goal: "no SEC data" audit, continuation of the interest_coverage /
current_ratio fixes): 440 of the universe's total_debt "missing_sec_data" rows have zero debt
components across their 3 most recent fiscal years on file. Unlike current_ratio/quick_ratio
(dominated by banks/REITs), this bucket is a mixed bag - SPACs ("Blank Checks", 127), pre-
revenue pharma/biotech (90), small tech/services companies (~70), and a smaller bank/REIT
contingent (~40) - so it gets its own reason string (total_debt_not_itemized) rather than
reit_special_entity, which would misdescribe most of these symbols. Same "3 most recent years,
not all-time history" windowing as _get_unclassified_balance_sheet_symbols() /
_get_no_recent_interest_expense_symbols().
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(operating_income=-17_841_919.0):
    # 34-column shape (index 33 = prior_year_gross_profit, added after
    # test_quality_metrics_implausible_ratio_reason.py's 33-column fixture was written).
    row = [None] * 34
    row[0] = 500_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[5] = operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_debt_symbols):
        self._no_recent_debt = no_recent_debt_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_balance_sheet" in self._last_query and "long_term_debt" in self._last_query:
            return [(s,) for s in self._no_recent_debt]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_debt_symbols=frozenset()):
        self._no_recent_debt = no_recent_debt_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_debt)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_debt_symbols=frozenset(), ev_metrics=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_debt_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestTotalDebtNotItemizedReason:
    def test_symbol_with_no_recent_debt_components_gets_not_itemized_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"SPAC1"}))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SPAC1", row, ev_metrics=None)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "total_debt_not_itemized"

    def test_symbol_not_in_no_recent_set_keeps_generic_reason(self, monkeypatch):
        # total_debt is None for this fiscal year, but the symbol reported debt recently
        # (real one-year extraction/timing gap) - must stay the generic "missing_sec_data".
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"SPAC1"}))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "missing_sec_data"

    def test_real_total_debt_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"SPAC1"}))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("SPAC1", row, ev_metrics=(50_000_000.0, 10_000_000.0, 25_000_000.0))

        assert metrics["total_debt"] == 50_000_000.0
        assert metrics.get("total_debt_unavailable_reason") is None

"""Regression test: interest_coverage_unavailable_reason must distinguish a company that
hasn't itemized interest expense in its 3 most recent fiscal years (debt-free, or netted into
other income/expense - not a data gap) from a genuine SEC extraction gap.

Found live 2026-08-18 (goal: "no SEC data" audit): live query found 927 of 1525 universe
interest_coverage "missing_sec_data" rows have zero interest_expense across their 3 most recent
fiscal years on file. AAPL is the clearest case: it reported real interest_expense every year
through FY2023 ($3.9B) but has netted it into "other income/(expense)" since FY2024 - a real,
large, indebted borrower that simply stopped breaking the line out, not a loader failure. Same
"3 most recent years, not all-time history" windowing as the current_ratio/quick_ratio
reit_special_entity fix (5cae1c18d) and the dividend-recency fix (7ef77e938), for the same
reason: a company can permanently change what it itemizes partway through its filing history.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(operating_income=-17_841_919.0, interest_expense=None):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
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
    def __init__(self, no_recent_interest_expense_symbols):
        self._no_recent = no_recent_interest_expense_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_income_statement" in self._last_query and "interest_expense" in self._last_query:
            return [(s,) for s in self._no_recent]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_interest_expense_symbols=frozenset()):
        self._no_recent = no_recent_interest_expense_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_interest_expense_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_interest_expense_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestInterestCoverageNotItemizedReason:
    def test_symbol_with_no_recent_interest_expense_gets_not_itemized_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_interest_expense_symbols=frozenset({"AAPL"}))
        row = _quality_row(interest_expense=None)

        metrics = loader._compute_quality_metrics("AAPL", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "interest_expense_not_itemized"

    def test_symbol_not_in_no_recent_set_keeps_generic_reason(self, monkeypatch):
        # interest_expense is None for this fiscal year, but the symbol reported it recently
        # (real one-year extraction/timing gap) - must stay the generic "missing_sec_data".
        loader = _make_loader(monkeypatch, no_recent_interest_expense_symbols=frozenset({"AAPL"}))
        row = _quality_row(interest_expense=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "missing_sec_data"

    def test_real_interest_expense_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_interest_expense_symbols=frozenset({"AAPL"}))
        row = _quality_row(operating_income=100_000_000.0, interest_expense=10_000_000.0)

        metrics = loader._compute_quality_metrics("AAPL", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 10.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

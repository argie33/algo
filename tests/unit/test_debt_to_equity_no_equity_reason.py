"""Regression test: debt_to_equity_unavailable_reason must distinguish a company that hasn't
reported stockholders_equity in its 3 most recent fiscal years from a real SEC extraction gap.

Found live 2026-08-18 (goal: "no SEC data" audit, continuation of the current_ratio/total_debt/
ebitda_margin fixes): 156 of 1,048 universe debt_to_equity "missing_sec_data" rows have zero
stockholders_equity across their 3 most recent fiscal years on file. A genuine mixed bag (pharma,
REITs, utilities, investment advice, real estate - no single entity type dominates), so this gets
its own reason string (stockholders_equity_not_reported) rather than reit_special_entity. Same "3
most recent years, not all-time history" windowing as the sibling fixes.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=None, total_liabilities=200_000_000.0):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_equity_symbols):
        self._no_recent_equity = no_recent_equity_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_balance_sheet" in self._last_query and "stockholders_equity" in self._last_query:
            return [(s,) for s in self._no_recent_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_equity_symbols=frozenset()):
        self._no_recent_equity = no_recent_equity_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_equity)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_equity_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_equity_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestDebtToEquityNoEquityReason:
    def test_symbol_with_no_recent_equity_gets_not_reported_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"AAT"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("AAT", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_symbol_not_in_no_recent_set_keeps_generic_reason(self, monkeypatch):
        # stockholders_equity is None for this fiscal year, but the symbol reported it recently
        # (real one-year extraction/timing gap) - must stay "missing_sec_data".
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"AAT"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "missing_sec_data"

    def test_real_equity_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"AAT"}))
        row = _quality_row(stockholders_equity=100_000_000.0, total_liabilities=200_000_000.0)

        metrics = loader._compute_quality_metrics("AAT", row, ev_metrics=None)

        assert metrics["debt_to_equity"] == 2.0
        assert metrics.get("debt_to_equity_unavailable_reason") is None

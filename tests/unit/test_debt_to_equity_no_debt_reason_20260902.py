"""Regression test: debt_to_equity_unavailable_reason must distinguish a genuinely debt-free (or
no-longer-itemizing) filer from a real SEC extraction gap - the debt-side counterpart to
test_debt_to_equity_no_equity_reason.py's equity-side fix.

Found live 2026-09-02 (goal: "no SEC data" audit continuation): debt_to_equity's compute block
fails whenever EITHER roic_stockholders_equity OR debt_for_roic is None, but the reason block
only ever checked the equity side via _get_no_recent_stockholders_equity_symbols() - the debt
side had no gate at all, even though total_debt_unavailable_reason already has one
(_get_no_recent_debt_components_symbols(), "total_debt_not_itemized") a few hundred lines below.
Live-confirmed 265 of 319 universe debt_to_equity "missing_sec_data" rows (83%) are this exact
debt-side gap.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=100_000_000.0, cash_and_equivalents=20_000_000.0, long_term_debt=None):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[20] = long_term_debt
    row[21] = cash_and_equivalents
    return row


class _FakeCursor:
    def __init__(self, no_recent_debt_symbols):
        self._no_recent_debt = no_recent_debt_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        # Only the batch _get_no_recent_debt_components_symbols() query selects
        # short_term_debt - the inline per-symbol fallback query (fetchone) never does.
        if "annual_balance_sheet" in self._last_query and "short_term_debt" in self._last_query:
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


def _make_loader(monkeypatch, no_recent_debt_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_debt_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestDebtToEquityNoDebtReason:
    def test_symbol_with_no_recent_debt_gets_not_itemized_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"DEBTFREE"}))
        # Real equity/cash on file, no debt anywhere (ev_metrics has no total_debt, no
        # long_term_debt on the balance sheet row either).
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "total_debt_not_itemized"

    def test_symbol_not_in_no_recent_debt_set_keeps_generic_reason(self, monkeypatch):
        # No debt on file for this row, but the symbol hasn't been confirmed structurally
        # debt-free across 3 recent years (real one-year extraction/timing gap) - must stay
        # "missing_sec_data".
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"DEBTFREE"}))
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "missing_sec_data"

    def test_real_debt_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"DEBTFREE"}))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(300_000_000.0, 0.0, 0.0))

        assert metrics["debt_to_equity"] == 3.0
        assert metrics.get("debt_to_equity_unavailable_reason") is None

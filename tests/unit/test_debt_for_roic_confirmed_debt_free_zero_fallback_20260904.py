"""Regression test: debt_for_roic (feeds debt_to_equity/roce_pct/roic_pct) must compute a real
0.0 debt value for a symbol double-confirmed structurally debt-free, instead of leaving those
fields None with a "missing_sec_data"/"total_debt_not_itemized" reason - a real-value fix, not
just a relabel.

Found 2026-09-04 (goal: "Missing SEC/XBRL data" reduction to zero). debt_to_equity's existing
fix (test_debt_to_equity_no_debt_reason_20260902.py) only relabels the reason once a symbol is
confirmed in _get_never_tagged_debt_components_symbols() - the value itself stays None, so the
row still counts under "Missing SEC/XBRL data" in the coverage dashboard (total_debt_not_itemized
maps to the same category). load_sec_valuations.py's own EV computation already treats a missing
total_debt as 0 (`debt_val = total_debt if total_debt else 0`, load_sec_valuations.py) rather than
blocking - this test locks in the same precedent applied to debt_for_roic, gated on BOTH the
never-tagged-debt-components AND never-tagged-interest-expense signals (stronger than the EV
precedent's single-signal bar) so a real, non-itemized debt-holder isn't silently zeroed.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=100_000_000.0, cash_and_equivalents=20_000_000.0, long_term_debt=None):
    # 34-column shape (index 33 = prior_year_gross_profit), matching
    # test_debt_to_equity_no_debt_reason_20260902.py's fixture.
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
    def __init__(self, never_tagged_debt_symbols, never_tagged_interest_symbols):
        self._never_tagged_debt = never_tagged_debt_symbols
        self._never_tagged_interest = never_tagged_interest_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_income_statement" in q and "interest_expense" in q:
            return [(s,) for s in self._never_tagged_interest]
        if "annual_balance_sheet" in q and "short_term_debt" in q and "ROW_NUMBER" not in q:
            # _get_never_tagged_debt_components_symbols (full-history, no windowing).
            return [(s,) for s in self._never_tagged_debt]
        if "annual_balance_sheet" in q and "short_term_debt" in q and "ROW_NUMBER" in q:
            # _get_no_recent_debt_components_symbols (3-year window) - not exercised here.
            return []
        return []

    def fetchone(self):
        # Per-symbol inline long_term_debt fallback search - nothing on file.
        return None


class _FakeDatabaseContext:
    def __init__(self, never_tagged_debt_symbols=frozenset(), never_tagged_interest_symbols=frozenset()):
        self._never_tagged_debt = never_tagged_debt_symbols
        self._never_tagged_interest = never_tagged_interest_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_debt, self._never_tagged_interest)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, never_tagged_debt_symbols=frozenset(), never_tagged_interest_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(never_tagged_debt_symbols, never_tagged_interest_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestDebtForRoicConfirmedDebtFreeZeroFallback:
    def test_double_confirmed_debt_free_computes_zero_debt_to_equity(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"DEBTFREE"}),
            never_tagged_interest_symbols=frozenset({"DEBTFREE"}),
        )
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_equity"] == 0.0
        assert metrics.get("debt_to_equity_unavailable_reason") is None

    def test_debt_never_tagged_but_interest_expense_reported_stays_unavailable(self, monkeypatch):
        # Debt components never itemized, but real interest expense IS on file somewhere -
        # contradicts "genuinely no debt" (an un-itemized debt-holder, not a debt-free filer) -
        # must NOT zero the debt out.
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"HASINTEREST"}),
            never_tagged_interest_symbols=frozenset(),
        )
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("HASINTEREST", row, ev_metrics=(None, None, None))

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "total_debt_not_itemized"

    def test_real_debt_still_computes_normally(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"DEBTFREE"}),
            never_tagged_interest_symbols=frozenset({"DEBTFREE"}),
        )
        row = _quality_row()

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(300_000_000.0, 0.0, 0.0))

        assert metrics["debt_to_equity"] == 3.0
        assert metrics.get("debt_to_equity_unavailable_reason") is None

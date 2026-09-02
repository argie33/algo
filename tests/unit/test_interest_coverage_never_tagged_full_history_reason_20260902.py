"""Regression test: interest_coverage_unavailable_reason must reuse the existing
"interest_expense_not_itemized" label for a symbol that has never once tagged a real,
nonzero interest_expense ANYWHERE in its filing history, even when it doesn't yet have the 3
consecutive real fiscal years _get_no_recent_interest_expense_symbols() requires (recent
IPOs/SPAC-mergers) - not just fall through to the generic "missing_sec_data".

Found live 2026-09-02 (goal: "keep the missing-data number going down" SEC/XBRL audit,
continuation of test_fcf_yield_capex_never_tagged_reason_20260902.py): 145 of quality_metrics'
167-row universe interest_coverage "missing_sec_data" residual genuinely have no fiscal year
anywhere with both a real interest_expense and a real operating_income/pretax_income; of a live
sample, 96 have interest_expense NULL in every real row on file (fewer than 3, so the existing
gate's `COUNT(*) = 3` requirement never fires) and 14 report a real $0 (never distinguished from
NULL by any existing gate). 87 of the 167 matched the new, broader
_get_never_tagged_interest_expense_symbols() check directly against the live DB.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(operating_income=-17_841_919.0, interest_expense=None):
    # Same 34-column shape as test_interest_coverage_not_itemized_reason.py's fixture.
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
    """Distinguishes the two interest-expense gate queries by their SQL shape:
    _get_no_recent_interest_expense_symbols() windows via ROW_NUMBER()/rn<=3;
    _get_never_tagged_interest_expense_symbols() is a plain full-history GROUP BY with no
    ROW_NUMBER() at all - the two must be tested independently, not conflated."""

    def __init__(self, no_recent_symbols, never_tagged_symbols):
        self._no_recent = no_recent_symbols
        self._never_tagged = never_tagged_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_income_statement" not in self._last_query or "interest_expense" not in self._last_query:
            return []
        if "ROW_NUMBER()" in self._last_query:
            return [(s,) for s in self._no_recent]
        return [(s,) for s in self._never_tagged]

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_symbols=frozenset(), never_tagged_symbols=frozenset()):
        self._no_recent = no_recent_symbols
        self._never_tagged = never_tagged_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent, self._never_tagged)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_symbols=frozenset(), never_tagged_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_symbols, never_tagged_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestInterestCoverageNeverTaggedFullHistoryReason:
    def test_symbol_only_in_never_tagged_gate_gets_not_itemized_reason(self, monkeypatch):
        # Not in the 3-recent-year gate (too new to have 3 real years) but IS in the
        # broader full-history "never once tagged a real interest expense" gate.
        loader = _make_loader(monkeypatch, never_tagged_symbols=frozenset({"RECENTIPO"}))
        row = _quality_row(interest_expense=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "interest_expense_not_itemized"

    def test_symbol_not_in_either_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_symbols=frozenset({"RECENTIPO"}))
        row = _quality_row(interest_expense=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "missing_sec_data"

    def test_real_interest_expense_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_symbols=frozenset({"RECENTIPO"}))
        row = _quality_row(operating_income=100_000_000.0, interest_expense=10_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 10.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

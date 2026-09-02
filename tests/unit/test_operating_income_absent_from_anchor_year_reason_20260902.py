"""Regression test (2026-09-02, quality_row_db anchor-year investigation follow-up to
test_net_income_absent_from_anchor_year_reason_20260902.py / test_revenue_absent_from_
anchor_year_quality_metrics_20260902.py): operating_margin/operating_profitability's
operating_income_for_margin only ever looked at the balance-sheet anchor fiscal year's own
operating_income (falling back within THAT SAME year to the pretax_income+interest_expense
EBIT approximation), never a different fiscal year - unlike its net_income/revenue siblings,
which already search full history via a dedicated positive gate. Fixed by adding
_get_operating_income_available_elsewhere_symbols() (COUNT(operating_income) >= 1 across any
available fiscal year) and requiring symbol membership in it before ever emitting
"operating_income_absent_from_anchor_year".
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    operating_income=None,
    pretax_income=None,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    revenue=100_000_000.0,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[4] = revenue
    row[5] = operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[23] = pretax_income
    return row


class _FakeCursor:
    """Distinguishes the new positive gate's query (COUNT(operating_income) >= 1) from every
    other gate query by exact query text, same discipline as the net_income/revenue sibling
    tests' fixtures."""

    def __init__(self, operating_income_available_elsewhere):
        self._operating_income_available_elsewhere = operating_income_available_elsewhere
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "COUNT(operating_income) >= 1" in q:
            return [(s,) for s in self._operating_income_available_elsewhere]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, operating_income_available_elsewhere=frozenset()):
        self._operating_income_available_elsewhere = operating_income_available_elsewhere

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._operating_income_available_elsewhere)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_operating_margin_absent_from_anchor_year_when_real_operating_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, operating_income_available_elsewhere=frozenset({"ZZZQ"}))
    row = _quality_row(operating_income=None, pretax_income=None)

    metrics = loader._compute_quality_metrics("ZZZQ", row, ev_metrics=None)

    assert metrics["operating_margin"] is None
    assert metrics["operating_margin_unavailable_reason"] == "operating_income_absent_from_anchor_year"


def test_operating_profitability_absent_from_anchor_year_when_real_operating_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, operating_income_available_elsewhere=frozenset({"ZZZQ"}))
    row = _quality_row(operating_income=None, pretax_income=None)

    metrics = loader._compute_quality_metrics("ZZZQ", row, ev_metrics=None)

    assert metrics["operating_profitability"] is None
    assert metrics["operating_profitability_unavailable_reason"] == "operating_income_absent_from_anchor_year"


def test_operating_margin_stays_generic_missing_sec_data_when_not_in_positive_gate(monkeypatch):
    """A symbol with no real operating_income anywhere is NOT in
    _get_operating_income_available_elsewhere_symbols() and must keep the generic
    "missing_sec_data" label - not be misdiagnosed as an anchor-year mismatch that doesn't
    actually exist."""
    loader = _make_loader(monkeypatch, operating_income_available_elsewhere=frozenset())
    row = _quality_row(operating_income=None, pretax_income=None)

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["operating_margin_unavailable_reason"] == "missing_sec_data"
    assert metrics["operating_profitability_unavailable_reason"] == "missing_sec_data"


def test_operating_margin_prefers_ebit_approximation_over_anchor_year_label(monkeypatch):
    """When the anchor year's own pretax_income IS available, operating_income_for_margin
    resolves via the same-year EBIT approximation and the value is computed normally - the
    anchor-year-mismatch label must never override a value that's actually available."""
    loader = _make_loader(monkeypatch, operating_income_available_elsewhere=frozenset({"HASEBIT"}))
    row = _quality_row(operating_income=None, pretax_income=50_000_000.0)

    metrics = loader._compute_quality_metrics("HASEBIT", row, ev_metrics=None)

    assert metrics["operating_margin"] is not None
    assert metrics["operating_margin_unavailable_reason"] is None

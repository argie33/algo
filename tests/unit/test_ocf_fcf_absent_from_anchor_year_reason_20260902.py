"""Regression test (2026-09-02, quality_row_db anchor-year investigation, same /goal session
as test_net_income_absent_from_anchor_year_reason_20260902.py and
test_revenue_absent_from_anchor_year_quality_metrics_20260902.py): accruals_ratio/
fcf_to_net_income/ocf_to_net_income/operating_cash_flow/free_cash_flow_unavailable_reason
fell to generic "missing_sec_data" when the balance-sheet anchor year's own annual_cash_flow
row is unavailable but the symbol has real operating_cash_flow/free_cash_flow in a nearby
fiscal year - a residual _get_no_recent_operating_cash_flow_symbols()/_get_no_recent_free_
cash_flow_symbols() themselves already documented as unfixed ("the rest have OCF/FCF in an
off-anchor year instead ... deliberately NOT fixed this pass").
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    revenue=100_000_000.0,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[4] = revenue
    # row[13] = operating_cash_flow, row[14] = free_cash_flow (both left None)
    return row


class _FakeCursor:
    def __init__(self, ocf_available_elsewhere, fcf_available_elsewhere):
        self._ocf_available_elsewhere = ocf_available_elsewhere
        self._fcf_available_elsewhere = fcf_available_elsewhere
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "HAVING COUNT(operating_cash_flow) >= 1" in q:
            return [(s,) for s in self._ocf_available_elsewhere]
        if "HAVING COUNT(free_cash_flow) >= 1" in q:
            return [(s,) for s in self._fcf_available_elsewhere]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, ocf_available_elsewhere=frozenset(), fcf_available_elsewhere=frozenset()):
        self._ocf_available_elsewhere = ocf_available_elsewhere
        self._fcf_available_elsewhere = fcf_available_elsewhere

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._ocf_available_elsewhere, self._fcf_available_elsewhere)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_operating_cash_flow_absent_from_anchor_year_when_real_ocf_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, ocf_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row()

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["operating_cash_flow_unavailable_reason"] == "operating_cash_flow_absent_from_anchor_year"
    assert metrics["accruals_ratio_unavailable_reason"] == "operating_cash_flow_absent_from_anchor_year"
    assert metrics["ocf_to_net_income_unavailable_reason"] == "operating_cash_flow_absent_from_anchor_year"


def test_free_cash_flow_absent_from_anchor_year_when_real_fcf_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, fcf_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row()

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["free_cash_flow_unavailable_reason"] == "free_cash_flow_absent_from_anchor_year"
    assert metrics["fcf_to_net_income_unavailable_reason"] == "free_cash_flow_absent_from_anchor_year"


def test_operating_cash_flow_stays_generic_missing_sec_data_when_not_in_positive_gate(monkeypatch):
    """A symbol with no real OCF anywhere is NOT in
    _get_operating_cash_flow_available_elsewhere_symbols() and must keep the generic
    "missing_sec_data" label rather than being misdiagnosed as an anchor-year mismatch that
    doesn't exist."""
    loader = _make_loader(monkeypatch)
    row = _quality_row()

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["operating_cash_flow_unavailable_reason"] == "missing_sec_data"

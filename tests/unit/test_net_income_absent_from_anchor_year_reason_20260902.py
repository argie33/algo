"""Regression test (2026-09-02, quality_row_db anchor-year investigation, same /goal session
as test_quality_metrics_never_tagged_full_history_reason_sweep_20260902.py): roe/roa/
net_margin/sustainable_growth_rate's reason blocks in load_value_quality_growth_metrics.py
used to infer "net_income exists somewhere, just not for this specific balance-sheet anchor
fiscal year" from "symbol is in neither _get_no_recent_net_income_symbols() nor
_get_never_tagged_net_income_symbols()" - but that inference is wrong for a symbol with ZERO
available annual_income_statement rows at all (both of those gates require >=1/3 real rows
to fire, so a symbol with none slips through un-flagged by either while genuinely having no
net_income data anywhere - live-caught by that file's test_symbols_not_in_any_gate_keep_
generic_reason regression). Fixed by adding a direct positive gate,
_get_net_income_available_elsewhere_symbols() (COUNT(net_income) >= 1 across any available
fiscal year), and requiring symbol membership in it before ever emitting
"net_income_absent_from_anchor_year" - this file exercises that gate on its own, distinct
from the never-tagged/no-recent gates' "COUNT(net_income) = 0" queries.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=None,
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
    return row


class _FakeCursor:
    """Distinguishes the new positive gate's query (COUNT(net_income) >= 1) from the
    never-tagged/no-recent gates' negative queries (COUNT(net_income) = 0 / ROW_NUMBER())
    by exact query text, rather than the coarser table+column substring match the sibling
    test file's fixture uses - those two query shapes must be told apart for this test to
    mean anything."""

    def __init__(self, net_income_available_elsewhere):
        self._net_income_available_elsewhere = net_income_available_elsewhere
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "COUNT(net_income) >= 1" in q:
            return [(s,) for s in self._net_income_available_elsewhere]
        # Every other gate query (never-tagged equity/net_income/total_assets, no-recent
        # windowed variants) returns empty - this test only exercises the new positive gate.
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, net_income_available_elsewhere=frozenset()):
        self._net_income_available_elsewhere = net_income_available_elsewhere

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._net_income_available_elsewhere)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_net_margin_absent_from_anchor_year_when_real_net_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, net_income_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["net_margin"] is None
    assert metrics["net_margin_unavailable_reason"] == "net_income_absent_from_anchor_year"


def test_roe_absent_from_anchor_year_when_real_net_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, net_income_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["roe"] is None
    assert metrics["roe_unavailable_reason"] == "net_income_absent_from_anchor_year"


def test_roa_absent_from_anchor_year_when_real_net_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, net_income_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["roa"] is None
    assert metrics["roa_unavailable_reason"] == "net_income_absent_from_anchor_year"


def test_sustainable_growth_rate_absent_from_anchor_year_when_real_net_income_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, net_income_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["sustainable_growth_rate_unavailable_reason"] == "net_income_absent_from_anchor_year"


def test_net_margin_stays_generic_missing_sec_data_when_not_in_positive_gate(monkeypatch):
    """A symbol with no real net_income anywhere (zero available annual_income_statement
    rows, or genuinely never tagged) is NOT in _get_net_income_available_elsewhere_symbols()
    and must keep the generic "missing_sec_data" label - not be misdiagnosed as an
    anchor-year mismatch that doesn't actually exist."""
    loader = _make_loader(monkeypatch, net_income_available_elsewhere=frozenset())
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["net_margin_unavailable_reason"] == "missing_sec_data"

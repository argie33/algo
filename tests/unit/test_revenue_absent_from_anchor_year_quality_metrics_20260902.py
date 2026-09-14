"""Regression test (2026-09-02, quality_row_db anchor-year investigation, same /goal session
as test_net_income_absent_from_anchor_year_reason_20260902.py): asset_turnover/ebitda_margin
fell to generic "missing_sec_data" when the balance-sheet anchor year's own
annual_income_statement row is unavailable but the symbol has real revenue in a nearby
fiscal year - a residual _get_no_recent_revenue_symbols() itself already documented as
unfixed back on 2026-08-18 ("a distinct fiscal-year-anchor-selection gap ... deliberately
NOT covered by this windowed check"). Reuses the "revenue_absent_from_anchor_year" reason
string (already wired into scores.py's coverage categorization for the value_metrics
ev_revenue/ps_ratio sibling fix landed earlier this session), via a new direct positive
gate, _get_revenue_available_elsewhere_symbols().
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    revenue=None,
    cost_of_revenue=None,
    gross_profit=None,
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
    row[12] = cost_of_revenue
    row[19] = gross_profit
    return row


class _FakeCursor:
    def __init__(self, revenue_available_elsewhere):
        self._revenue_available_elsewhere = revenue_available_elsewhere
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "FILTER (WHERE revenue IS NOT NULL AND revenue != 0) >= 1" in q:
            return [(s,) for s in self._revenue_available_elsewhere]
        # Every other gate query (no-recent/never-tagged windowed variants, blank-check,
        # total-assets/equity gates) returns empty - this test only exercises the new
        # positive revenue gate.
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, revenue_available_elsewhere=frozenset()):
        self._revenue_available_elsewhere = revenue_available_elsewhere

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._revenue_available_elsewhere)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_asset_turnover_absent_from_anchor_year_when_real_revenue_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, revenue_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(revenue=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["asset_turnover"] is None
    assert metrics["asset_turnover_unavailable_reason"] == "revenue_absent_from_anchor_year"


def test_ebitda_margin_absent_from_anchor_year_when_real_revenue_exists_elsewhere(monkeypatch):
    loader = _make_loader(monkeypatch, revenue_available_elsewhere=frozenset({"OBX"}))
    row = _quality_row(revenue=None)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["ebitda_margin_unavailable_reason"] in (
        "revenue_absent_from_anchor_year",
        "reit_special_entity",
        "implausible_ratio",
        None,
    )
    # Not asserting the exact string beyond ruling out a crash / stale generic label -
    # ebitda_margin has an earlier no_operating_income_concept branch that may legitimately
    # take priority depending on the fixture's other None fields; the key regression guard
    # is that "missing_sec_data" never wins once real revenue is known to exist elsewhere.
    assert metrics["ebitda_margin_unavailable_reason"] != "missing_sec_data"


def test_gross_margin_absent_from_anchor_year_when_real_revenue_exists_elsewhere(monkeypatch):
    """FIX 2026-09-03: gross_margin was documented (in this same gate's own docstring) as part
    of the 2026-09-02 anchor-year fix alongside ebitda_margin/asset_turnover, but the branch was
    never actually wired for it - it kept falling to generic "missing_sec_data" ever since."""
    loader = _make_loader(monkeypatch, revenue_available_elsewhere=frozenset({"OBX"}))
    # Real gross_profit present (so no_gross_profit_concept is False / not reit_special_entity),
    # revenue absent from the anchor row (so gross_profit_revenue can't resolve).
    row = _quality_row(revenue=None, cost_of_revenue=40_000_000.0, gross_profit=60_000_000.0)

    metrics = loader._compute_quality_metrics("OBX", row, ev_metrics=None)

    assert metrics["gross_margin"] is None
    assert metrics["gross_margin_unavailable_reason"] == "revenue_absent_from_anchor_year"


def test_gross_margin_stays_generic_missing_sec_data_when_not_in_positive_gate(monkeypatch):
    loader = _make_loader(monkeypatch, revenue_available_elsewhere=frozenset())
    row = _quality_row(revenue=None, cost_of_revenue=40_000_000.0, gross_profit=60_000_000.0)

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["gross_margin_unavailable_reason"] == "missing_sec_data"


def test_asset_turnover_stays_generic_missing_sec_data_when_not_in_positive_gate(monkeypatch):
    """A symbol with no real revenue anywhere is NOT in
    _get_revenue_available_elsewhere_symbols() and must keep the generic "missing_sec_data"
    label rather than being misdiagnosed as an anchor-year mismatch that doesn't exist."""
    loader = _make_loader(monkeypatch, revenue_available_elsewhere=frozenset())
    row = _quality_row(revenue=None)

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["asset_turnover_unavailable_reason"] == "missing_sec_data"

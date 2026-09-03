"""Regression test (2026-09-03, "Missing SEC/XBRL data" reduction goal session):
current_ratio/quick_ratio's reason chains never checked either structural input
(current_assets/current_liabilities) against a no-data gate at all - unlike every other ratio
in this file, which reuses `_get_no_recent_X_symbols()`/`_get_never_tagged_X_symbols()` pairs
for their own inputs. Not a "left behind sibling" bug like the others fixed today - the gate
infrastructure for current_assets/current_liabilities simply never existed before this fix.
Live-confirmed 33 of 64 universe current_ratio/quick_ratio "missing_sec_data" rows have
current_assets or current_liabilities in one of the 4 new gates this fix adds.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    current_assets=150_000_000.0,
    current_liabilities=100_000_000.0,
    revenue=None,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = current_assets
    row[7] = current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    """Windowed gates (ROW_NUMBER()) always return empty - only the never-tagged full-history
    siblings (plain GROUP BY, no ROW_NUMBER()) can fire in this test."""

    def __init__(self, never_tagged_current_assets, never_tagged_current_liabilities):
        self._never_tagged_current_assets = never_tagged_current_assets
        self._never_tagged_current_liabilities = never_tagged_current_liabilities
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "current_assets" in q:
            return [(s,) for s in self._never_tagged_current_assets]
        if "current_liabilities" in q:
            return [(s,) for s in self._never_tagged_current_liabilities]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, never_tagged_current_assets=frozenset(), never_tagged_current_liabilities=frozenset()):
        self._never_tagged_current_assets = never_tagged_current_assets
        self._never_tagged_current_liabilities = never_tagged_current_liabilities

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_current_assets, self._never_tagged_current_liabilities)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestCurrentRatioQuickRatioNeverTaggedGates:
    def test_current_ratio_never_tagged_current_assets(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_current_assets=frozenset({"RECENTIPO"}))
        row = _quality_row(current_assets=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["current_ratio"] is None
        assert metrics["current_ratio_unavailable_reason"] == "no_recent_current_assets_reported"

    def test_current_ratio_never_tagged_current_liabilities(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_current_liabilities=frozenset({"RECENTIPO"}))
        row = _quality_row(current_liabilities=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["current_ratio"] is None
        assert metrics["current_ratio_unavailable_reason"] == "no_recent_current_liabilities_reported"

    def test_quick_ratio_never_tagged_current_assets(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_current_assets=frozenset({"RECENTIPO"}))
        row = _quality_row(current_assets=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["quick_ratio"] is None
        assert metrics["quick_ratio_unavailable_reason"] == "no_recent_current_assets_reported"

    def test_symbols_not_in_gate_keep_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(current_assets=None, current_liabilities=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["current_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["quick_ratio_unavailable_reason"] == "missing_sec_data"

    def test_positive_control_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NORMALCO2", row, ev_metrics=None)

        assert metrics["current_ratio"] is not None
        assert metrics["current_ratio_unavailable_reason"] is None
        assert metrics["quick_ratio_unavailable_reason"] is None

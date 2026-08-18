"""Regression test for load_enhanced_quality_growth_metrics.py's _process_one_symbol() UPDATE.

Covers a stale-reason bug: the growth_metrics/quality_metrics UPDATE only ever SET the value
column for a computed field, never the paired {field}_unavailable_reason column - so a symbol
whose baseline load_value_quality_growth_metrics.py pass set e.g. "no_analyst_estimates" kept
that stale reason forever even after this loader computed and wrote a real value here.
Live-confirmed on quality_metrics: AAPL/MSFT/CMS/D/TNDM all had real non-NULL
estimate_revision_direction/revision_activity_30d/estimate_momentum_60d/estimate_momentum_90d/
revision_trend_score values while their _unavailable_reason columns still read
"no_analyst_estimates" - 3,750/4,959 active-universe symbols affected on
estimate_revision_direction alone.
"""

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, list]] = []

    def execute(self, query, params=None):
        self.executed.append((query, params))


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def _loader(monkeypatch, metric_dict):
    import loaders.load_enhanced_quality_growth_metrics as mod

    cursor = _FakeCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "fetch_incremental", lambda *a, **k: [metric_dict])
    loader._watermark = type("_FakeWatermark", (), {"advance_watermark": lambda self, **kw: None})()
    return loader, cursor


class TestStaleReasonClearedOnRealValue:
    def test_quality_metrics_update_clears_paired_reason_column(self, monkeypatch):
        metric_dict = {
            "estimate_revision_direction": 2.0,
            "revision_activity_30d": 2.0,
            "estimate_momentum_60d": 1.5,
            "estimate_momentum_90d": 1.2,
            "revision_trend_score": 1.35,
        }
        loader, cursor = _loader(monkeypatch, metric_dict)

        loader._process_one_symbol("AAPL", None, [None])

        quality_update = next(q for q, _ in cursor.executed if "UPDATE quality_metrics" in q)
        assert "estimate_revision_direction_unavailable_reason = NULL" in quality_update
        assert "revision_activity_30d_unavailable_reason = NULL" in quality_update
        assert "estimate_momentum_60d_unavailable_reason = NULL" in quality_update
        assert "estimate_momentum_90d_unavailable_reason = NULL" in quality_update
        assert "revision_trend_score_unavailable_reason = NULL" in quality_update

    def test_growth_metrics_update_clears_paired_reason_column(self, monkeypatch):
        metric_dict = {"sustainable_growth_rate": 0.12, "fcf_growth_yoy": 0.05}
        loader, cursor = _loader(monkeypatch, metric_dict)

        loader._process_one_symbol("AAPL", None, [None])

        growth_update = next(q for q, _ in cursor.executed if "UPDATE growth_metrics" in q)
        assert "sustainable_growth_rate_unavailable_reason = NULL" in growth_update
        assert "fcf_growth_yoy_unavailable_reason = NULL" in growth_update

    def test_field_absent_from_metric_dict_does_not_touch_its_reason_column(self, monkeypatch):
        metric_dict = {"estimate_revision_direction": 2.0}
        loader, cursor = _loader(monkeypatch, metric_dict)

        loader._process_one_symbol("AAPL", None, [None])

        quality_update = next(q for q, _ in cursor.executed if "UPDATE quality_metrics" in q)
        assert "revision_activity_30d_unavailable_reason = NULL" not in quality_update
        assert "revision_activity_30d = %s" not in quality_update

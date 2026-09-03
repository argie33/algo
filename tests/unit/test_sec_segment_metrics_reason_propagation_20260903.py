"""Regression test: sec_segment_metrics.reason must propagate sec_segment_info's own
already-diagnosed terminal reason (companyfacts_api_never_exposes_per_segment_revenue,
no_us_gaap_facts, symbol_not_found, zero_total_segment_revenue, ...) instead of collapsing
every one of them into the generic "no_computable_segment_metrics".

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction sweep): fetch_incremental()
only respected sec_segment_info.reason early when it matched a narrow substring allowlist
("single_segment"/"no_segment") - any OTHER real, already-diagnosed terminal reason instead
fell through to "try to proceed anyway" with all-None segment fields, landed on
all_missing=True, and got silently discarded in favor of the generic
"no_computable_segment_metrics" label. Live-confirmed 155 universe sec_segment_metrics rows
carry one of the 4 non-matching upstream reasons instead - same reason-propagation-gap shape
as positioning_metrics.short_interest_pct fixed earlier this session.
"""

from loaders.load_sec_segment_metrics import SecSegmentMetricsLoader


def _make_loader():
    return SecSegmentMetricsLoader.__new__(SecSegmentMetricsLoader)


class _RoutingCursor:
    def __init__(self, segment_info_row=None):
        self._row = segment_info_row

    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


def _run(monkeypatch, segment_info_row):
    import loaders.load_sec_segment_metrics as mod

    cursor = _RoutingCursor(segment_info_row=segment_info_row)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    return loader.fetch_incremental("TEST", since=None)[0]


class TestSegmentMetricsReasonPropagation:
    def test_propagates_companyfacts_api_never_exposes_per_segment_revenue(self, monkeypatch):
        # (segment_count, largest_segment_revenue_pct, revenue_concentration_hhi,
        #  segment_data_available, data_unavailable, reason)
        row = (None, None, None, False, True, "companyfacts_api_never_exposes_per_segment_revenue")
        result = _run(monkeypatch, row)

        assert result["reason"] == "companyfacts_api_never_exposes_per_segment_revenue"
        assert result["data_unavailable"] is True

    def test_propagates_no_us_gaap_facts(self, monkeypatch):
        row = (None, None, None, False, True, "no_us_gaap_facts")
        result = _run(monkeypatch, row)

        assert result["reason"] == "no_us_gaap_facts"

    def test_propagates_symbol_not_found(self, monkeypatch):
        row = (None, None, None, False, True, "symbol_not_found")
        result = _run(monkeypatch, row)

        assert result["reason"] == "symbol_not_found"

    def test_propagates_zero_total_segment_revenue(self, monkeypatch):
        row = (None, None, None, False, True, "zero_total_segment_revenue")
        result = _run(monkeypatch, row)

        assert result["reason"] == "zero_total_segment_revenue"

    def test_no_reason_falls_back_to_generic(self, monkeypatch):
        row = (None, None, None, False, True, None)
        result = _run(monkeypatch, row)

        assert result["reason"] == "no_computable_segment_metrics"

    def test_single_segment_reason_still_short_circuits_early(self, monkeypatch):
        row = (None, None, None, False, True, "no_segment_dimension_contexts_in_xbrl_xml")
        result = _run(monkeypatch, row)

        assert result["reason"] == "no_segment_dimension_contexts_in_xbrl_xml"

    def test_real_values_still_populate_with_no_reason(self, monkeypatch):
        row = (3, 55.0, 0.42, True, False, None)
        result = _run(monkeypatch, row)

        assert result["segment_count"] == 3
        assert result["data_unavailable"] is False
        assert result.get("reason") is None

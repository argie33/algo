#!/usr/bin/env python3
"""Regression test for loaders/load_sec_segment_metrics.py.

Two real crash bugs, both confirmed live (not just mypy noise):

1. fetch_incremental() called self._unavailable_marker(...), a method that was never
   defined on SecSegmentMetricsLoader or OptimalLoader - every symbol hitting either
   "no segment_row" or "unavailable or not has_data" raised AttributeError. The same
   bug was already found and fixed once in load_sec_cash_flow_metrics.py (module-level
   function instead of a nonexistent method) - this file had the identical bug,
   unfixed.
2. safe_float(largest_segment_pct) / safe_float(hhi) were called without the required
   field_name argument (utils.type_conversion.safe_float has no default for it) -
   confirmed via direct call that this raises TypeError. This is the loader's success
   path (a symbol WITH real segment data), so it was completely non-functional too.
"""

import pytest

from loaders.load_sec_segment_metrics import _unavailable_marker
from utils.type_conversion import safe_float


class TestUnavailableMarkerIsAPlainFunction:
    def test_returns_valid_marker_dict(self):
        marker = _unavailable_marker("AAPL", "no_segment_disclosure")
        assert marker["symbol"] == "AAPL"
        assert marker["data_unavailable"] is True
        assert marker["reason"] == "no_segment_disclosure"
        # Every real column must be present (even if None) - matches this loader's
        # success-path dict shape so downstream code sees a consistent schema.
        for key in ("segment_count", "largest_segment_revenue_pct", "revenue_concentration_hhi", "is_diversified"):
            assert key in marker
            assert marker[key] is None

    def test_is_not_a_bound_method_call(self):
        """Regression guard: this must be callable as a plain function, not
        self._unavailable_marker(...) - that call pattern is what crashed before."""
        # If this were still (incorrectly) only a method, calling it as a bare function
        # with exactly these two positional args would still work identically -  the
        # real regression this guards is `self._unavailable_marker(...)` appearing
        # anywhere in fetch_incremental, checked separately via source inspection below.
        result = _unavailable_marker("MSFT", "segment_data_unavailable")
        assert result["reason"] == "segment_data_unavailable"

    def test_fetch_incremental_does_not_call_missing_self_method(self):
        import inspect

        from loaders.load_sec_segment_metrics import SecSegmentMetricsLoader

        source = inspect.getsource(SecSegmentMetricsLoader.fetch_incremental)
        assert "self._unavailable_marker" not in source, (
            "fetch_incremental must not call self._unavailable_marker - that method "
            "was never defined and every call to it raised AttributeError"
        )


class TestNoDeadGeographicFallback:
    """2026-07-27: fetch_incremental() had a second query block, gated on `if not
    segment_row`, that counted DISTINCT segment_name WHERE segment_type = 'geographic'
    and built a fabricated-looking marker (has_data=True, largest_segment_pct=None,
    hhi=None) as a "fallback" when no primary segment row was found. This was provably
    dead: load_sec_segment_info.py's own _unavailable_marker() always writes
    segment_type=None on data_unavailable=TRUE rows (confirmed by reading its source),
    so a symbol with zero data_unavailable=FALSE rows (the only way `not segment_row`
    fires) can never have a row with segment_type='geographic' to match on - the two
    branches' preconditions are mutually exclusive by construction. Confirmed live
    against the DB: zero sec_segment_metrics rows exist with the fallback's distinctive
    signature (largest_segment_revenue_pct AND revenue_concentration_hhi both NULL
    while data_unavailable=FALSE) - it had never once fired. Removed outright; the
    primary query already correctly picks up real geographic-segment filers (their rows
    have data_unavailable=FALSE regardless of segment_type, so they satisfy the primary
    unfiltered query directly)."""

    def test_fetch_incremental_has_no_geographic_fallback_query(self):
        import inspect

        from loaders.load_sec_segment_metrics import SecSegmentMetricsLoader

        source = inspect.getsource(SecSegmentMetricsLoader.fetch_incremental)
        assert "geographic" not in source, (
            "the geographic-segment fallback query was dead code (provably "
            "unreachable given how load_sec_segment_info.py builds unavailable "
            "markers) and was removed - it should not be reintroduced without first "
            "establishing a real code path that leaves segment_type='geographic' set "
            "on a data_unavailable=TRUE row"
        )


class TestSafeFloatCallsIncludeFieldName:
    def test_safe_float_requires_field_name_positional_arg(self):
        """Confirms the underlying constraint this loader's bug violated: safe_float
        has no default for field_name, so omitting it is a real TypeError, not a
        style/lint issue."""
        with pytest.raises(TypeError):
            safe_float(42.5)  # type: ignore[call-arg]

    def test_fetch_incremental_passes_field_name_to_every_safe_float_call(self):
        import inspect

        from loaders.load_sec_segment_metrics import SecSegmentMetricsLoader

        source = inspect.getsource(SecSegmentMetricsLoader.fetch_incremental)
        for line in source.splitlines():
            if "safe_float(" in line:
                assert "," in line.split("safe_float(", 1)[1], (
                    f"safe_float call missing field_name argument: {line.strip()!r}"
                )

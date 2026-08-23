"""Regression test: a real exception during fetch_incremental() must not be silently relabeled
as a generic legitimate-gap reason.

Before this fix, ValueQualityGrowthMetricsLoader.fetch_incremental()'s catch-all `except
Exception` handler called _unavailable_marker() with no `reason` for all three tables (value_
metrics, quality_metrics, growth_metrics), so a genuine bug/exception during fetch (a DB error,
a malformed row, anything unexpected - as opposed to a symbol that legitimately lacks the data)
got the exact same "missing_sec_data"/"insufficient_history" reason every real data gap gets.
That's indistinguishable from a legitimate absence in the Scores Data Coverage rollup, so a real
loader bug could hide inside "Missing SEC/XBRL data"/"Insufficient history" forever instead of
showing up in "Other (errors / excluded)" where an unexplained error belongs.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_fetch_exception_reason_is_not_generic_missing_data() -> None:
    loader = _loader()

    with patch(
        "loaders.load_value_quality_growth_metrics.DatabaseContext",
        side_effect=RuntimeError("connection reset"),
    ):
        [(value_dict, quality_dict, growth_dict)] = loader.fetch_incremental("TEST", date(2026, 8, 21))

    for d in (value_dict, quality_dict, growth_dict):
        assert d["data_unavailable"] is True

    # Every per-field *_unavailable_reason must carry the real exception, not the generic
    # "missing_sec_data"/"insufficient_history" a legitimate data gap would get. Exclude
    # forward_pe_unavailable_reason: hardcoded to "analyst_estimates_not_in_sec_filings"
    # regardless of cause - forward P/E structurally never comes from SEC filings, exception
    # or not, so that field intentionally doesn't vary with `reason`.
    for d in (value_dict, quality_dict, growth_dict):
        reason_fields = [
            v
            for k, v in d.items()
            if k.endswith("_unavailable_reason") and v is not None and k != "forward_pe_unavailable_reason"
        ]
        assert reason_fields, f"expected at least one populated reason field in {d['symbol']!r} marker"
        for reason in reason_fields:
            assert reason.startswith("fetch_exception: RuntimeError"), reason
            assert reason not in ("missing_sec_data", "insufficient_history")


def test_unavailable_marker_defaults_unchanged_when_no_reason_passed() -> None:
    loader = _loader()
    quality = loader._unavailable_marker("quality_metrics", "TEST")
    growth = loader._unavailable_marker("growth_metrics", "TEST")

    assert quality["roe_unavailable_reason"] == "missing_sec_data"
    assert growth["eps_growth_5y_unavailable_reason"] == "insufficient_history"


def test_unavailable_marker_uses_specific_reason_when_passed() -> None:
    loader = _loader()
    quality = loader._unavailable_marker("quality_metrics", "TEST", reason="fetch_exception: KeyError: 'x'")
    growth = loader._unavailable_marker("growth_metrics", "TEST", reason="fetch_exception: KeyError: 'x'")

    assert quality["roe_unavailable_reason"] == "fetch_exception: KeyError: 'x'"
    assert growth["eps_growth_5y_unavailable_reason"] == "fetch_exception: KeyError: 'x'"


def test_categorize_reason_routes_fetch_exception_to_other_bucket() -> None:
    import importlib

    scores_mod = importlib.import_module("lambda.api.routes.scores")
    assert scores_mod._categorize_reason("fetch_exception: RuntimeError: boom") == "Other (errors / excluded)"

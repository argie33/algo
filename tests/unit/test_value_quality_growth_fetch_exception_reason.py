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
    value = loader._unavailable_marker("value_metrics", "TEST")
    quality = loader._unavailable_marker("quality_metrics", "TEST")
    growth = loader._unavailable_marker("growth_metrics", "TEST")

    assert value["pe_ratio_unavailable_reason"] == "missing_sec_data"
    assert quality["roe_unavailable_reason"] == "missing_sec_data"
    assert growth["eps_growth_5y_unavailable_reason"] == "insufficient_history"


def test_unavailable_marker_uses_specific_reason_when_passed() -> None:
    loader = _loader()
    value = loader._unavailable_marker("value_metrics", "TEST", reason="fetch_exception: KeyError: 'x'")
    quality = loader._unavailable_marker("quality_metrics", "TEST", reason="fetch_exception: KeyError: 'x'")
    growth = loader._unavailable_marker("growth_metrics", "TEST", reason="fetch_exception: KeyError: 'x'")

    assert value["pe_ratio_unavailable_reason"] == "fetch_exception: KeyError: 'x'"
    assert quality["roe_unavailable_reason"] == "fetch_exception: KeyError: 'x'"
    assert growth["eps_growth_5y_unavailable_reason"] == "fetch_exception: KeyError: 'x'"


def test_unavailable_marker_whole_row_reason_matches_specific_reason() -> None:
    """BUG FOUND 2026-08-24 (real-money-readiness goal, log-audit pass): the whole-row
    `reason` key was hardcoded per-table ("Insufficient SEC valuation data" / "Insufficient
    SEC financial data" / "Insufficient historical data") regardless of the real cause -
    diverging from every per-field *_unavailable_reason above it, which correctly carries a
    real exception message. Live-confirmed 1,298 value_metrics rows universe-wide all shared
    this one generic whole-row reason. Confirmed dead for the Scores Data Coverage dashboard
    (value_metrics/quality_metrics/growth_metrics are deliberately excluded from scores.py's
    bare_reason_tables in favor of the granular per-field columns), but still misleading to
    direct DB inspection/debugging - a real fetch exception would read as a generic "no data"
    message at the row level."""
    loader = _loader()
    for table, field in (
        ("value_metrics", "pe_ratio_unavailable_reason"),
        ("quality_metrics", "roe_unavailable_reason"),
        ("growth_metrics", "eps_growth_5y_unavailable_reason"),
    ):
        no_reason = loader._unavailable_marker(table, "TEST")
        assert no_reason["reason"] == no_reason[field]

        with_reason = loader._unavailable_marker(table, "TEST", reason="fetch_exception: KeyError: 'x'")
        assert with_reason["reason"] == "fetch_exception: KeyError: 'x'"
        assert with_reason["reason"] == with_reason[field]


def test_categorize_reason_routes_fetch_exception_to_other_bucket() -> None:
    import importlib

    scores_mod = importlib.import_module("lambda.api.routes.scores")
    assert scores_mod._categorize_reason("fetch_exception: RuntimeError: boom") == "Other (errors / excluded)"

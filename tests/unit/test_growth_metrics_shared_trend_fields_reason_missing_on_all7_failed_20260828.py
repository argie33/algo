"""Regression test: _compute_growth_metrics's len(failed_metrics)==7 branch must set reason
codes for _SHARED_TREND_FIELDS, not just leave them NULL.

Found live 2026-08-28 in the same audit pass that found the book_value_growth and quality_score
_unavailable_marker gaps (see the two sibling test files with the same date suffix). Root cause
is different from those two: fetch_incremental (~line 874) copies _SHARED_TREND_FIELDS (value
AND reason) from quality_dict into growth_dict, but only `if not growth_dict.get(
"data_unavailable")`. Every path that sets growth_dict["data_unavailable"] = True goes through
_unavailable_marker() first (which already populates real reasons for all 16 shared fields) -
except the len(failed_metrics) == 7 branch inside _compute_growth_metrics itself, which sets
data_unavailable=True directly by mutating the in-progress `metrics` dict, bypassing
_unavailable_marker entirely. Live-confirmed 118 symbols (CXII, AARD, TMS, AEON, etc.) with all
16 shared fields NULL/NULL despite this branch's own `metrics["reason"]` already explaining
exactly what's missing on the very same row.
"""

from loaders.load_value_quality_growth_metrics import _SHARED_TREND_FIELDS, ValueQualityGrowthMetricsLoader


def _loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


# A single fiscal year of income-statement history: every CAGR period (1y/3y/5y revenue, EPS,
# book_value_growth) needs at least 2 data points, so all 7 fail with insufficient_history -
# the len(failed_metrics) == 7 branch this test targets.
_SINGLE_YEAR_INCOME_ROWS = [(2026, 100.0, 10.0, 5.0, 1.0, 100.0, 100.0, 500.0)]


class TestAllSevenFailedBranchSetsSharedTrendFieldReasons:
    def test_data_unavailable_true_with_real_reason(self) -> None:
        result = _loader()._compute_growth_metrics("TESTSYM", _SINGLE_YEAR_INCOME_ROWS)
        assert result["data_unavailable"] is True
        assert result["reason"].startswith("Insufficient historical data:")

    def test_every_shared_trend_field_gets_a_reason(self) -> None:
        result = _loader()._compute_growth_metrics("TESTSYM", _SINGLE_YEAR_INCOME_ROWS)
        for field in _SHARED_TREND_FIELDS:
            assert result.get(field) is None
            assert result.get(f"{field}_unavailable_reason") is not None, (
                f"{field}_unavailable_reason must not be NULL when data_unavailable=True with "
                "a known reason - NULL here is indistinguishable from a bug"
            )
            assert result[f"{field}_unavailable_reason"] == result["reason"]

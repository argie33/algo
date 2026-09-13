"""Regression test for the 2026-09-13 fix to loaders/load_trend_analysis.py::run()'s
post-merge availability labeling.

Root-caused alongside the load_technical_indicators.py ROC_OVERFLOW_SKIP marker fix (see
data_patrol_backlog_report.py's 'needs_fix' review for the technical_data_daily/
trend_template_data coverage shortfall): trend_template_data is built via an INNER JOIN
against technical_data_daily, so once a symbol's technical_data_daily row exists only as an
unavailable-marker (data_unavailable=TRUE, every indicator column NULL), that row now flows
into `merged` instead of being silently dropped by the join. But `run()` used to
unconditionally set `merged["data_unavailable"] = False` after the join, regardless of the
source row's own flag - mislabeling a propagated unavailable-marker row as a successful
computation, even though its weinstein_stage/minervini_trend_score/etc are already all NaN.
"""

import numpy as np
import pandas as pd

from loaders.load_trend_analysis import _propagate_source_availability


def _build_merged(**overrides) -> pd.DataFrame:
    base = {
        "symbol": pd.Series(["AAA"]),
        "weinstein_stage": pd.Series([pd.NA]),
        "minervini_trend_score": pd.Series([np.nan]),
        "source_data_unavailable": pd.Series([False]),
        "source_reason": pd.Series([None]),
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestPropagateSourceAvailability:
    def test_normal_computed_row_stays_available(self):
        merged = _build_merged(
            weinstein_stage=pd.Series([2]),
            minervini_trend_score=pd.Series([6.0]),
        )
        result = _propagate_source_availability(merged)
        assert bool(result["data_unavailable"].iloc[0]) is False
        assert result["reason"].iloc[0] is None

    def test_roc_overflow_marker_row_propagates_unavailable(self):
        merged = _build_merged(
            source_data_unavailable=pd.Series([True]),
            source_reason=pd.Series(["roc_overflow_skip:extreme_volatility_exceeds_numeric_range"]),
        )
        result = _propagate_source_availability(merged)
        assert bool(result["data_unavailable"].iloc[0]) is True
        assert result["reason"].iloc[0] == "roc_overflow_skip:extreme_volatility_exceeds_numeric_range"

    def test_missing_source_flag_defaults_to_available(self):
        merged = _build_merged(source_data_unavailable=pd.Series([np.nan]))
        result = _propagate_source_availability(merged)
        assert bool(result["data_unavailable"].iloc[0]) is False

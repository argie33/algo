"""Regression test for a real-money-readiness scoring bug (2026-09-10, fresh field-by-field
Quality pillar re-audit): update_quality_sector_neutral_scores() (loaders/helpers/
vqg_quality_batch.py) unconditionally overwrote quality_score for every row with
total_weight > 0, with no floor - unlike Pass-1's _compute_quality_composite_score()
(loaders/helpers/vqg_quality_score.py), which withholds a score (min_quality_weight_pct=40.0
of the nominal 100-point composite) when too few components are available, precisely to stop
a 1-2 component thin sample extrapolating to a false 0-100 score.

Because this batch pass is documented as "the sole authoritative source of quality_score"
(it unconditionally overwrites Pass-1's value), a symbol whose available weight here falls
below 40 got a fully-extrapolated score anyway, silently discarding Pass-1's more
conservative (possibly withheld) value. Fixed by porting the same 40.0 floor into this
pass's per-symbol loop: below it, skip the write entirely (leave whatever score already
exists untouched), matching the existing total_weight<=0 skip.

UNIFORM EQUAL-WEIGHT 2026-09-11 (see loaders/stock_scores/pillar_weights.py's
BASE_PILLAR_WEIGHTS comment): all 8 components are now flat 12.5 each, so clearing the 40.0
floor requires at least 4 of the 8 components (4 x 12.5 = 50.0) rather than the old
magnitude-tuned combinations.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx,
        patch("loaders.load_value_quality_growth_metrics.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_quality_sector_neutral_scores()
    if not mock_execute_values.called:
        return []
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return list(updates)


class TestQualityBatchMinWeightFloor:
    def test_below_40pct_available_weight_produces_no_update(self) -> None:
        """Only fcf_margin present (weight 15 of 101 = 14.9%, well below the 40.0 floor) -
        must NOT be extrapolated to a full 0-100 score; the row must be skipped entirely,
        leaving any prior quality_score value untouched."""
        row = ("THIN", "Technology", None, None, None, None, 20.0, None, None, None, None, 33.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert "THIN" not in updates

    def test_exactly_at_40pct_available_weight_produces_no_update(self) -> None:
        """roce + d2e = 2 x 12.5 = 25 < 40 under equal weighting - still skipped (only 3 of 8
        components, 37.5, would also still fall short; 4 are needed to clear the floor)."""
        row = ("BOUNDARY_UNDER", "Technology", None, None, None, 20.0, None, 0.5, None, None, None, 33.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert "BOUNDARY_UNDER" not in updates

    def test_above_40pct_available_weight_still_updates(self) -> None:
        """roce + fcf_margin + d2e + margin_volatility = 4 x 12.5 = 50 >= 40 - clears the
        floor, update fires (3 components alone, 37.5, no longer clears it under equal
        weighting - see test_missing_metrics_below_new_equal_weight_floor_produces_no_update
        in test_quality_roe_roce_percentile_ranking_20260828.py for that boundary case)."""
        row = ("ENOUGH", "Technology", None, None, None, 20.0, 12.0, 0.5, 10.0, None, None, 33.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert "ENOUGH" in updates

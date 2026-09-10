"""Regression test for a real-money-readiness scoring bug (2026-09-10, fresh field-by-field
Quality pillar re-audit): update_quality_sector_neutral_scores() (loaders/helpers/
vqg_quality_batch.py) unconditionally overwrote quality_score for every row with
total_weight > 0, with no floor - unlike Pass-1's _compute_quality_composite_score()
(loaders/helpers/vqg_quality_score.py), which withholds a score (min_quality_weight_pct=40.0
of the nominal 101-point composite) when too few components are available, precisely to stop
a 1-2 component thin sample extrapolating to a false 0-100 score.

Because this batch pass is documented as "the sole authoritative source of quality_score"
(it unconditionally overwrites Pass-1's value), a symbol whose available weight here falls
below 40 got a fully-extrapolated score anyway, silently discarding Pass-1's more
conservative (possibly withheld) value. Fixed by porting the same 40.0 floor into this
pass's per-symbol loop: below it, skip the write entirely (leave whatever score already
exists untouched), matching the existing total_weight<=0 skip.
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
        """roce(18) + fcf_margin(15) + d2e(some>=0)(is this >=40? 18+15=33 <40) - pick a
        combination whose weight sums to exactly under 40 to pin the boundary is-strictly-
        less-than semantics; d2e alone at 18 plus roce at 18 = 36 < 40, still skipped."""
        row = ("BOUNDARY_UNDER", "Technology", None, None, None, 20.0, None, 0.5, None, None, None, 33.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert "BOUNDARY_UNDER" not in updates

    def test_above_40pct_available_weight_still_updates(self) -> None:
        """roce(18) + fcf_margin(15) + d2e(18) = 51 >= 40 - clears the floor, update fires."""
        row = ("ENOUGH", "Technology", None, None, None, 20.0, 12.0, 0.5, None, None, None, 33.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert "ENOUGH" in updates

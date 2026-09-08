"""Tests for ValueQualityGrowthMetricsLoader.update_quality_sector_neutral_scores() and its
supporting _margin_curve (loaders/load_value_quality_growth_metrics.py).

REWRITE 2026-09-07 ("best and brightest" scoring-methodology directive): this pass moved from
ROE/ROCE-only cross-sectional percentile ranking (Financial Services/Real Estate/Utilities
excluded) to sector-neutral z-scoring of all 8 Quality sub-metrics, all sectors, via
loaders/helpers/factor_normalization.py's sector_neutral_zscore()/zscore_to_percentile_scale()
(that module has its own dedicated unit tests -
tests/unit/test_factor_normalization_sector_neutral_zscore_20260907.py - covering the core
winsorize/z-score/residual-pool numerics in isolation). These tests instead pin the
RECONCILIATION arithmetic end to end: does update_quality_sector_neutral_scores() wire the raw
columns into the right z-score pools, apply the sign-flip guard, and apply the negative-value
floors and component weights correctly.

`_percent_rank_higher_is_better` (the old ROE/ROCE-only universe-wide percentile helper this
method used before the rewrite) no longer has any caller and was deleted along with its tests
here.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


class TestMarginCurveStillUsedByPass1:
    """_margin_curve is now Pass-1-only (PROVISIONAL scoring in vqg_quality.py, always
    overwritten by update_quality_sector_neutral_scores) - still pinned here since this file
    owns the shared definition."""

    def test_roe_breakpoints(self) -> None:
        assert L._margin_curve(10.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 50.0
        assert L._margin_curve(20.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 85.0
        assert L._margin_curve(40.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 100.0
        assert L._margin_curve(151.91, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 100.0

    def test_roce_breakpoints(self) -> None:
        assert L._margin_curve(8.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]) == 40.0
        assert L._margin_curve(25.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]) == 100.0

    def test_negative_value_floors_at_zero(self) -> None:
        assert L._margin_curve(-5.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)]) == 0.0


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx,
        patch("loaders.load_value_quality_growth_metrics.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)  # bypass __init__, this method has no instance state dependency
        loader.update_quality_sector_neutral_scores()
    if not mock_execute_values.called:
        return []
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return list(updates)


class TestUpdateQualitySectorNeutralScoresReconciliation:
    """End-to-end test against a fully mocked DB. Row shape:
    (symbol, sector, roe, roa, roce_pct, fcf_margin, debt_to_equity, margin_volatility,
     asset_turnover, gross_profitability, quality_score_old).

    Every case here uses a sector with fewer than sector_neutral_zscore's min_sector_size=15
    members, so each metric pools into ONE shared residual group across all rows in the test
    (see factor_normalization.py's own residual-pool fallback) rather than being sector-split -
    deliberate, so the z-score arithmetic stays hand-verifiable without needing 15+ rows.
    """

    def test_single_symbol_all_8_components_reconciles_to_neutral_50(self) -> None:
        # A lone symbol, no peers anywhere: every metric's pool has exactly 1 member, so
        # sector_neutral_zscore's z-score is 0.0 for lack of anything to compare against ->
        # zscore_to_percentile_scale maps that to the neutral 50.0 for every component.
        row = ("ONLY", "Technology", 15.0, 10.0, 12.0, 8.0, 0.5, 10.0, 60.0, 20.0, 0.0)
        updates = dict(_run_with_mocked_rows([row]))
        assert updates["ONLY"] == 50.0

    def test_negative_metrics_floor_to_zero_not_zscored(self) -> None:
        # roe/roa/roce/fcf_margin/asset_turnover/gross_profitability/debt_to_equity all
        # negative - each floors to 0.0 directly (the "if value < 0: floor" convention this
        # pass preserves from Pass 1's _margin_curve), never entering the z-score population.
        # margin_volatility=10.0 (>=0, no floor case) is alone in its pool -> neutral 50.0.
        row = ("NEG", "Technology", -1.0, -1.0, -1.0, -1.0, -1.0, 10.0, -1.0, -1.0, 999.0)
        updates = dict(_run_with_mocked_rows([row]))
        components = [
            (0.0, 11.0),  # roe: sign-flip-guard floor (roe<0 and roa<0)
            (0.0, 18.0),  # roa
            (0.0, 18.0),  # roce
            (0.0, 15.0),  # fcf_margin
            (0.0, 18.0),  # debt_to_equity: negative = real distress, floored
            (50.0, 7.0),  # margin_volatility: not floored, z-scores to neutral
            (0.0, 7.0),  # asset_turnover
            (0.0, 7.0),  # gross_profitability
        ]
        expected = round(
            sum(v * w for v, w in components) / sum(w for _, w in components),
            2,
        )
        assert updates["NEG"] == expected

    def test_missing_metrics_omitted_not_defaulted(self) -> None:
        # Only fcf_margin present - every other component's weight must be excluded from the
        # denominator entirely, not defaulted to 0 and diluting the average.
        row = ("SPARSE", "Technology", None, None, None, 20.0, None, None, None, None, 0.0)
        updates = dict(_run_with_mocked_rows([row]))
        # fcf_margin=20.0 alone in its pool -> z-scores to neutral -> percentile 50.0, weight
        # 15 is the ENTIRE denominator, so the composite equals it exactly.
        assert updates["SPARSE"] == 50.0

    def test_all_components_missing_produces_no_update(self) -> None:
        row = ("EMPTY", "Technology", None, None, None, None, None, None, None, None, 0.0)
        assert _run_with_mocked_rows([row]) == []

    def test_score_unchanged_produces_no_write(self) -> None:
        # Same shape as the lone-symbol case above, but quality_score_old already matches the
        # recomputed 50.0 - no write should be issued (this pass never rewrites a row whose
        # recomputed score is identical, to avoid needless updated_at churn every run).
        row = ("SAME", "Technology", 15.0, 10.0, 12.0, 8.0, 0.5, 10.0, 60.0, 20.0, 50.0)
        assert _run_with_mocked_rows([row]) == []

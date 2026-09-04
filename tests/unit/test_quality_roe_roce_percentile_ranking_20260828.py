"""Tests for ValueQualityGrowthMetricsLoader._percent_rank_higher_is_better and the
update_quality_roe_roce_percentiles() reconciliation math (loaders/load_value_quality_growth_metrics.py).

Goal session 2026-08-28 (repo-wide "best and brightest" curve-vs-percentile sweep, following
Value's P/E/P/B/P/S and Size's market_cap switches): ROE and ROCE were the only 2 of Quality's
8 components to show a cross-sectional percentile improvement consistent across the full sample
and both half-split eras (see algo/research/all_pillars_curve_vs_percentile_sweep_20260828.py).
These tests pin the percentile helper and the reconciliation arithmetic in isolation, with
fully-known inputs/outputs - a live DB spot-check during implementation found an unexplained
~0.6-1pt discrepancy between a from-scratch recompute and the actual corrected value, which these
tests are partly designed to help isolate (does the SHIPPED reconciliation function match its own
documented formula, independent of what any real symbol's pre-correction value happened to be).
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


class TestPercentRankHigherIsBetter:
    def test_empty_input_returns_empty(self) -> None:
        assert L._percent_rank_higher_is_better({}) == {}

    def test_single_symbol_gets_midpoint(self) -> None:
        assert L._percent_rank_higher_is_better({"AAPL": 15.0}) == {"AAPL": 50.0}

    def test_highest_raw_value_gets_highest_percentile(self) -> None:
        result = L._percent_rank_higher_is_better({"LOW": 5.0, "MID": 15.0, "HIGH": 40.0})
        assert result["HIGH"] == 100.0
        assert result["MID"] == 50.0
        assert result["LOW"] == 0.0

    def test_ties_share_the_same_percentile(self) -> None:
        result = L._percent_rank_higher_is_better({"A": 10.0, "B": 10.0, "C": 20.0})
        assert result["A"] == result["B"]
        assert result["C"] > result["A"]

    def test_opposite_direction_from_percent_rank_cheap_high(self) -> None:
        # Sanity check this is NOT accidentally the same convention as
        # StockScoresLoader._percent_rank_cheap_high (which gives the LOWEST value the highest
        # percentile) - the exact sign-mixup class already caught once this session in Size's
        # own percentile reconciliation (since removed along with the rest of that pillar -
        # see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS).
        values = {"LOW": 1.0, "HIGH": 99.0}
        result = L._percent_rank_higher_is_better(values)
        assert result["HIGH"] > result["LOW"]


class TestReconciliationMarginCurveMatchesNestedOriginal:
    """_margin_curve must exactly match _compute_quality_metrics's nested
    _margin_curve (verbatim copy - verified against known ROE/ROCE breakpoint outputs)."""

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


class TestUpdateQualityRoeRocePercentilesReconciliation:
    """End-to-end test of update_quality_roe_roce_percentiles() against a fully mocked DB, with
    a hand-computable expected output - the only way to know FOR CERTAIN the shipped function's
    arithmetic is correct, independent of any real symbol's actual (unknowable after the fact)
    pre-correction value."""

    def test_single_symbol_all_8_components_reconciles_exactly(self) -> None:
        # One symbol, all 8 Quality components available, hand-computed expected quality_score.
        roe, roa, roce_pct, fcf_margin, d2e, margin_vol, asset_turnover, gross_profitability = (
            15.0,
            10.0,
            12.0,
            8.0,
            0.5,
            10.0,
            60.0,
            20.0,
        )
        # Old (curve-based) component scores, computed the exact same way _compute_quality_metrics
        # does (verified against TestReconciliationMarginCurveMatchesNestedOriginal above).
        roe_curve = L._margin_curve(roe, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_score = L._margin_curve(roa, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        roce_curve = L._margin_curve(roce_pct, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        fcf_score = L._margin_curve(fcf_margin, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (d2e / 2.0) * 100.0))
        mv_score = 100.0 - L._margin_curve(margin_vol, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
        at_score = L._margin_curve(asset_turnover, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
        gp_score = L._margin_curve(gross_profitability, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        quality_score_old = (
            roe_curve * 11
            + roa_score * 18
            + roce_curve * 18
            + fcf_score * 15
            + d2e_score * 18
            + mv_score * 7
            + at_score * 7
            + gp_score * 7
        ) / 101

        # Only 1 symbol in the universe -> percentile is 50.0 for both ROE and ROCE
        # (_percent_rank_higher_is_better's own single-symbol convention).
        roe_pct_new, roce_pct_new = 50.0, 50.0
        expected_delta = ((roe_pct_new * 11 + roce_pct_new * 18) - (roe_curve * 11 + roce_curve * 18)) / 101
        expected_quality_score_new = round(max(0.0, min(100.0, quality_score_old + expected_delta)), 2)

        mock_rows = [
            (
                "ONLY",
                quality_score_old,
                roe,
                roa,
                roce_pct,
                fcf_margin,
                d2e,
                margin_vol,
                asset_turnover,
                gross_profitability,
            )
        ]
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = mock_rows
        with (
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx,
            patch("loaders.load_value_quality_growth_metrics.execute_values") as mock_execute_values,
        ):
            mock_ctx.return_value.__enter__.return_value = mock_cur
            loader = L.__new__(L)  # bypass __init__, this method has no instance state dependency
            loader.update_quality_roe_roce_percentiles()

        if abs(expected_delta) < 1e-9:
            mock_execute_values.assert_not_called()
        else:
            mock_execute_values.assert_called_once()
            _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
            assert updates == [("ONLY", expected_quality_score_new)]

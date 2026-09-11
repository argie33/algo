"""Regression tests for the 2026-08-31 fix (goal session: "get all the data we need"
full-coverage audit) to what is now update_quality_sector_neutral_scores() (loaders/
load_value_quality_growth_metrics.py, renamed/generalized by the 2026-09-07 "best and
brightest" scoring-methodology rewrite - the idempotency/negative-floor properties this file
tests are unchanged by that rewrite).

Live-confirmed on the real local DB: this batch pass runs unconditionally on the WHOLE
scored universe every time the loader runs (regardless of --symbols scope), and its
original additive-delta design (`quality_score_NEW = quality_score_OLD + delta`, reading
quality_score_OLD from the SAME mutable column it writes to) is NOT idempotent - three
consecutive runs today with zero underlying data changes drifted a fixed sample of
symbols upward every time (e.g. AAPL 83.57 -> 86.69, AAPG 78.57 -> 87.30), because the
same delta gets re-added on top of the prior run's already-corrected value instead of
being computed fresh against a stable baseline. 1,567/5,110 symbols (30.7% of the scored
universe) were found stuck at EXACTLY quality_score=100.00 after ~3 days of this running
in the normal pipeline cadence - including companies with deeply negative ROA/ROE/ROCE
(e.g. GLIBK: ROE -18.31%, ROCE -11.99%, gross profitability -10.73%).

Separately: a negative raw ROE/ROCE is floored to curve-score 0.0 in Pass 1
(`_margin_curve`'s own `if value < 0: return 0.0`), but a plain percentile rank never
floors at 0 for a non-worst performer - live-confirmed ROE=-18.31% still ranked at the
31st percentile of the real universe. Fixed the same way
load_stock_scores.py's update_value_multiples_percentiles() already fixes this for
unprofitable P/E: rank only the non-negative population, floor negative-raw-value symbols
to percentile 0.0 explicitly.

Fix: this method is now a pure, idempotent function of the raw stored ratio columns
(matching load_stock_scores.py's update_rs_percentiles() pattern) - quality_score is only
ever a WRITE target, never also a read input, and ROE/ROCE percentiles are floored to 0.0
for negative raw values.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _run_with_mocked_rows(rows: list[tuple]) -> list[tuple[str, float]]:
    """Run update_quality_roe_roce_percentiles() against a fully mocked DB returning `rows`
    for both the SELECT and any subsequent call (simulating the SAME DB state persisting
    across the run, i.e. a single pass), and return the UPDATE's (symbol, quality_score)
    pairs, or [] if no UPDATE was issued."""
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


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """The defining symptom of the bug: feed the function's OWN prior output back in as
        `quality_score` (simulating a second consecutive run with zero underlying data
        change) and it must NOT drift further - a fixed point, not a ratchet."""
        # Two symbols so z-scores aren't the single-symbol neutral-50.0 special case.
        # quality_score placeholder
        row_a = ("A", "Technology", None, 20.0, 10.0, 15.0, 8.0, 0.5, 10.0, 60.0, 20.0, 999.0)
        row_b = ("B", "Technology", None, -18.31, -1.68, -11.99, -5.29, 0.0, 0.87, 97.03, None, 999.0)

        first_pass_updates = _run_with_mocked_rows([row_a, row_b])
        assert first_pass_updates, "expected the first pass to correct the placeholder quality_score"
        corrected = dict(first_pass_updates)

        row_a_2 = ("A", "Technology", None, 20.0, 10.0, 15.0, 8.0, 0.5, 10.0, 60.0, 20.0, corrected["A"])
        row_b_2 = ("B", "Technology", None, -18.31, -1.68, -11.99, -5.29, 0.0, 0.87, 97.03, None, corrected["B"])
        second_pass_updates = _run_with_mocked_rows([row_a_2, row_b_2])

        assert second_pass_updates == [], (
            "re-running with unchanged raw inputs and the prior run's own output must not "
            f"change quality_score again (got {second_pass_updates}) - this is the exact "
            "non-idempotence/compounding bug this fix closes"
        )

    def test_three_consecutive_runs_converge_not_drift(self) -> None:
        """Broader sanity check across more symbols, including a negative-ROE/ROCE one -
        three passes in a row must reach a fixed point by pass 2, never keep moving."""
        rows = [
            ("POS", "Technology", None, 25.0, 12.0, 18.0, 10.0, 0.3, 5.0, 80.0, 30.0, 999.0),
            ("NEG", "Technology", None, -30.0, -10.0, -20.0, -15.0, 1.0, 20.0, 40.0, -5.0, 999.0),
            ("MIX", "Technology", None, 5.0, 3.0, -2.0, 2.0, 0.8, 15.0, 55.0, 12.0, 999.0),
        ]

        def _next_pass_rows(prior_rows: list[tuple], prior_updates: dict[str, float]) -> list[tuple]:
            return [(r[0], *r[1:11], prior_updates.get(r[0], r[11])) for r in prior_rows]

        pass1 = dict(_run_with_mocked_rows(rows))
        rows_after_1 = _next_pass_rows(rows, pass1)
        pass2 = dict(_run_with_mocked_rows(rows_after_1))
        rows_after_2 = _next_pass_rows(rows_after_1, pass2)
        pass3_updates = _run_with_mocked_rows(rows_after_2)

        assert pass3_updates == [], f"score kept drifting on a 3rd identical pass: {pass3_updates}"


class TestNegativeRoeRoceFloor:
    def test_deeply_negative_roe_and_roce_does_not_inflate_quality_score(self) -> None:
        """GLIBK-shaped case: ROE/ROCE both deeply negative alongside otherwise-mediocre
        inputs must NOT land anywhere near 100 - the exact live-observed failure mode."""
        rows = [
            # a genuinely strong peer
            ("GOOD", "Technology", None, 25.0, 15.0, 20.0, 12.0, 0.2, 3.0, 90.0, 35.0, 0.0),
            ("GLIBK", "Technology", None, -18.31, -9.55, -11.99, 11.66, 0.72, None, 32.34, -10.73, 0.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        assert "GLIBK" in updates
        assert updates["GLIBK"] < 60.0, (
            f"a company with negative ROE/ROCE/gross-profitability scored {updates['GLIBK']}, "
            "expected well below a mediocre-quality threshold"
        )

    def test_negative_roe_contributes_zero_not_a_lenient_percentile(self) -> None:
        """Direct unit-level check: a negative-ROE symbol's ROE term must compute as if it
        were curve-scored at 0, not ranked among the (non-negative-only) percentile universe -
        verified by comparing two universes where the only difference is whether a very-bad
        (but not literally most-negative) ROE symbol would otherwise rank favorably.

        The 2026-09-07 sign-flip-distress fix (see
        test_quality_roe_sign_flip_distress_artifact_excluded_20260907.py) made the ROE
        component require `roa` to be present at all (omitted, not floored, when roa is
        missing). Both rows below now also set a negative `roa` (consistent with the
        deeply-negative-ROE distress shape this test is modeling) so the ROE component is
        actually included and its floor-at-0-for-negative-values behavior gets exercised,
        instead of being omitted entirely (total_weight=0, no update issued).

        Both rows also carry identical margin_volatility/asset_turnover/gross_profitability
        values (weight 5 x 12.5 = 62.5 under equal weighting - 2026-09-11, see
        pillar_weights.py's BASE_PILLAR_WEIGHTS comment - clears the 40.0 completeness floor)
        so an update actually fires - with matching values across both rows, those three
        components pool as ties and z-score to neutral percentile 50.0 for both symbols, so
        the ROE/ROA floor-to-0 behavior is still the only thing distinguishing the composite
        from a plain neutral score."""
        rows = [
            ("WORST_NEG", "Technology", None, -40.0, -30.0, None, None, None, 10.0, 50.0, 25.0, 99.0),
            ("MID_NEG", "Technology", None, -5.0, -3.0, None, None, None, 10.0, 50.0, 25.0, 99.0),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        # Both symbols: ROE and ROA (both weight 12.5 each under equal weighting) both
        # negative, both floored to 0; margin_volatility/asset_turnover/gross_profitability
        # (weight 12.5 each, tied between the two rows) all z-score to neutral 50.0.
        # Composite = (0*12.5 + 0*12.5 + 50*12.5*3) / 62.5.
        expected = round((50.0 * 12.5 * 3) / 62.5, 2)
        assert updates.get("WORST_NEG") == expected
        assert updates.get("MID_NEG") == expected

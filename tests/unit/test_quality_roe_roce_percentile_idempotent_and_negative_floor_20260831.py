"""Regression tests for the 2026-08-31 fix (goal session: "get all the data we need"
full-coverage audit) to update_quality_roe_roce_percentiles() (loaders/
load_value_quality_growth_metrics.py).

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
        loader.update_quality_roe_roce_percentiles()
    if not mock_execute_values.called:
        return []
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return list(updates)


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """The defining symptom of the bug: feed the function's OWN prior output back in as
        `quality_score` (simulating a second consecutive run with zero underlying data
        change) and it must NOT drift further - a fixed point, not a ratchet."""
        # Two symbols so percentiles aren't the single-symbol 50.0 special case.
        row_a = ("A", 999.0, 20.0, 10.0, 15.0, 8.0, 0.5, 10.0, 60.0, 20.0)  # quality_score placeholder
        row_b = ("B", 999.0, -18.31, -1.68, -11.99, -5.29, 0.0, 0.87, 97.03, None)

        first_pass_updates = _run_with_mocked_rows([row_a, row_b])
        assert first_pass_updates, "expected the first pass to correct the placeholder quality_score"
        corrected = dict(first_pass_updates)

        row_a_2 = ("A", corrected["A"], 20.0, 10.0, 15.0, 8.0, 0.5, 10.0, 60.0, 20.0)
        row_b_2 = ("B", corrected["B"], -18.31, -1.68, -11.99, -5.29, 0.0, 0.87, 97.03, None)
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
            ("POS", 999.0, 25.0, 12.0, 18.0, 10.0, 0.3, 5.0, 80.0, 30.0),
            ("NEG", 999.0, -30.0, -10.0, -20.0, -15.0, 1.0, 20.0, 40.0, -5.0),
            ("MIX", 999.0, 5.0, 3.0, -2.0, 2.0, 0.8, 15.0, 55.0, 12.0),
        ]

        pass1 = dict(_run_with_mocked_rows(rows))
        rows_after_1 = [(sym, pass1.get(sym, r[1]), *r[2:]) for sym, r in zip([r[0] for r in rows], rows, strict=True)]
        pass2 = dict(_run_with_mocked_rows(rows_after_1))
        rows_after_2 = [
            (sym, pass2.get(sym, r[1]), *r[2:])
            for sym, r in zip([r[0] for r in rows_after_1], rows_after_1, strict=True)
        ]
        pass3_updates = _run_with_mocked_rows(rows_after_2)

        assert pass3_updates == [], f"score kept drifting on a 3rd identical pass: {pass3_updates}"


class TestNegativeRoeRoceFloor:
    def test_deeply_negative_roe_and_roce_does_not_inflate_quality_score(self) -> None:
        """GLIBK-shaped case: ROE/ROCE both deeply negative alongside otherwise-mediocre
        inputs must NOT land anywhere near 100 - the exact live-observed failure mode."""
        rows = [
            ("GOOD", 0.0, 25.0, 15.0, 20.0, 12.0, 0.2, 3.0, 90.0, 35.0),  # a genuinely strong peer
            ("GLIBK", 0.0, -18.31, -9.55, -11.99, 11.66, 0.72, None, 32.34, -10.73),
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
        (but not literally most-negative) ROE symbol would otherwise rank favorably."""
        # Without the floor, "MID_NEG" (-5%) would rank above "WORST_NEG" (-40%) at ~50th
        # percentile of an all-negative universe - a clearly wrong "relatively fine" signal
        # for a lossmaking company. With the floor, both contribute exactly 0 for the ROE term.
        rows = [
            ("WORST_NEG", 99.0, -40.0, None, None, None, None, None, None, None),
            ("MID_NEG", 99.0, -5.0, None, None, None, None, None, None, None),
        ]
        updates = dict(_run_with_mocked_rows(rows))
        # Both symbols' ONLY component is ROE (weight 11) - floored to 0 for both -> quality_score 0.0.
        assert updates.get("WORST_NEG") == 0.0
        assert updates.get("MID_NEG") == 0.0

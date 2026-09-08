"""Regression tests for the 2026-08-31 fix (goal session: "VCIG tops the scores and it's a
shitty stock, dig in") to update_value_multiples_percentiles() (loaders/load_stock_scores.py).

Live-confirmed on the real local DB: this batch pass runs unconditionally on the WHOLE scored
universe every time the loader's post_run() runs (regardless of --symbols scope), and its
original additive-delta design (`value_score_NEW = value_score_OLD + delta`, reading
value_score_OLD from the SAME mutable column it writes to) was NOT idempotent - two consecutive
live calls today with zero underlying pe/pb/ps/forward_pe changes drifted a fixed sample of
symbols by the SAME delta each time (TAP.A 89.69 -> 83.70 -> 77.71, CMCT 81.84 -> 81.66 -> 81.48),
because the same delta gets re-added on top of the prior call's already-corrected value instead
of being computed fresh against a stable baseline. Several real tickers (BMA - a large Argentine
bank, CISS, VCIG) were already pinned at the 0/100 clamp in this same test, consistent with this
mechanism having run repeatedly in the normal pipeline cadence. This mirrors the exact same bug
class just found and fixed in loaders/load_value_quality_growth_metrics.py's
update_quality_roe_roce_percentiles() (see that fix's own "BUG FOUND + FIXED 2026-08-31" note and
its sibling test file, test_quality_roe_roce_percentile_idempotent_and_negative_floor_20260831.py,
which this test file mirrors).

Fix: update_value_multiples_percentiles() is now a pure, idempotent function of the raw stored
ratio/pillar columns (matching load_stock_scores.py's own update_rs_percentiles() pattern) -
value_score and composite_score are only ever WRITE targets here, never also read inputs.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(
    symbol: str,
    value_score: float,
    composite_score: float,
    risk_score: float | None,
    quality_score: float | None,
    growth_score: float | None,
    momentum_score: float | None,
    pe: float | None,
    pb: float | None,
    ps: float | None,
    fwd_pe: float | None,
    dividend_yield: float | None,
    pe_reason: str | None = None,
    fwd_pe_reason: str | None = None,
    components: dict | None = None,
    sector: str | None = None,
    data_completeness: float | None = 99.99,
    data_unavailable: bool = False,
    unavailable_metrics: dict | None = None,
) -> tuple:
    return (
        symbol,
        value_score,
        composite_score,
        risk_score,
        quality_score,
        growth_score,
        momentum_score,
        pe,
        pb,
        ps,
        fwd_pe,
        dividend_yield,
        pe_reason,
        fwd_pe_reason,
        components if components is not None else {},
        sector,
        data_completeness,
        data_unavailable,
        unavailable_metrics if unavailable_metrics is not None else {},
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float, float]]:
    """Run update_value_multiples_percentiles() against a fully mocked DB returning `rows` for
    the SELECT, and return {symbol: (value_score, composite_score)} from the UPDATE, or {} if
    no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_value_multiples_percentiles()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """The defining symptom of the bug: feed the function's OWN prior output back in as
        value_score/composite_score (simulating a second consecutive run with zero underlying
        data change) and it must NOT drift further - a fixed point, not a ratchet."""
        # Several symbols with distinct pe/pb/ps so percentiles aren't all tied at 50.0.
        rows = [
            _row("CHEAP", 999.0, 999.0, 40.0, 70.0, 60.0, 55.0, 5.0, 0.5, 1.0, None, None),
            _row("MID", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, 18.0, 2.5, 4.0, None, 0.01),
            _row("EXPENSIVE", 999.0, 999.0, 60.0, 40.0, 45.0, 45.0, 60.0, 8.0, 12.0, None, None),
        ]

        first_pass = _run_with_mocked_rows(rows)
        assert first_pass, "expected the first pass to correct the placeholder value_score"

        rows_after_1 = [
            _row(
                r[0],
                first_pass.get(r[0], (r[1], r[2]))[0],
                first_pass.get(r[0], (r[1], r[2]))[1],
                r[3],
                r[4],
                r[5],
                r[6],
                r[7],
                r[8],
                r[9],
                r[10],
                r[11],
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not "
            f"change value_score/composite_score again (got {second_pass}) - this is the exact "
            "non-idempotence/compounding bug this fix closes"
        )

    def test_three_consecutive_runs_converge_not_drift(self) -> None:
        """Broader sanity check across more symbols - three passes in a row must reach a fixed
        point by pass 2, never keep moving (the live-observed TAP.A/CMCT symptom)."""
        rows = [
            _row("A", 999.0, 999.0, 45.0, 55.0, 50.0, 50.0, 24.1, 5.98, 7.25, 17.04, 0.0037),
            _row("B", 999.0, 999.0, 55.0, 60.0, 45.0, 40.0, 9.0, 1.2, 0.8, 11.0, None),
            _row("C", 999.0, 999.0, 35.0, 40.0, 35.0, 30.0, 0.01, 0.01, 0.02, None, 0.0),
        ]

        def _apply(rows_in: list[tuple], corrections: dict[str, tuple[float, float]]) -> list[tuple]:
            return [
                _row(
                    r[0],
                    corrections.get(r[0], (r[1], r[2]))[0],
                    corrections.get(r[0], (r[1], r[2]))[1],
                    r[3],
                    r[4],
                    r[5],
                    r[6],
                    r[7],
                    r[8],
                    r[9],
                    r[10],
                    r[11],
                )
                for r in rows_in
            ]

        pass1 = _run_with_mocked_rows(rows)
        rows_after_1 = _apply(rows, pass1)
        pass2 = _run_with_mocked_rows(rows_after_1)
        rows_after_2 = _apply(rows_after_1, pass2)
        pass3 = _run_with_mocked_rows(rows_after_2)

        assert pass3 == {}, f"score kept drifting on a 3rd identical pass: {pass3}"


class TestNoWinsorizationOutlierDomination:
    """NOTE-only test: documents (does not fix - see update_value_multiples_percentiles()'s own
    "NOTE (separate, NOT fixed by this pass)" docstring) that a single universe-extreme raw
    ratio still wins percentile 100/0 outright, same as the live VCIG/BMA behavior."""

    def test_single_most_extreme_raw_ratio_wins_top_percentile_outright(self) -> None:
        result = L._percent_rank_cheap_high({"EXTREME": 0.0001, "NORMAL_A": 1.0, "NORMAL_B": 2.0})
        assert result["EXTREME"] == 100.0

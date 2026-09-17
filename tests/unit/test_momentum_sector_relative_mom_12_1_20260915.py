"""Tests for update_momentum_sector_relative_mom_12_1() (loaders/stock_scores/momentum_scoring.py).

AQR MOMENTUM PIVOT (2026-09-17, /goal directive: "moving away from the msci and towards the aqr
for the factors"). REWRITTEN this pass: the method dropped mom_6m and the MSCI-style
risk-adjustment/risk-free-netting machinery entirely - AQR's momentum factor (Asness, Moskowitz &
Pedersen 2013, "Value and Momentum Everywhere") is a single RAW 12-1 skip-month return, universe-
wide z-scored, weight 1.0. volatility_252d/sector/is_foreign_private_issuer/momentum_6m are no
longer selected by the query at all (they only ever fed the now-removed risk-adjustment/sector
paths), so mocked rows are 12 columns, not 16. The method's name (`..._sector_relative_...`) is
stale relative to what it does - left unchanged to avoid touching every call site in the same
commit as this scoring-logic fix; a rename is a separate, lower-risk follow-up.

Test structure still mirrors tests/unit/test_growth_sector_neutral_scores_20260908.py's mocked-
DB-row / idempotency-across-repeated-runs pattern, since this method is still built on the
identical "Pass 1 provisional, batch pass fully recomputes and overwrites" architecture.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(
    symbol: str,
    momentum_score: float,
    composite_score: float,
    quality_score: float | None,
    growth_score: float | None,
    value_score: float | None,
    risk_score: float | None,
    components: dict | None,
    data_completeness: float | None,
    data_unavailable: bool,
    momentum_1m: float | None,
    momentum_12m: float | None,
) -> tuple:
    """Build a mocked SELECT row matching update_momentum_sector_relative_mom_12_1()'s own
    column order exactly: symbol, momentum_score, composite_score, quality_score, growth_score,
    value_score, risk_score, components, data_completeness, data_unavailable, momentum_1m,
    momentum_12m. Nothing else is selected - momentum_6m/volatility_252d/sector/
    is_foreign_private_issuer/rsi_14/macd/sma_50/sma_200/close/momentum_3m are all gone from the
    query (AQR MOMENTUM PIVOT removed the risk-adjustment/sector paths that used them)."""
    return (
        symbol,
        momentum_score,
        composite_score,
        quality_score,
        growth_score,
        value_score,
        risk_score,
        components if components is not None else {},
        data_completeness,
        data_unavailable,
        momentum_1m,
        momentum_12m,
    )


def _full_row(symbol: str, mom_12m: float, mom_1m: float = 0.0) -> tuple:
    """A row with mom_12_1 scoreable, varying momentum_12m (the dominant driver of mom_12_1 when
    momentum_1m is held near zero)."""
    return _row(symbol, 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, mom_1m, mom_12m)


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_momentum_sector_relative_mom_12_1() against a fully mocked DB returning `rows`
    for the SELECT, and return {symbol: (momentum_score, composite_score)} from the UPDATE, or
    {} if no UPDATE was issued.

    `_withhold_momentum_below_floor` (a separate query/method entirely - see its own docstring)
    is stubbed to return [] here: these tests exercise the CORRECTION pass's own logic against a
    single mocked row shape, not the withhold companion's own (differently-shaped) query."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader._withhold_momentum_below_floor = list  # type: ignore[method-assign]
        loader.update_momentum_sector_relative_mom_12_1()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


class TestUniverseWideRanking:
    def test_stronger_12mo_return_scores_higher_than_weaker_peer(self) -> None:
        """Basic sanity: a higher raw momentum_12m must score higher than a lower one."""
        rows = [
            _full_row("STRONG", 60.0),
            _full_row("WEAK", -20.0),
            _full_row("MID_A", 0.0),
            _full_row("MID_B", 10.0),
            _full_row("MID_C", 25.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert (
            updates["STRONG"][0] > updates["MID_C"][0] > updates["MID_B"][0] > updates["MID_A"][0] > updates["WEAK"][0]
        )

    def test_same_absolute_return_scores_the_same_regardless_of_grouping(self) -> None:
        """mom_12_1 is universe-wide, not sector-relative (no sector column exists in the query
        at all any more) - two disjoint batches of symbols with the same raw 12mo return
        distribution must land on identical z-scores/percentiles once pooled into one run."""
        batch_a = [
            _full_row(f"A_{i}", v)
            for i, v in enumerate(
                [40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 20.0]
            )
        ]
        batch_b = [
            _full_row(f"B_{i}", v)
            for i, v in enumerate(
                [-30.0, -25.0, -20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0, 19.0, 20.0]
            )
        ]
        updates = _run_with_mocked_rows(batch_a + batch_b)
        # A_14 and B_14 both carry the identical raw momentum_12m = 20.0 - with universe-wide
        # z-scoring they're compared against the SAME pooled population, so they must land on
        # the identical score.
        assert updates["B_14"][0] == updates["A_14"][0], (
            f"B_14={updates['B_14'][0]} A_14={updates['A_14'][0]}: identical raw 12mo returns "
            "must score identically under universe-wide z-scoring."
        )


class TestMomentumMinWeightFloorPreserved:
    def test_thin_coverage_withheld_not_saturated(self) -> None:
        """MOMENTUM_MIN_WEIGHT=0.40: a symbol with mom_12_1 available (weight 1.0) scores, but a
        symbol with NOTHING available must be withheld (None), not silently dropped from the
        composite recompute as if it were fine."""
        rows = [
            _row(
                "NOTHING",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                None,  # momentum_1m missing -> mom_12_1 can't derive
                None,  # momentum_12m missing
            ),
            _full_row("PEER_A", 10.0),
            _full_row("PEER_B", 20.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "NOTHING" in updates
        assert updates["NOTHING"][0] is None, f"expected momentum_score withheld (None), got {updates['NOTHING'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class this repo already fixed for Value/Quality/Growth's
        batch passes - momentum_score/composite_score must never be read back as inputs to this
        pass, since the raw momentum_1m/12m inputs are what it's a pure function of."""
        rows = [
            _full_row("A", 25.0),
            _full_row("B", -5.0),
            _full_row("C", 60.0),
        ]

        first_pass = _run_with_mocked_rows(rows)
        assert first_pass, "expected the first pass to correct the placeholder momentum_score"

        rows_after_1 = [
            _row(
                r[0],
                first_pass[r[0]][0] if first_pass[r[0]][0] is not None else r[1],
                first_pass[r[0]][1],
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
            f"change momentum_score/composite_score again (got {second_pass})"
        )


class TestCompositeScoreRecomputed:
    def test_composite_score_reflects_new_momentum_score(self) -> None:
        """Composite recompute must use the NEW momentum_score, not the stale placeholder -
        same check as Growth/Value's own composite-recompute tests."""
        rows = [
            _full_row("A", 80.0),
            _full_row("B", -60.0),
        ]
        updates = _run_with_mocked_rows(rows)
        mom_a, comp_a = updates["A"]
        mom_b, comp_b = updates["B"]
        assert mom_a is not None and mom_b is not None
        assert mom_a > mom_b
        # A's stronger momentum_score must translate into a strictly higher composite_score
        # than B's (other pillars held identical at 50.0 in _full_row), not just be recomputed
        # in isolation and discarded.
        assert comp_a > comp_b

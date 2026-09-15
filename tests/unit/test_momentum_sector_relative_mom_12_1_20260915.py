"""Tests for update_momentum_sector_relative_mom_12_1() (loaders/stock_scores/momentum_scoring.py,
added 2026-09-15), the Momentum-pillar sibling of Quality/Growth/Value's own sector-neutral-zscore
batch passes.

Context: TWO-LAYER VALIDATION POLICY (pillar_weights.py, 2026-09-15, user directive) - pillar
constructions are validated against fidelity to the real institutional factor definition, not
their own standalone IC. MTUM's real underlying index (MSCI USA Momentum SR "Sector-Relative"
Variant) z-scores momentum WITHIN each GICS sector - this method applies that same transform to
mom_12_1 (45% of momentum_score), the one component with a real sourced sector-relative
precedent, leaving momentum_3m/tech_trend/sma_avg on their existing universe-wide/self-relative
constructions.

Test structure mirrors tests/unit/test_growth_sector_neutral_scores_20260908.py exactly (same
mocked-DB-row / idempotency-across-repeated-runs pattern), since this method is built on the
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
    momentum_3m: float | None,
    momentum_12m: float | None,
    rsi_14: float | None,
    macd: float | None,
    sma_50: float | None,
    sma_200: float | None,
    close: float | None,
    volatility_252d: float | None,
    sector: str | None,
    is_fpi: bool = False,
) -> tuple:
    """Build a mocked SELECT row matching update_momentum_sector_relative_mom_12_1()'s own
    column order exactly: symbol, momentum_score, composite_score, quality_score, growth_score,
    value_score, risk_score, components, data_completeness, data_unavailable, momentum_1m,
    momentum_3m, momentum_12m, rsi_14, macd, sma_50, sma_200, close, volatility_252d, sector,
    is_foreign_private_issuer."""
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
        momentum_3m,
        momentum_12m,
        rsi_14,
        macd,
        sma_50,
        sma_200,
        close,
        volatility_252d,
        sector,
        is_fpi,
    )


def _full_row(symbol: str, mom_12m: float, sector: str, mom_1m: float = 0.0) -> tuple:
    """A row with every input present (all 4 momentum_score slots scoreable), varying only
    momentum_12m (the dominant driver of mom_12_1 when momentum_1m is held near zero)."""
    return _row(
        symbol,
        999.0,
        999.0,
        50.0,
        50.0,
        50.0,
        50.0,
        {},
        99.99,
        False,
        mom_1m,
        5.0,
        mom_12m,
        55.0,
        1.0,
        105.0,
        102.0,
        110.0,
        0.30,
        sector,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_momentum_sector_relative_mom_12_1() against a fully mocked DB returning `rows`
    for the SELECT, and return {symbol: (momentum_score, composite_score)} from the UPDATE, or
    {} if no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_momentum_sector_relative_mom_12_1()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


class TestSectorRelativeRanking:
    def test_stronger_12mo_return_scores_higher_than_weaker_peer_same_sector(self) -> None:
        """Basic sanity: within the same sector, a higher raw momentum_12m (all else equal)
        must score higher than a lower one."""
        rows = [
            _full_row("STRONG", 60.0, "Technology"),
            _full_row("WEAK", -20.0, "Technology"),
            _full_row("MID_A", 0.0, "Technology"),
            _full_row("MID_B", 10.0, "Technology"),
            _full_row("MID_C", 25.0, "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        assert (
            updates["STRONG"][0] > updates["MID_C"][0] > updates["MID_B"][0] > updates["MID_A"][0] > updates["WEAK"][0]
        )

    def test_same_absolute_return_scores_differently_across_sectors(self) -> None:
        """The whole point of the rewrite: an IDENTICAL raw 12mo return should NOT map to the
        identical score once sector peer groups differ - a return that's mediocre for a
        hot-momentum sector should score lower than the SAME return in a cold sector. Energy
        peers here are uniformly much stronger than Utilities peers, so a shared raw return of
        20.0 should rank the Utilities symbol relatively higher."""
        energy_rows = [
            _full_row(f"NRG_{i}", v, "Energy")
            for i, v in enumerate(
                [40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0, 20.0]
            )
        ]
        util_rows = [
            _full_row(f"UTL_{i}", v, "Utilities")
            for i, v in enumerate(
                [-30.0, -25.0, -20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 12.0, 14.0, 16.0, 18.0, 19.0, 20.0]
            )
        ]
        updates = _run_with_mocked_rows(energy_rows + util_rows)
        # NRG_14 and UTL_14 both carry the identical raw momentum_12m = 20.0.
        assert updates["UTL_14"][0] > updates["NRG_14"][0], (
            f"UTL_14={updates['UTL_14'][0]} NRG_14={updates['NRG_14'][0]}: identical raw 12mo return "
            "should score higher relative to a cold (Utilities) peer group than a hot (Energy) one - "
            "this is the entire point of sector-relative z-scoring, and the exact pattern the live "
            "2026-09 energy/refiner momentum cluster showed under the old universe-wide construction"
        )


class TestMomentumMinWeightFloorPreserved:
    def test_thin_coverage_withheld_not_saturated(self) -> None:
        """MOMENTUM_MIN_WEIGHT=0.40: a symbol with only mom_12_1 available (0.45 weight is
        enough alone) still scores, but a symbol with NOTHING available must be withheld
        (None), not silently dropped from the composite recompute as if it were fine."""
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
                None,  # momentum_3m missing
                None,  # momentum_12m missing
                None,  # rsi_14 missing
                None,  # macd missing
                None,  # sma_50 missing
                None,  # sma_200 missing
                None,  # close missing
                None,
                "Technology",
            ),
            _full_row("PEER_A", 10.0, "Technology"),
            _full_row("PEER_B", 20.0, "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "NOTHING" in updates
        assert updates["NOTHING"][0] is None, f"expected momentum_score withheld (None), got {updates['NOTHING'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class this repo already fixed for Value/Quality/Growth's
        batch passes - momentum_score/composite_score must never be read back as inputs to this
        pass, since the raw momentum_1m/3m/12m/rsi/macd/sma/vol inputs are what it's a pure
        function of."""
        rows = [
            _full_row("A", 25.0, "Technology"),
            _full_row("B", -5.0, "Technology"),
            _full_row("C", 60.0, "Technology"),
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
                r[12],
                r[13],
                r[14],
                r[15],
                r[16],
                r[17],
                r[18],
                r[19],
                r[20],
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
            _full_row("A", 80.0, "Technology"),
            _full_row("B", -60.0, "Technology"),
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

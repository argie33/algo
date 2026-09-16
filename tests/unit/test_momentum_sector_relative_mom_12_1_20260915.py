"""Tests for update_momentum_sector_relative_mom_12_1() (loaders/stock_scores/momentum_scoring.py).

REWRITTEN 2026-09-15 (same day, later pass - user directive: "do what is needed so we get ours
like theirs", after live-verifying against fresh MTUM daily holdings). This method's name and
the original test file predate a same-day correction: sector-relative z-scoring of mom_12_1 was
based on a misread of MTUM's real methodology ("sector diversification" in MSCI's own published
language is a portfolio-construction-level exposure CAP, not a stock-scoring-level per-sector
z-score) - live-verified wrong via fresh MTUM daily holdings (cap-neutral Spearman rank
correlation 0.235 sector-relative vs 0.558 universe-wide for mom_12_1 alone). The method now
z-scores mom_12_1 AND mom_6m universe-wide (not per-sector) and blends them 50/50 - momentum_3m/
tech_trend/sma_avg are no longer scored at all (see momentum_scoring.py's own WEIGHTS REBALANCED
docstring note for the full evidence trail). The method's name (`..._sector_relative_...`) is
now stale relative to what it does - left unchanged in this pass to avoid touching every call
site across the codebase in the same commit as the scoring-logic fix; a rename is a separate,
lower-risk follow-up.

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
    volatility_252d: float | None,
    sector: str | None,
    is_fpi: bool = False,
    momentum_6m: float | None = None,
) -> tuple:
    """Build a mocked SELECT row matching update_momentum_sector_relative_mom_12_1()'s own
    column order exactly: symbol, momentum_score, composite_score, quality_score, growth_score,
    value_score, risk_score, components, data_completeness, data_unavailable, momentum_1m,
    momentum_12m, volatility_252d, sector, is_foreign_private_issuer, momentum_6m (appended as
    the trailing column, 2026-09-15). rsi_14/macd/sma_50/sma_200/close/momentum_3m were dropped
    from the query entirely (2026-09-16) - the recompute never scored them, only passed them
    through unused."""
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
        volatility_252d,
        sector,
        is_fpi,
        momentum_6m,
    )


def _full_row(symbol: str, mom_12m: float, sector: str, mom_1m: float = 0.0, mom_6m: float | None = None) -> tuple:
    """A row with every input present (both mom_12_1 and mom_6m slots scoreable), varying
    momentum_12m (the dominant driver of mom_12_1 when momentum_1m is held near zero).
    momentum_6m defaults to the same value as momentum_12m when not given, so tests that only
    care about the 12m-driven ordering aren't diluted by an independently-varying 6m input."""
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
        mom_12m,
        0.30,
        sector,
        momentum_6m=mom_6m if mom_6m is not None else mom_12m,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_momentum_sector_relative_mom_12_1() against a fully mocked DB returning `rows`
    for the SELECT, and return {symbol: (momentum_score, composite_score)} from the UPDATE, or
    {} if no UPDATE was issued.

    `_withhold_momentum_below_floor` (added 2026-09-15, a separate query/method entirely - see
    its own docstring) is stubbed to return [] here: these tests exercise the CORRECTION pass's
    own logic against a single mocked row shape, not the withhold companion's own (differently-
    shaped) query - see test_momentum_withhold_below_liquidity_floor_20260915.py for that."""
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
        """Basic sanity: a higher raw momentum_12m (all else equal, same sector so this isn't
        testing the sector question) must score higher than a lower one."""
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

    def test_same_absolute_return_scores_the_same_regardless_of_sector(self) -> None:
        """FIXED 2026-09-15 (was inverted before this rewrite - see module docstring): mom_12_1
        is now universe-wide, not sector-relative, matching MTUM's real construction (sector
        diversification there is a portfolio-CONSTRUCTION cap, not per-sector stock scoring).
        An IDENTICAL raw 12mo return (and identical mom_6m, held equal via _full_row's default)
        must map to the SAME score regardless of which sector's peer group it's compared
        against - the opposite property of what this test asserted before the fix."""
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
        # NRG_14 and UTL_14 both carry the identical raw momentum_12m = 20.0 (and, via
        # _full_row's default, identical momentum_6m = 20.0 too) - with universe-wide z-scoring
        # they're compared against the SAME population regardless of sector, so they must land
        # on the identical score now.
        assert updates["UTL_14"][0] == updates["NRG_14"][0], (
            f"UTL_14={updates['UTL_14'][0]} NRG_14={updates['NRG_14'][0]}: identical raw 12mo/6mo "
            "returns must score identically now that mom_12_1/mom_6m are universe-wide, not "
            "sector-relative - a sector-dependent split here would mean the sector-relative bug "
            "this same-day fix removed has regressed."
        )


class TestMomentumMinWeightFloorPreserved:
    def test_thin_coverage_withheld_not_saturated(self) -> None:
        """MOMENTUM_MIN_WEIGHT=0.40: a symbol with only mom_12_1 available (0.50 weight is
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
                None,  # momentum_12m missing
                None,  # volatility_252d
                "Technology",
                momentum_6m=None,  # momentum_6m missing too
            ),
            _full_row("PEER_A", 10.0, "Technology"),
            _full_row("PEER_B", 20.0, "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "NOTHING" in updates
        assert updates["NOTHING"][0] is None, f"expected momentum_score withheld (None), got {updates['NOTHING'][0]}"

    def test_only_mom_6m_available_still_scores(self) -> None:
        """Symmetric to the mom_12_1-only case: a symbol missing momentum_1m/12m (so mom_12_1
        can't derive) but with momentum_6m present should still score off that 0.50 weight
        alone, clearing MOMENTUM_MIN_WEIGHT=0.40."""
        rows = [
            _row(
                "ONLY_6M",
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
                None,  # momentum_12m missing -> mom_12_1 can't derive
                0.30,
                "Technology",
                momentum_6m=20.0,
            ),
            _full_row("PEER_A", 10.0, "Technology"),
            _full_row("PEER_B", 20.0, "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "ONLY_6M" in updates
        assert updates["ONLY_6M"][0] is not None, "expected a real score off mom_6m's 0.50 weight alone"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class this repo already fixed for Value/Quality/Growth's
        batch passes - momentum_score/composite_score must never be read back as inputs to this
        pass, since the raw momentum_1m/3m/6m/12m/rsi/macd/sma/vol inputs are what it's a pure
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
                momentum_6m=r[15],
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

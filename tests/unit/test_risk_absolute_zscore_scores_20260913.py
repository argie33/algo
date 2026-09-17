"""Tests for update_risk_absolute_zscore_scores() (loaders/stock_scores/risk_scoring.py, added
2026-09-13), the Risk-pillar sibling of Momentum/Growth/Value's own sector-neutral z-score
batch passes.

REVERSED 2026-09-13 (same day, composite-score structural audit): originally shipped
deliberately UNIVERSE-WIDE on the argument that the low-volatility anomaly is harvested on an
absolute basis in the literature. A fresh non-circular test that same session
(`algo/research/fama_macbeth_price_factors.py --industries banks|insurers|reits`) found zero
robust forward-return edge for vol/beta/max_dd in exactly the industries that argument was meant
to protect - see risk_scoring.py's own module docstring for the full evidence trail. This pass
is now SECTOR-RELATIVE, matching Quality/Growth/Value, via the same `sector_neutral_zscore`
primitive with a real symbol->sector map (a symbol with no sector, or in a sector below
`min_sector_size`, is pooled into one residual group and z-scored against that pool instead -
same fallback Value/Growth/Quality already use). Tests below that don't pass a `sector` to
`_row()` default to None, landing every such symbol in that residual pool - preserving their
original "no sector info at all" behavior unchanged.

Context: `_vol_curve_score`'s fixed breakpoints (0.15/0.30/0.60) were live-checked against the
real stability_metrics distribution and found badly miscalibrated (p50 volatility_60d=0.516,
already past the curve's OWN 0.30 breakpoint). This batch pass replaces it with
winsorize+z-score against the live universe.

MAX_DRAWDOWN_1Y REMOVED FROM SCORING 2026-09-16 (factor-purity sweep - see risk_scoring.py's
own module docstring): never a real Barra/MSCI risk descriptor, era-flipped sign with no
stable predictive power. TestMinTradingDaysForDrawdownGate (the old IPO-partial-history-
drawdown regression lock) and the drawdown-dependent assertions elsewhere in this file are
removed along with it - see git history if a future pass resurrects a drawdown-like input with
real evidence behind it. `_row()`'s `max_drawdown_1y`/`trading_days_history` params are kept
only because they still match the live SELECT's column order (harmless, unused by scoring).

Test structure mirrors tests/unit/test_momentum_sector_neutral_scores_20260913.py exactly (same
mocked-DB-row / idempotency-across-repeated-runs pattern), adapted for Risk's different fetch
shape (one SELECT, with trading_days_history instead of a second technical-data SELECT).
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(
    symbol: str,
    risk_score: float,
    composite_score: float,
    quality_score: float | None,
    growth_score: float | None,
    value_score: float | None,
    momentum_score: float | None,
    components: dict | None,
    data_completeness: float | None,
    data_unavailable: bool,
    volatility_60d: float | None,
    volatility_252d: float | None,
    beta: float | None,
    max_drawdown_1y: float | None,
    avg_dollar_volume_20d: float | None,
    trading_days_history: int,
    sector: str | None = None,
) -> tuple:
    """Build a mocked SELECT row matching update_risk_absolute_zscore_scores()'s own column
    order exactly: symbol, risk_score, composite_score, quality_score, growth_score, value_score,
    momentum_score, components, data_completeness, data_unavailable, volatility_60d,
    volatility_252d, beta, max_drawdown_1y, avg_dollar_volume_20d, trading_days_history, sector.
    `sector` defaults to None (pools into the residual group - see module docstring)."""
    return (
        symbol,
        risk_score,
        composite_score,
        quality_score,
        growth_score,
        value_score,
        momentum_score,
        components if components is not None else {},
        data_completeness,
        data_unavailable,
        volatility_60d,
        volatility_252d,
        beta,
        max_drawdown_1y,
        avg_dollar_volume_20d,
        trading_days_history,
        sector,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_risk_absolute_zscore_scores() against a fully mocked DB returning `rows` for
    the main SELECT, and return {symbol: (risk_score, composite_score)} from the UPDATE, or {}
    if no UPDATE was issued."""
    mock_cur = MagicMock()
    # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second is
    # _withhold_risk_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep) - []
    # means no symbol is below the liquidity floor in this test's fixture population.
    mock_cur.fetchall.side_effect = [rows, []]
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_risk_absolute_zscore_scores()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


LONG_HISTORY = (
    260  # trading_days_history value used throughout - no longer gates anything, kept for row-shape compatibility
)


class TestAbsoluteZScoreRanking:
    def test_lower_volatility_and_drawdown_score_higher(self) -> None:
        """Basic sanity: lower volatility_60d/252d and a smaller max_drawdown_1y magnitude must
        score higher than a peer with uniformly worse readings on all three."""

        def _rows_for(vol: float, dd: float) -> tuple:
            symbol = f"SYM_{vol}_{dd}"
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
                vol,
                vol * 1.1,
                1.0,
                -dd,
                5_000_000.0,
                LONG_HISTORY,
            )

        pairs = [(0.10, 5.0), (0.30, 15.0), (0.50, 30.0), (0.80, 50.0), (1.20, 70.0)]
        rows = [_rows_for(v, d) for v, d in pairs]
        updates = _run_with_mocked_rows(rows)
        ordered = [updates[f"SYM_{v}_{d}"][0] for v, d in pairs]
        assert ordered == sorted(ordered, reverse=True), f"expected strictly descending scores, got {ordered}"

    def test_no_sector_info_pools_into_one_residual_group(self) -> None:
        """Symbols with no sector (None, as when company_profile has no row) fall into
        `sector_neutral_zscore`'s residual pool and are z-scored against each other - identical
        raw inputs must still map to the IDENTICAL score in that shared residual group."""
        rows = [
            _row(
                "A",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.25,
                0.28,
                1.0,
                -12.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "B",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.25,
                0.28,
                1.0,
                -12.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "PEER1",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.60,
                0.65,
                1.0,
                -40.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "PEER2",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.10,
                0.12,
                1.0,
                -5.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["A"][0] == updates["B"][0], (
            f"identical raw inputs with no sector info must score identically in the residual pool - "
            f"A={updates['A'][0]} B={updates['B'][0]}"
        )

    def test_volatility_is_universe_wide_not_sector_relative(self) -> None:
        """LOCKS IN the 2026-09-15 partial re-reversal (see
        `_compute_risk_absolute_zscore_percentiles`'s own comment): volatility_60d/252d must
        score on ABSOLUTE magnitude across the whole universe, not relative to sector peers.
        Isolates volatility from drawdown/liquidity (both held identical across the two
        symbols, beta absent) so only the vol transform drives the score difference. A "calm
        for Tech" symbol (vol=0.35, genuinely elevated in absolute terms) must NOT out-score a
        "typical for Utilities" symbol (vol=0.20, genuinely lower in absolute terms) just
        because each is unremarkable within its own sector - the opposite of what
        test_sector_relative_scoring_matches_quality_growth_value_pattern intentionally still
        checks for max_drawdown_1y. Real motivation: a real min-vol fund (USMV, live N-PORT
        holdings fetched 2026-09-15) holds genuinely low-absolute-vol names across sectors, not
        "calmest within its own noisy sector" names - sector-neutral vol was elevating names
        like UBER (vol=0.41) over genuinely defensive DUK (vol=0.18)."""
        calm_for_tech = _row(
            "CALMTECH",
            999.0,
            999.0,
            50.0,
            50.0,
            50.0,
            50.0,
            {},
            99.99,
            False,
            0.35,
            0.35,
            None,
            None,
            5_000_000.0,
            LONG_HISTORY,
            sector="Technology",
        )
        typical_util = _row(
            "TYPUTIL",
            999.0,
            999.0,
            50.0,
            50.0,
            50.0,
            50.0,
            {},
            99.99,
            False,
            0.20,
            0.20,
            None,
            None,
            5_000_000.0,
            LONG_HISTORY,
            sector="Utilities",
        )
        # Pad each sector past min_sector_size=15 with genuinely worse Tech peers / genuinely
        # better Utilities peers, so a sector-relative transform (if one were still in play)
        # would make CALMTECH look good for its sector and TYPUTIL look mediocre for its own -
        # the opposite of the absolute ordering this test requires.
        tech_peers = [
            _row(
                f"NOISYTECH{i}",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.60 + i * 0.05,
                0.60 + i * 0.05,
                None,
                None,
                5_000_000.0,
                LONG_HISTORY,
                sector="Technology",
            )
            for i in range(15)
        ]
        util_peers = [
            _row(
                f"CALMUTIL{i}",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.08 + i * 0.005,
                0.08 + i * 0.005,
                None,
                None,
                5_000_000.0,
                LONG_HISTORY,
                sector="Utilities",
            )
            for i in range(15)
        ]
        updates = _run_with_mocked_rows([calm_for_tech, typical_util, *tech_peers, *util_peers])
        assert updates["TYPUTIL"][0] > updates["CALMTECH"][0], (
            f"volatility must score on absolute magnitude, not sector-relative position - "
            f"TYPUTIL (vol=0.20) must outscore CALMTECH (vol=0.35) despite CALMTECH looking "
            f"calm for its own noisy sector - TYPUTIL={updates['TYPUTIL'][0]} "
            f"CALMTECH={updates['CALMTECH'][0]}"
        )


class TestRiskMinWeightFloorPreserved:
    def test_symbol_with_no_scoreable_inputs_is_withheld(self) -> None:
        """RISK_MIN_WEIGHT_AVAILABLE=0.40 must still gate this pass exactly as it gates Pass 1 -
        a symbol with none of the 3 remaining components available (vol_60d/vol_252d/beta all
        None) must get risk_score=None (withheld)."""
        rows = [
            _row(
                "THIN",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                None,
                None,
                None,
                None,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "PEER",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.20,
                0.22,
                1.0,
                -8.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "THIN" in updates
        assert updates["THIN"][0] is None, f"expected risk_score withheld (None), got {updates['THIN'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class already fixed for Value/Quality/Growth/Momentum's batch
        passes - verify risk_score/composite_score aren't read back as inputs here either."""
        rows = [
            _row(
                "A",
                999.0,
                999.0,
                55.0,
                50.0,
                50.0,
                45.0,
                {},
                99.99,
                False,
                0.25,
                0.28,
                1.0,
                -15.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "B",
                999.0,
                999.0,
                60.0,
                45.0,
                55.0,
                40.0,
                {},
                99.99,
                False,
                0.60,
                0.65,
                1.5,
                -45.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "C",
                999.0,
                999.0,
                40.0,
                35.0,
                35.0,
                30.0,
                {},
                99.99,
                False,
                0.15,
                0.18,
                0.9,
                -8.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
        ]

        first_pass = _run_with_mocked_rows(rows)
        assert first_pass, "expected the first pass to correct the placeholder risk_score"

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
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not change "
            f"risk_score/composite_score again (got {second_pass})"
        )


class TestBetaAndLiquidityUnchanged:
    def test_beta_scored_by_low_beta_reward_not_closeness_to_one(self) -> None:
        """Beta now rewards LOW beta directly (2026-09-15, real BAB/Min-Vol anomaly - see
        _score_risk's own docstring), not closeness to an invented 1.0 target - a symbol with
        beta=0.1 must outscore one with beta=1.0."""
        rows = [
            _row(
                "ATONE",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.20,
                0.22,
                1.0,
                -10.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
            _row(
                "LOWBETA",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.20,
                0.22,
                0.1,
                -10.0,
                5_000_000.0,
                LONG_HISTORY,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["LOWBETA"][0] > updates["ATONE"][0], (
            f"beta=0.1 must score higher than beta=1.0 (low-beta reward, not closeness-to-1.0) - "
            f"ATONE={updates['ATONE'][0]} LOWBETA={updates['LOWBETA'][0]}"
        )

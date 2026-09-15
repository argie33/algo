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

Context: `_vol_curve_score`/`_max_drawdown_curve_score`'s fixed breakpoints (0.15/0.30/0.60 for
vol, 10/25/50 for drawdown) were live-checked against the real stability_metrics distribution
and found badly miscalibrated (p50 volatility_60d=0.516, already past the curve's OWN 0.30
breakpoint). This batch pass replaces them with winsorize+z-score against the live universe.

A pre-ship dry run of the naive z-score swap (before MIN_TRADING_DAYS_FOR_DRAWDOWN existed)
put brand-new IPOs in the top 15 of the corrected risk_score, off partial-history
max_drawdown_1y + Liquidity alone (exactly the "shitty microcap with no real track record
dominates the safest list" failure mode this whole exercise exists to eliminate).
TestMinTradingDaysForDrawdownGate below locks that regression in as a permanent test.

Test structure mirrors tests/unit/test_momentum_sector_neutral_scores_20260913.py exactly (same
mocked-DB-row / idempotency-across-repeated-runs pattern), adapted for Risk's different fetch
shape (one SELECT, with trading_days_history instead of a second technical-data SELECT).
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L
from loaders.stock_scores.risk_scoring import MIN_TRADING_DAYS_FOR_DRAWDOWN


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
    mock_cur.fetchall.return_value = rows
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


LONG_HISTORY = MIN_TRADING_DAYS_FOR_DRAWDOWN + 200  # comfortably clears the gate


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

    def test_sector_relative_scoring_matches_quality_growth_value_pattern(self) -> None:
        """The 2026-09-13 reversal made vol/drawdown sector-relative like Quality/Growth/Value.
        PARTIALLY RE-REVERSED 2026-09-15 (see `_compute_risk_absolute_zscore_percentiles`'s own
        comment): volatility_60d/252d went back to universe-wide after a whole-universe
        Fama-MacBeth test found vol has a real, robust forward-return edge broadly (the
        2026-09-13 test only checked banks/insurers/REITs, where it doesn't) AND a real min-vol
        fund's actual holdings (USMV) confirmed absolute vol is what matters, not
        calmer-than-sector. max_drawdown_1y stays sector-relative (evidence there is weak
        either way). This test still passes because max_drawdown's sector-relative pull plus
        beta/liquidity parity keep MEDTECH/MEDUTIL close enough even with vol now absolute -
        it's no longer proof vol itself is sector-relative, just that the overall risk_score
        for this synthetic pair still lands within tolerance. Uses 15 symbols per sector to
        clear `sector_neutral_zscore`'s min_sector_size=15 floor for drawdown, so neither group
        falls back to the residual pool there."""
        tech_rows = [
            _row(
                f"TECH{i}",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.70 + i * 0.05,
                0.75 + i * 0.05,
                1.0,
                -50.0 - i,
                5_000_000.0,
                LONG_HISTORY,
                sector="Technology",
            )
            for i in range(15)
        ]
        util_rows = [
            _row(
                f"UTIL{i}",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                0.10 + i * 0.01,
                0.12 + i * 0.01,
                1.0,
                -5.0 - i * 0.1,
                5_000_000.0,
                LONG_HISTORY,
                sector="Utilities",
            )
            for i in range(15)
        ]
        # A "mediocre for its sector" symbol in each group - same relative position (roughly
        # median-ish raw value within its own peer set), different absolute magnitude.
        test_tech = _row(
            "MEDTECH",
            999.0,
            999.0,
            50.0,
            50.0,
            50.0,
            50.0,
            {},
            99.99,
            False,
            0.90,
            0.95,
            1.0,
            -55.0,
            5_000_000.0,
            LONG_HISTORY,
            sector="Technology",
        )
        test_util = _row(
            "MEDUTIL",
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
            sector="Utilities",
        )
        updates = _run_with_mocked_rows([*tech_rows, *util_rows, test_tech, test_util])
        # Sanity: sector-relative scoring means the raw-worse-looking absolute Tech reading and
        # the raw-better-looking absolute Utilities reading land at comparable relative
        # positions within their own peer groups, unlike a universe-wide transform where MEDTECH
        # (much higher absolute vol/drawdown) would always score far below MEDUTIL.
        # Tolerance widened 2026-09-15 (40, was 30) after Liquidity's removal as a scored Risk
        # component rebalanced the remaining 4 inputs from 20% each (of 5, incl. Liquidity) to
        # 25% each - universe-wide volatility (still absolute, not sector-relative - see
        # test_volatility_is_universe_wide_not_sector_relative below) now carries proportionally
        # more of the total weight, so a real, large absolute-vol gap between these two synthetic
        # symbols (0.90-0.95 vs 0.10-0.12) legitimately widens the composite gap even though
        # drawdown's own sector-relative component still keeps them comparable on that input.
        assert abs(updates["MEDTECH"][0] - updates["MEDUTIL"][0]) < 40, (
            f"sector-relative scoring should put a similarly-positioned peer within each sector "
            f"in a comparable range, not penalize Tech purely for its sector's higher absolute "
            f"volatility - MEDTECH={updates['MEDTECH'][0]} MEDUTIL={updates['MEDUTIL'][0]}"
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


class TestMinTradingDaysForDrawdownGate:
    def test_brand_new_ipo_does_not_win_on_partial_history_drawdown_alone(self) -> None:
        """REGRESSION LOCK (caught in pre-ship verification, 2026-09-13): a brand-new IPO with
        real, large liquidity but too little history for volatility_60d/beta (both None, as
        stability_metrics would genuinely report for insufficient_history) must NOT win on
        max_drawdown_1y + Liquidity alone just because it hasn't been trading long enough to
        have lived through a real drawdown yet. Below MIN_TRADING_DAYS_FOR_DRAWDOWN, drawdown's
        weight must drop out entirely, leaving only Liquidity (0.20) - below
        RISK_MIN_WEIGHT_AVAILABLE (0.40) - so risk_score is withheld (None), not a fabricated
        near-max score."""
        thin_history = MIN_TRADING_DAYS_FOR_DRAWDOWN - 1
        rows = [
            # Brand-new IPO: real liquidity, no vol/beta (insufficient_history), tiny drawdown
            # only because it hasn't existed long enough to have a real one.
            _row(
                "NEWIPO",
                82.0,
                82.0,
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
                -5.0,
                20_000_000.0,
                thin_history,
            ),
            # A real, seasoned low-vol stock with a comparably small drawdown AND enough history
            # to trust it - must still be scoreable and must not be penalized by NEWIPO merely
            # existing in the same batch.
            _row(
                "SEASONED",
                70.0,
                70.0,
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
                20_000_000.0,
                LONG_HISTORY,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "NEWIPO" in updates, "expected NEWIPO's risk_score to change (withheld), so it must appear in the UPDATE"
        assert updates["NEWIPO"][0] is None, (
            f"expected a brand-new IPO's risk_score to be withheld (None) below MIN_TRADING_DAYS_FOR_DRAWDOWN, "
            f"got {updates['NEWIPO'][0]}"
        )

    def test_symbol_at_or_above_the_history_threshold_is_scored_normally(self) -> None:
        """Sanity check on the boundary: a symbol with exactly MIN_TRADING_DAYS_FOR_DRAWDOWN
        real trading days must have its max_drawdown_1y counted, not gated out."""
        rows = [
            _row(
                "EXACT",
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
                20_000_000.0,
                MIN_TRADING_DAYS_FOR_DRAWDOWN,
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
                -40.0,
                20_000_000.0,
                LONG_HISTORY,
            ),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["EXACT"][0] is not None, (
            "a symbol clearing the history floor exactly must be scored, not withheld"
        )
        assert updates["EXACT"][0] > updates["PEER"][0], (
            "EXACT has a much smaller drawdown magnitude than PEER and both clear the history floor - "
            f"EXACT should score higher (EXACT={updates['EXACT'][0]} PEER={updates['PEER'][0]})"
        )


class TestRiskMinWeightFloorPreserved:
    def test_symbol_with_only_liquidity_available_is_withheld(self) -> None:
        """RISK_MIN_WEIGHT_AVAILABLE=0.40 (2/5 slots) must still gate this pass exactly as it
        gates Pass 1 - a symbol with only Liquidity available (1/5 slots = 0.20 weight, vol/
        beta/drawdown all None or gated) must get risk_score=None (withheld)."""
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

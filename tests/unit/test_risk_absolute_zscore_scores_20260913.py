"""Tests for update_risk_absolute_zscore_scores() (loaders/stock_scores/risk_scoring.py, added
2026-09-13), the Risk-pillar sibling of Momentum/Growth/Value's own sector-neutral z-score
batch passes.

REWRITTEN 2026-09-19 (AQR PIVOT REVERTED - see risk_scoring.py's own module docstring,
RISK_COMPONENT_WEIGHT's "REVERTED 2026-09-19" note, for the full evidence trail: live TOP/BVC
bad-print Safety-leaderboard inversion, and the explicit user directive to put every pillar
back on one consistent MSCI/Barra methodology after Value/Momentum/Quality had already been
reverted the day before but Risk was left on AQR's beta_bab). This pass is back to its
pre-pivot 3-component construction: volatility_60d (Barra's real DASTD), cmra_12m (Barra's real
Cumulative Range descriptor), and raw OLS beta - each independently winsorize+z-scored
universe-wide (market-cap-weighted) and equal-weighted 1/3 (RISK_COMPONENT_WEIGHT).

`_row()` below matches `_fetch_risk_absolute_zscore_rows`'s real, current SELECT shape:
(symbol, risk_score, composite_score, quality_score, growth_score, value_score, momentum_score,
components, data_completeness, data_unavailable, avg_dollar_volume_20d, volatility_60d,
market_cap, cmra_12m, beta) - 15 columns.

Grouping is universe-wide (empty sectors dict), matching the real, published low-volatility/
low-beta anomaly (Ang et al. 2006; Frazzini & Pedersen 2014) this module's own top-of-file
docstring describes - not sector-relative. RISK_MIN_WEIGHT_AVAILABLE (0.40) requires >=2 of the
3 equal-weighted (1/3 each) components to clear.

Test structure mirrors tests/unit/test_momentum_sector_neutral_scores_20260913.py (same
mocked-DB-row / idempotency-across-repeated-runs pattern).
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
    avg_dollar_volume_20d: float | None,
    volatility_60d: float | None,
    market_cap: float = 1_000_000_000.0,
    cmra_12m: float | None = None,
    beta: float | None = None,
) -> tuple:
    """Build a mocked SELECT row matching `_fetch_risk_absolute_zscore_rows`'s real, current
    column order: symbol, risk_score, composite_score, quality_score, growth_score, value_score,
    momentum_score, components, data_completeness, data_unavailable, avg_dollar_volume_20d,
    volatility_60d, market_cap, cmra_12m, beta."""
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
        avg_dollar_volume_20d,
        volatility_60d,
        market_cap,
        cmra_12m,
        beta,
    )


def _row_all_three(
    symbol: str, volatility_60d: float, cmra_12m: float, beta: float, adv20: float = 5_000_000.0
) -> tuple:
    """Convenience: a row with all 3 scored components present, matching values so ordering
    tests aren't muddied by conflicting legs."""
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
        adv20,
        volatility_60d,
        1_000_000_000.0,
        cmra_12m,
        beta,
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


class TestAbsoluteZScoreRanking:
    def test_lower_values_score_higher(self) -> None:
        """Basic sanity: lower volatility_60d/cmra_12m/beta (more defensive) must score higher
        than a peer with higher values, under the real winsorize+z-score transform."""

        def _rows_for(v: float) -> tuple:
            return _row_all_three(f"SYM_{v}", v, v, v)

        values = [-0.5, 0.2, 0.6, 1.0, 1.8]
        rows = [_rows_for(v) for v in values]
        updates = _run_with_mocked_rows(rows)
        ordered = [updates[f"SYM_{v}"][0] for v in values]
        assert ordered == sorted(ordered, reverse=True), f"expected strictly descending scores, got {ordered}"

    def test_identical_inputs_score_identically(self) -> None:
        """Identical raw inputs must map to the IDENTICAL score - this pass has no sector
        grouping to otherwise differentiate them."""
        rows = [
            _row_all_three("A", 0.5, 0.5, 0.7),
            _row_all_three("B", 0.5, 0.5, 0.7),
            _row_all_three("PEER1", 1.0, 1.0, 1.4),
            _row_all_three("PEER2", 0.1, 0.1, 0.1),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["A"][0] == updates["B"][0], (
            f"identical inputs must score identically - A={updates['A'][0]} B={updates['B'][0]}"
        )

    def test_universe_wide_not_sector_relative(self) -> None:
        """This pass groups universe-wide (empty sectors dict, no sector column even fetched
        any more) - there is no per-sector distinction to test other than confirming symbols
        with no shared grouping key still get correctly ranked against the whole population."""
        subject = _row_all_three("SUBJECT", 0.3, 0.3, 0.3)
        better_peers = [_row_all_three(f"BETTER{i}", -0.5 - i * 0.1, -0.5 - i * 0.1, -0.5 - i * 0.1) for i in range(15)]
        worse_peers = [_row_all_three(f"WORSE{i}", 2.0 + i * 0.1, 2.0 + i * 0.1, 2.0 + i * 0.1) for i in range(15)]
        updates = _run_with_mocked_rows([subject, *better_peers, *worse_peers])
        assert updates["SUBJECT"][0] < updates["BETTER0"][0]
        assert updates["SUBJECT"][0] > updates["WORSE0"][0]

    def test_near_zero_liquidity_gates_inputs_out(self) -> None:
        """NEAR_ZERO_LIQUIDITY_THRESHOLD gate: a near-frozen price series (avg_dollar_volume_20d
        just above 0) makes volatility_60d/cmra_12m/beta measurement noise, not a real signal -
        it must be excluded from the population, not just from its own score, so it doesn't bias
        every other symbol's z-score against a fabricated data point."""
        frozen = _row_all_three("FROZEN", -5.0, -5.0, -5.0, adv20=100.0)
        peer = _row_all_three("PEER", 1.0, 1.0, 1.0)
        updates = _run_with_mocked_rows([frozen, peer])
        assert updates["FROZEN"][0] is None, (
            f"a near-zero-liquidity symbol's inputs must be gated out entirely (withheld), got {updates['FROZEN'][0]}"
        )


class TestRiskMinWeightFloorPreserved:
    def test_symbol_with_no_inputs_is_withheld(self) -> None:
        """RISK_MIN_WEIGHT_AVAILABLE=0.40 must still gate this pass - with no scored inputs at
        all, a symbol has zero available weight and must get risk_score=None (withheld), not a
        fabricated score."""
        rows = [
            _row("THIN", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, None),
            _row_all_three("PEER", 1.0, 1.0, 1.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "THIN" in updates
        assert updates["THIN"][0] is None, f"expected risk_score withheld (None), got {updates['THIN'][0]}"

    def test_single_of_three_components_is_withheld(self) -> None:
        """A single component alone (weight 1/3 ~= 0.333) falls below the 0.40 floor."""
        rows = [
            _row("THIN", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 0.5),
            _row_all_three("PEER", 1.0, 1.0, 1.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["THIN"][0] is None

    def test_two_of_three_components_clears_floor(self) -> None:
        """2 of 3 components (weight 2/3 ~= 0.667) clears RISK_MIN_WEIGHT_AVAILABLE (0.40)."""
        rows = [
            _row(
                "PARTIAL",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                5_000_000.0,
                0.5,
                1_000_000_000.0,
                0.5,
            ),
            _row_all_three("PEER", 1.0, 1.0, 1.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["PARTIAL"][0] is not None


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class already fixed for Value/Quality/Growth/Momentum's batch
        passes - verify risk_score/composite_score aren't read back as inputs here either."""
        rows = [
            _row_all_three("A", 0.4, 0.4, 0.4),
            _row_all_three("B", 1.5, 1.5, 1.5),
            _row_all_three("C", -0.2, -0.2, -0.2),
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
                r[10],  # avg_dollar_volume_20d unchanged
                r[11],  # volatility_60d unchanged
                r[12],  # market_cap unchanged
                r[13],  # cmra_12m unchanged
                r[14],  # beta unchanged
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not change "
            f"risk_score/composite_score again (got {second_pass})"
        )

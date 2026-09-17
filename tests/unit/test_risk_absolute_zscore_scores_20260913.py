"""Tests for update_risk_absolute_zscore_scores() (loaders/stock_scores/risk_scoring.py, added
2026-09-13), the Risk-pillar sibling of Momentum/Growth/Value's own sector-neutral z-score
batch passes.

REWRITTEN 2026-09-17 (AQR PIVOT - see risk_scoring.py's own module docstring, "AQR PIVOT
2026-09-17"). Everything in this file previously exercised a 3-component pass (volatility_60d,
volatility_252d/cmra_12m, beta), each winsorize+z-scored and equal-weighted. That pass now
z-scores exactly ONE input, `beta_bab` (Frazzini & Pedersen 2014's own published shrinkage
estimator, computed upstream in loaders/load_risk_metrics_daily.py's `_calculate_beta_bab`) -
volatility_60d/cmra_12m are computed/persisted informational only, no longer scoring inputs, and
plain `beta` was replaced by `beta_bab` for scoring purposes.

DEAD-COLUMN SWEEP 2026-09-17 (same day, AQR purity cleanup - user: "get the aqr down to its
purest form... extra shit mixing with msci"): `_fetch_risk_absolute_zscore_rows`'s own SELECT
no longer fetches volatility_60d/cmra_12m/beta at all - a prior version of this pass's own
rewrite kept them as always-None placeholder columns nothing read, the exact "fetched but
nothing reads it" dead-weight pattern this file's history already flags elsewhere. `_row()`
below matches the real, current, lean SELECT shape: (symbol, risk_score, composite_score,
quality_score, growth_score, value_score, momentum_score, components, data_completeness,
data_unavailable, avg_dollar_volume_20d, beta_bab) - 12 columns, beta_bab last.

Grouping is universe-wide (empty sectors dict), matching the real, published low-beta anomaly
(Ang et al. 2006; Frazzini & Pedersen 2014) this module's own top-of-file docstring describes -
not sector-relative. RISK_COMPONENT_WEIGHT is 1.0 (beta_bab is the pillar's sole scored
component) - RISK_MIN_WEIGHT_AVAILABLE (0.40) is now a binary gate: a symbol either has beta_bab
(clears the floor outright) or doesn't (withheld), there is no partial-weight state left to test.

Test structure mirrors tests/unit/test_momentum_sector_neutral_scores_20260913.py (same
mocked-DB-row / idempotency-across-repeated-runs pattern), adapted for Risk's single-field
z-score shape.
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
    beta_bab: float | None,
) -> tuple:
    """Build a mocked SELECT row matching `_fetch_risk_absolute_zscore_rows`'s real, current
    column order: symbol, risk_score, composite_score, quality_score, growth_score, value_score,
    momentum_score, components, data_completeness, data_unavailable, avg_dollar_volume_20d,
    beta_bab. volatility_60d/cmra_12m/beta are no longer in the SELECT at all (dead-column
    sweep, see this file's module docstring) - not represented here even as placeholders."""
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
        beta_bab,
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
    def test_lower_beta_bab_scores_higher(self) -> None:
        """Basic sanity: lower beta_bab (more defensive) must score higher than a peer with a
        higher beta_bab, under the real winsorize+z-score transform."""

        def _rows_for(beta_bab: float) -> tuple:
            symbol = f"SYM_{beta_bab}"
            return _row(symbol, 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, beta_bab)

        values = [-0.5, 0.2, 0.6, 1.0, 1.8]
        rows = [_rows_for(v) for v in values]
        updates = _run_with_mocked_rows(rows)
        ordered = [updates[f"SYM_{v}"][0] for v in values]
        assert ordered == sorted(ordered, reverse=True), f"expected strictly descending scores, got {ordered}"

    def test_identical_beta_bab_scores_identically(self) -> None:
        """Identical raw beta_bab inputs must map to the IDENTICAL score - this pass has no
        sector grouping to otherwise differentiate them."""
        rows = [
            _row("A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 0.7),
            _row("B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 0.7),
            _row("PEER1", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 1.4),
            _row("PEER2", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 0.1),
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["A"][0] == updates["B"][0], (
            f"identical beta_bab inputs must score identically - A={updates['A'][0]} B={updates['B'][0]}"
        )

    def test_universe_wide_not_sector_relative(self) -> None:
        """This pass groups universe-wide (empty sectors dict, no sector column even fetched
        any more) - there is no per-sector distinction to test other than confirming symbols
        with no shared grouping key still get correctly ranked against the whole population."""
        subject = _row("SUBJECT", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 0.3)
        better_peers = [
            _row(f"BETTER{i}", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, -0.5 - i * 0.1)
            for i in range(15)
        ]
        worse_peers = [
            _row(f"WORSE{i}", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 2.0 + i * 0.1)
            for i in range(15)
        ]
        updates = _run_with_mocked_rows([subject, *better_peers, *worse_peers])
        assert updates["SUBJECT"][0] < updates["BETTER0"][0]
        assert updates["SUBJECT"][0] > updates["WORSE0"][0]

    def test_near_zero_liquidity_gates_beta_bab_out(self) -> None:
        """NEAR_ZERO_LIQUIDITY_THRESHOLD gate: a near-frozen price series (avg_dollar_volume_20d
        just above 0) makes beta_bab measurement noise, not a real signal - it must be excluded
        from the population, not just from its own score, so it doesn't bias every other
        symbol's z-score against a fabricated data point."""
        frozen = _row("FROZEN", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 100.0, -5.0)
        peer = _row("PEER", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 1.0)
        updates = _run_with_mocked_rows([frozen, peer])
        assert updates["FROZEN"][0] is None, (
            f"a near-zero-liquidity symbol's beta_bab must be gated out entirely (withheld), got {updates['FROZEN'][0]}"
        )


class TestRiskMinWeightFloorPreserved:
    def test_symbol_with_no_beta_bab_is_withheld(self) -> None:
        """RISK_MIN_WEIGHT_AVAILABLE=0.40 must still gate this pass - beta_bab is the pillar's
        sole scored input (weight 1.0), so a symbol with no beta_bab at all has zero available
        weight and must get risk_score=None (withheld), not a fabricated score."""
        rows = [
            _row("THIN", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, None),
            _row("PEER", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 5_000_000.0, 1.0),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "THIN" in updates
        assert updates["THIN"][0] is None, f"expected risk_score withheld (None), got {updates['THIN'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class already fixed for Value/Quality/Growth/Momentum's batch
        passes - verify risk_score/composite_score aren't read back as inputs here either."""
        rows = [
            _row("A", 999.0, 999.0, 55.0, 50.0, 50.0, 45.0, {}, 99.99, False, 5_000_000.0, 0.4),
            _row("B", 999.0, 999.0, 60.0, 45.0, 55.0, 40.0, {}, 99.99, False, 5_000_000.0, 1.5),
            _row("C", 999.0, 999.0, 40.0, 35.0, 35.0, 30.0, {}, 99.99, False, 5_000_000.0, -0.2),
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
                r[11],  # beta_bab unchanged
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not change "
            f"risk_score/composite_score again (got {second_pass})"
        )

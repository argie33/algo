"""Tests for update_growth_sector_neutral_scores() (loaders/stock_scores/growth_scoring.py,
added 2026-09-08).

REBUILT 2026-09-17 (factor-purity follow-up, user: "where we inaccurately mixing industry
things to a point where it doesn't make sense"). This file used to test two things that no
longer exist:
  - A sector-relative z-score construction. Growth was REVERSED to universe_wide_zscore this
    same pass - see update_growth_sector_neutral_scores()'s own "REVERSED TO UNIVERSE-WIDE"
    docstring note for the full evidence trail (it had inherited sector-relative treatment from
    Quality's OLD, since-reversed implementation, was never independently validated, and its own
    citation for "matches MSCI" didn't actually say that). The old
    `test_same_absolute_growth_rate_scores_differently_across_sectors` test asserted the OPPOSITE
    of what universe-wide z-scoring produces - replaced below with a test that an identical raw
    rate DOES score identically regardless of sector, which is now the correct behavior.
  - 12 GROWTH_SCORE_FIELDS (trimmed to the real MSCI GIMIVG/Barra EGRO 4-field set on
    2026-09-16 - see that constant's own GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE). The old
    `_full_fields`/row-building helpers assumed 12 slots and a trailing `sector` column that no
    longer exists in the SELECT at all.

Test structure mirrors tests/unit/test_value_multiples_percentile_idempotent_20260831.py and
tests/unit/test_quality_roe_roce_percentile_idempotent_and_negative_floor_20260831.py (same
mocked-DB-row / idempotency-across-repeated-runs pattern), since this method is built on the
identical "Pass 1 provisional, batch pass fully recomputes and overwrites" architecture.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L
from loaders.stock_scores.growth_scoring import GROWTH_SCORE_FIELDS


def _row(
    symbol: str,
    growth_score: float,
    composite_score: float,
    quality_score: float | None,
    value_score: float | None,
    risk_score: float | None,
    momentum_score: float | None,
    components: dict | None,
    data_completeness: float | None,
    data_unavailable: bool,
    field_values: dict[str, float | None],
) -> tuple:
    """Build a mocked SELECT row matching update_growth_sector_neutral_scores()'s own column
    order exactly: symbol, growth_score, composite_score, quality_score, value_score, risk_score,
    momentum_score, components, data_completeness, data_unavailable, <GROWTH_SCORE_FIELDS in
    order>. No trailing sector/FPI columns - removed 2026-09-17 alongside the universe-wide
    reversal (see module docstring)."""
    field_tuple = tuple(field_values.get(f) for f in GROWTH_SCORE_FIELDS)
    return (
        symbol,
        growth_score,
        composite_score,
        quality_score,
        value_score,
        risk_score,
        momentum_score,
        components if components is not None else {},
        data_completeness,
        data_unavailable,
        *field_tuple,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_growth_sector_neutral_scores() against a fully mocked DB returning `rows` for
    the SELECT, and return {symbol: (growth_score, composite_score)} from the UPDATE, or {} if
    no UPDATE was issued."""
    mock_cur = MagicMock()
    # side_effect [rows, []]: first fetchall() is the correction pass's own SELECT, second is
    # _withhold_growth_below_floor()'s own SELECT (added 2026-09-16, factor-purity sweep) - []
    # means no symbol is below the liquidity floor in this test's fixture population.
    mock_cur.fetchall.side_effect = [rows, []]
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_growth_sector_neutral_scores()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


def _full_fields(base: float) -> dict[str, float]:
    """All GROWTH_SCORE_FIELDS set to distinct-but-related values around `base`, so every symbol
    clears GROWTH_MIN_FIELDS_AVAILABLE and z-scores aren't degenerate."""
    return {field: base + i for i, field in enumerate(GROWTH_SCORE_FIELDS)}


class TestUniverseWideRanking:
    def test_stronger_grower_scores_higher_than_weaker_peer(self) -> None:
        """Basic sanity: a symbol with uniformly higher raw growth rates across all
        GROWTH_SCORE_FIELDS must score higher than one with uniformly lower rates."""
        rows = [
            _row("STRONG", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(40.0)),
            _row("WEAK", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(-10.0)),
            _row("MID_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(10.0)),
            _row("MID_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(15.0)),
            _row("MID_C", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0)),
        ]
        updates = _run_with_mocked_rows(rows)
        assert (
            updates["STRONG"][0] > updates["MID_C"][0] > updates["MID_B"][0] > updates["MID_A"][0] > updates["WEAK"][0]
        )

    def test_identical_raw_growth_rate_scores_identically_regardless_of_peer_mix(self) -> None:
        """Reversed 2026-09-17 (see module docstring): Growth is now universe-wide, not
        sector-relative - the whole population is one peer group, so which OTHER symbols happen
        to exist alongside a given raw rate must not change that rate's own z-score/percentile.
        Two symbols with the identical raw rate must score identically even though one sits among
        a cluster of much stronger peers and the other among much weaker ones - the opposite of
        what the pre-reversal sector-relative version asserted."""
        strong_cluster = [
            _row(f"STRONGPEER_{i}", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(v))
            for i, v in enumerate([30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0])
        ]
        weak_cluster = [
            _row(f"WEAKPEER_{i}", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(v))
            for i, v in enumerate([-20.0, -15.0, -10.0, -5.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0])
        ]
        shared_value = 15.0
        rows = [
            _row("AMONG_STRONG", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(shared_value)),
            _row("AMONG_WEAK", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(shared_value)),
            *strong_cluster,
            *weak_cluster,
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["AMONG_STRONG"][0] == updates["AMONG_WEAK"][0], (
            f"AMONG_STRONG={updates['AMONG_STRONG'][0]} AMONG_WEAK={updates['AMONG_WEAK'][0]}: identical raw "
            "growth rates must score identically under universe-wide z-scoring regardless of which other "
            "symbols happen to be in the run - peer-group membership no longer matters after the "
            "2026-09-17 universe-wide reversal"
        )


class TestGrowthMinFieldsAvailableFloorPreserved:
    def test_symbol_with_one_of_four_fields_not_saturated(self) -> None:
        """GROWTH_MIN_FIELDS_AVAILABLE=2 must still gate the universe-wide pass exactly as it
        gates Pass 1 (ATTO/GFUZ/VRXA/KWM/BLSM-shaped case from growth_scoring.py's own
        docstring) - growth_score_new must be None (withheld), not a thin-sample extrapolation."""
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
                {GROWTH_SCORE_FIELDS[0]: 40.0},  # only 1 of 4 fields
            ),
            # peers so THIN's single available field isn't degenerate against a tiny population
            _row("PEER_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(10.0)),
            _row("PEER_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0)),
        ]
        updates = _run_with_mocked_rows(rows)
        assert "THIN" in updates
        assert updates["THIN"][0] is None, f"expected growth_score withheld (None), got {updates['THIN'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class this repo already fixed for Value/Quality's batch
        passes (see those files' own '2026-08-31 BUG FOUND + FIXED' notes) would apply here too
        if growth_score/composite_score were ever read back as inputs - verify they aren't."""
        rows = [
            _row("A", 999.0, 999.0, 55.0, 50.0, 45.0, 50.0, {}, 99.99, False, _full_fields(25.0)),
            _row("B", 999.0, 999.0, 60.0, 45.0, 55.0, 40.0, {}, 99.99, False, _full_fields(-5.0)),
            _row("C", 999.0, 999.0, 40.0, 35.0, 35.0, 30.0, {}, 99.99, False, _full_fields(60.0)),
        ]

        first_pass = _run_with_mocked_rows(rows)
        assert first_pass, "expected the first pass to correct the placeholder growth_score"

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
                dict(zip(GROWTH_SCORE_FIELDS, r[10 : 10 + len(GROWTH_SCORE_FIELDS)], strict=True)),
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not "
            f"change growth_score/composite_score again (got {second_pass})"
        )


class TestImplausibleValueExclusionPreserved:
    def test_extreme_raw_value_excluded_not_saturated(self) -> None:
        """GROWTH_INPUT_IMPLAUSIBLE_PCT=150.0: a field's raw value far past that bound must be
        excluded from the z-score population entirely (same as Pass 1's exclusion from the
        curve-blend), not merely winsorized down to a high-but-finite z-score. Uses
        sustainable_growth_rate (the one live GROWTH_SCORE_FIELDS candidate this threshold
        actually still does real work for - see GROWTH_INPUT_IMPLAUSIBLE_PCT's own 2026-09-17
        docstring note, e.g. VSA's real 1,674.89%), not eps_growth_1y (removed from
        GROWTH_SCORE_FIELDS on 2026-09-16, no longer a live candidate at all)."""
        fields = _full_fields(20.0)
        fields["sustainable_growth_rate"] = 1674.89  # VSA-shaped, from GROWTH_INPUT_IMPLAUSIBLE_PCT's own docstring
        rows = [
            _row("VSA_LIKE", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, fields),
            _row("PEER_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0)),
            _row("PEER_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(25.0)),
        ]
        updates = _run_with_mocked_rows(rows)
        # VSA_LIKE's sustainable_growth_rate term is dropped, leaving 3/4 fields (an ordinary,
        # non-saturating blend) - it should land close to its peers, not artificially inflated.
        assert updates["VSA_LIKE"][0] is not None
        assert updates["VSA_LIKE"][0] < 100.0

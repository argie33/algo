"""Tests for update_growth_sector_neutral_scores() (loaders/stock_scores/growth_scoring.py,
added 2026-09-08), the Growth-pillar sibling of Quality's 2026-09-07 sector-neutral-zscore
rewrite (loaders/helpers/vqg_quality_batch.py's update_quality_sector_neutral_scores()).

Context: after Quality's rewrite landed, composite_score's leaderboard was still ~60-66%
Financial Services, and growth_score itself led every sector average - traced to
_score_single_growth's ABSOLUTE curve (identical shape across every sector, no peer-group
context), the same gap Quality had before its own rewrite. This method replaces that curve
with sector_neutral_zscore()/zscore_to_percentile_scale() (loaders/helpers/factor_normalization.py)
- winsorize then z-score each of the 12 GROWTH_SCORE_FIELDS candidates WITHIN each symbol's own
GICS sector, map to [0,100], then re-apply the SAME equal-weighted blend / GROWTH_MIN_FIELDS_
AVAILABLE floor / GROWTH_INPUT_IMPLAUSIBLE_PCT exclusion _score_growth already used - only the
per-field transform changes.

Test structure mirrors tests/unit/test_value_multiples_percentile_idempotent_20260831.py and
tests/unit/test_quality_roe_roce_percentile_idempotent_and_negative_floor_20260831.py exactly
(same mocked-DB-row / idempotency-across-repeated-runs pattern), since this method is built on
the identical "Pass 1 provisional, batch pass fully recomputes and overwrites" architecture.
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
    sector: str | None,
) -> tuple:
    """Build a mocked SELECT row matching update_growth_sector_neutral_scores()'s own column
    order exactly: symbol, growth_score, composite_score, quality_score, value_score, risk_score,
    momentum_score, components, data_completeness, data_unavailable, <12 GROWTH_SCORE_FIELDS in
    GROWTH_SCORE_FIELDS order>, sector."""
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
        sector,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_growth_sector_neutral_scores() against a fully mocked DB returning `rows` for
    the SELECT, and return {symbol: (growth_score, composite_score)} from the UPDATE, or {} if
    no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
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
    """All 12 GROWTH_SCORE_FIELDS set to distinct-but-related values around `base`, so every
    symbol clears GROWTH_MIN_FIELDS_AVAILABLE and z-scores aren't degenerate."""
    return {field: base + i for i, field in enumerate(GROWTH_SCORE_FIELDS)}


class TestSectorNeutralRanking:
    def test_stronger_grower_scores_higher_than_weaker_peer_same_sector(self) -> None:
        """Basic sanity: within the same sector, a symbol with uniformly higher raw growth
        rates across all 12 fields must score higher than one with uniformly lower rates."""
        rows = [
            _row("STRONG", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(40.0), "Technology"),
            _row("WEAK", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(-10.0), "Technology"),
            _row("MID_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(10.0), "Technology"),
            _row("MID_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(15.0), "Technology"),
            _row("MID_C", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0), "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        assert (
            updates["STRONG"][0] > updates["MID_C"][0] > updates["MID_B"][0] > updates["MID_A"][0] > updates["WEAK"][0]
        )

    def test_same_absolute_growth_rate_scores_differently_across_sectors(self) -> None:
        """The whole point of the rewrite: an IDENTICAL raw growth rate should NOT map to the
        identical score once sector peer groups differ - a rate that's mediocre for a
        fast-growing sector should score lower than the SAME rate in a slow-growing sector.
        Financial Services peers here are uniformly weaker than Technology peers, so a shared
        raw value of 15.0 should rank the Financial Services symbol relatively higher."""
        tech_rows = [
            _row(f"TECH_{i}", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(v), "Technology")
            for i, v in enumerate(
                [30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 15.0]
            )
        ]
        fin_rows = [
            _row(
                f"FIN_{i}",
                999.0,
                999.0,
                50.0,
                50.0,
                50.0,
                50.0,
                {},
                99.99,
                False,
                _full_fields(v),
                "Financial Services",
            )
            for i, v in enumerate(
                [-20.0, -15.0, -10.0, -5.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 15.0]
            )
        ]
        updates = _run_with_mocked_rows(tech_rows + fin_rows)
        # TECH_14 and FIN_14 both carry the identical raw base value 15.0 across all 12 fields.
        assert updates["FIN_14"][0] > updates["TECH_14"][0], (
            f"FIN_14={updates['FIN_14'][0]} TECH_14={updates['TECH_14'][0]}: identical raw growth "
            "rate should score higher relative to a weaker (Financial Services) peer group than a "
            "stronger (Technology) one - this is the entire point of sector-neutral z-scoring"
        )


class TestGrowthMinFieldsAvailableFloorPreserved:
    def test_symbol_with_one_of_twelve_fields_withheld_not_saturated(self) -> None:
        """GROWTH_MIN_FIELDS_AVAILABLE=5 must still gate the sector-neutral pass exactly as it
        gated Pass 1 (ATTO/GFUZ/VRXA/KWM/BLSM-shaped case from growth_scoring.py's own
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
                {"revenue_growth_1y": 40.0},  # only 1/12 fields
                "Technology",
            ),
            # peers so THIN's single available field isn't degenerate against a 1-symbol sector
            _row("PEER_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(10.0), "Technology"),
            _row("PEER_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0), "Technology"),
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
            _row("A", 999.0, 999.0, 55.0, 50.0, 45.0, 50.0, {}, 99.99, False, _full_fields(25.0), "Technology"),
            _row("B", 999.0, 999.0, 60.0, 45.0, 55.0, 40.0, {}, 99.99, False, _full_fields(-5.0), "Technology"),
            _row("C", 999.0, 999.0, 40.0, 35.0, 35.0, 30.0, {}, 99.99, False, _full_fields(60.0), "Technology"),
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
                r[10 + len(GROWTH_SCORE_FIELDS)],
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
        curve-blend), not merely winsorized down to a high-but-finite z-score."""
        fields = _full_fields(20.0)
        fields["eps_growth_1y"] = 1889.36  # KARO-shaped one-off, from growth_scoring.py's own docstring
        rows = [
            _row("KARO_LIKE", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, fields, "Technology"),
            _row("PEER_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(20.0), "Technology"),
            _row("PEER_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, _full_fields(25.0), "Technology"),
        ]
        updates = _run_with_mocked_rows(rows)
        # KARO_LIKE's eps_growth_1y term is dropped, leaving 11/12 fields (an ordinary,
        # non-saturating blend) - it should land close to its peers, not artificially inflated.
        assert updates["KARO_LIKE"][0] is not None
        assert updates["KARO_LIKE"][0] < 100.0

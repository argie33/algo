"""Tests for update_momentum_sector_neutral_scores() (loaders/stock_scores/momentum_scoring.py,
added 2026-09-13), the Momentum-pillar sibling of Growth's 2026-09-08 sector-neutral-zscore pass
(loaders/stock_scores/growth_scoring.py's update_growth_sector_neutral_scores()) and Quality's
2026-09-07 rewrite (loaders/helpers/vqg_quality_batch.py's update_quality_sector_neutral_scores()).

Context: live DB check (/goal "question the scoring methodology" session, 2026-09-13) found avg
momentum_score by sector ranging Energy 72.0 down to Consumer Cyclical 39.4 (32.6-point spread) -
the same architectural gap Quality/Growth/Value already had closed: an absolute, sector-agnostic
mapping from raw technical/return values to 0-100, with no peer-group context. This method
replaces Pass-1's fixed mappings with sector_neutral_zscore()/zscore_to_percentile_scale() for
all 6 of Pass-1's raw inputs (momentum_3m, mom_12_1, rsi_14, macd_sign, price_vs_sma_50/200),
consolidated into the same 4 weighted slots (25% each) Pass-1 already uses, gated by the same
MOMENTUM_MIN_WEIGHT floor.

Test structure mirrors tests/unit/test_growth_sector_neutral_scores_20260908.py exactly (same
mocked-DB-row / idempotency-across-repeated-runs pattern) - this method is built on the identical
"Pass 1 provisional, batch pass fully recomputes and overwrites" architecture, just with two
SELECTs (stock_scores+momentum_metrics+company_profile, then technical_data_daily's latest row
per symbol) instead of Growth's one.
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
    sector: str | None,
) -> tuple:
    """Build a mocked main-SELECT row matching update_momentum_sector_neutral_scores()'s own
    column order exactly: symbol, momentum_score, composite_score, quality_score, growth_score,
    value_score, risk_score, components, data_completeness, data_unavailable, momentum_1m,
    momentum_3m, momentum_12m, sector."""
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
        sector,
    )


def _tech_row(
    symbol: str,
    rsi_14: float | None,
    macd: float | None,
    sma_50: float | None,
    sma_200: float | None,
    close: float | None,
) -> tuple:
    """Build a mocked technical_data_daily-SELECT row: symbol, rsi_14, macd, sma_50, sma_200,
    close, date. `date` is a real date object here since the staleness gate compares it via
    MarketCalendar.trading_days_elapsed."""
    from datetime import date

    return (symbol, rsi_14, macd, sma_50, sma_200, close, date.today())


def _run_with_mocked_rows(rows: list[tuple], tech_rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    """Run update_momentum_sector_neutral_scores() against a fully mocked DB returning `rows` for
    the main SELECT and `tech_rows` for the technical_data_daily SELECT, and return
    {symbol: (momentum_score, composite_score)} from the UPDATE, or {} if no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.side_effect = [rows, tech_rows]
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_momentum_sector_neutral_scores()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: (row[1], row[2]) for row in updates}


class TestSectorNeutralRanking:
    def test_stronger_momentum_scores_higher_than_weaker_peer_same_sector(self) -> None:
        """Basic sanity: within the same sector, a symbol with uniformly higher raw momentum
        (return + technical) inputs must score higher than one with uniformly lower ones."""

        def _rows_for(base: float) -> tuple[tuple, tuple]:
            symbol = f"SYM_{base}"
            return (
                _row(symbol, 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, base, base * 2, "Technology"),
                _tech_row(symbol, 50.0 + base, base, 100.0 * (1 + base / 100.0), 100.0, 100.0 * (1 + base / 100.0)),
            )

        pairs = [_rows_for(v) for v in (-10.0, 0.0, 10.0, 20.0, 30.0)]
        rows = [p[0] for p in pairs]
        tech_rows = [p[1] for p in pairs]
        updates = _run_with_mocked_rows(rows, tech_rows)
        ordered = [updates[f"SYM_{v}"][0] for v in (30.0, 20.0, 10.0, 0.0, -10.0)]
        assert ordered == sorted(ordered, reverse=True), f"expected strictly descending scores, got {ordered}"

    def test_same_absolute_momentum_scores_differently_across_sectors(self) -> None:
        """The whole point of the rewrite: an IDENTICAL raw momentum_3m should NOT map to the
        identical score once sector peer groups differ - Energy peers here are uniformly
        stronger than Real Estate peers, so a shared raw value should rank the Real Estate
        symbol relatively higher."""
        energy_vals = [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 20.0]
        re_vals = [-30.0, -25.0, -20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 20.0]

        def _mk(prefix: str, sector: str, vals: list[float]) -> tuple[list[tuple], list[tuple]]:
            rows, tech = [], []
            for i, v in enumerate(vals):
                symbol = f"{prefix}_{i}"
                rows.append(_row(symbol, 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, v, v * 2, sector))
                tech.append(_tech_row(symbol, 50.0, 1.0, 100.0, 100.0, 105.0))
            return rows, tech

        energy_rows, energy_tech = _mk("ENERGY", "Energy", energy_vals)
        re_rows, re_tech = _mk("REALESTATE", "Real Estate", re_vals)
        updates = _run_with_mocked_rows(energy_rows + re_rows, energy_tech + re_tech)
        # ENERGY_14 and REALESTATE_14 both carry the identical raw momentum_3m=20.0.
        assert updates["REALESTATE_14"][0] > updates["ENERGY_14"][0], (
            f"REALESTATE_14={updates['REALESTATE_14'][0]} ENERGY_14={updates['ENERGY_14'][0]}: identical raw "
            "momentum_3m should score higher relative to a weaker (Real Estate) peer group than a stronger "
            "(Energy) one - this is the entire point of sector-neutral z-scoring"
        )


class TestMomentumMinWeightFloorPreserved:
    def test_symbol_with_only_one_of_four_slots_withheld_not_saturated(self) -> None:
        """MOMENTUM_MIN_WEIGHT=0.40 (2/4 slots) must still gate the sector-neutral pass exactly
        as it gated Pass 1 - a symbol with only momentum_3m available (1/4 slots = 0.25 weight)
        must get momentum_score=None (withheld), not a thin-sample extrapolation."""
        rows = [
            _row("THIN", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, None, 40.0, None, "Technology"),
            _row("PEER_A", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, 10.0, 20.0, "Technology"),
            _row("PEER_B", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, 20.0, 40.0, "Technology"),
        ]
        tech_rows = [
            _tech_row("PEER_A", 50.0, 1.0, 100.0, 100.0, 102.0),
            _tech_row("PEER_B", 55.0, 1.0, 100.0, 100.0, 104.0),
        ]
        updates = _run_with_mocked_rows(rows, tech_rows)
        assert "THIN" in updates
        assert updates["THIN"][0] is None, f"expected momentum_score withheld (None), got {updates['THIN'][0]}"


class TestIdempotentAcrossRepeatedRuns:
    def test_re_running_with_the_prior_runs_output_as_input_produces_no_further_change(self) -> None:
        """Same non-idempotence bug class already fixed for Value/Quality/Growth's batch passes -
        verify momentum_score/composite_score aren't read back as inputs here either."""
        rows = [
            _row("A", 999.0, 999.0, 55.0, 50.0, 50.0, 45.0, {}, 99.99, False, 2.0, 25.0, 50.0, "Technology"),
            _row("B", 999.0, 999.0, 60.0, 45.0, 55.0, 40.0, {}, 99.99, False, -1.0, -5.0, -10.0, "Technology"),
            _row("C", 999.0, 999.0, 40.0, 35.0, 35.0, 30.0, {}, 99.99, False, 5.0, 60.0, 90.0, "Technology"),
        ]
        tech_rows = [
            _tech_row("A", 65.0, 1.0, 100.0, 100.0, 108.0),
            _tech_row("B", 30.0, -1.0, 100.0, 100.0, 95.0),
            _tech_row("C", 80.0, 1.0, 100.0, 100.0, 115.0),
        ]

        first_pass = _run_with_mocked_rows(rows, tech_rows)
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
            )
            for r in rows
        ]
        second_pass = _run_with_mocked_rows(rows_after_1, tech_rows)

        assert second_pass == {}, (
            "re-running with unchanged raw inputs and the prior run's own output must not change "
            f"momentum_score/composite_score again (got {second_pass})"
        )


class TestMacdSignNotMagnitude:
    def test_macd_scored_by_sign_only_not_raw_magnitude(self) -> None:
        """Pass-1 restricts MACD to sign-only (not comparable across symbols at different price
        levels) - the sector-neutral pass must preserve that: a $500-scale stock with a huge
        positive raw MACD must not out-score a $10-scale stock with a tiny positive raw MACD on
        that account, since both get raw_macd_sign=+1.0 identically before z-scoring."""
        rows = [
            _row("BIGPRICE", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, 10.0, 20.0, "Technology"),
            _row("SMALLPRICE", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, 10.0, 20.0, "Technology"),
            _row("PEER", 999.0, 999.0, 50.0, 50.0, 50.0, 50.0, {}, 99.99, False, 2.0, 10.0, 20.0, "Technology"),
        ]
        tech_rows = [
            _tech_row("BIGPRICE", 50.0, 25.0, 500.0, 500.0, 510.0),  # huge positive raw MACD
            _tech_row("SMALLPRICE", 50.0, 0.05, 10.0, 10.0, 10.2),  # tiny positive raw MACD
            _tech_row("PEER", 50.0, -1.0, 100.0, 100.0, 98.0),  # negative raw MACD
        ]
        updates = _run_with_mocked_rows(rows, tech_rows)
        assert updates["BIGPRICE"][0] == updates["SMALLPRICE"][0], (
            "identical MACD SIGN (both positive) with everything else equal must score identically "
            f"regardless of raw magnitude - got BIGPRICE={updates['BIGPRICE'][0]} "
            f"SMALLPRICE={updates['SMALLPRICE'][0]}"
        )

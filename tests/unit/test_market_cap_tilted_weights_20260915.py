"""Tests for update_market_cap_tilted_weights() (loaders/stock_scores/market_cap_tilt.py,
added 2026-09-15) - the batch pass that computes display-only market-cap-tilted weights for
stock_scores' 6 *_tilted_weight columns (migration 1294).

Context: replaces request-time tilt computation duplicated across two API endpoints (only one
of which got the fix), matching how real institutional multi-factor index providers (Goldman
ActiveBeta) compute their factor-tilted construction once on a schedule rather than
live-recomputing a formula per consumer. See market_cap_tilt.py's own module docstring for the
full rationale.

Test structure mirrors tests/unit/test_momentum_sector_relative_mom_12_1_20260915.py (same
mocked-DB-row pattern via loader.__new__ + patched DatabaseContext/execute_values).
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(
    symbol: str,
    composite_score: float | None,
    momentum_score: float | None,
    quality_score: float | None,
    value_score: float | None,
    growth_score: float | None,
    risk_score: float | None,
    market_cap: float | None,
) -> tuple[str | float | None, ...]:
    """Matches update_market_cap_tilted_weights()'s own SELECT column order exactly: symbol,
    composite_score, momentum_score, quality_score, value_score, growth_score, risk_score,
    market_cap."""
    return (symbol, composite_score, momentum_score, quality_score, value_score, growth_score, risk_score, market_cap)


def _run_with_mocked_rows(rows: list[tuple[str | float | None, ...]]) -> dict[str, tuple[float | None, ...]]:
    """Run update_market_cap_tilted_weights() against a fully mocked DB returning `rows` for
    the SELECT, and return {symbol: (composite, momentum, quality, value, growth, risk)_tilted_
    weight} from the UPDATE, or {} if no UPDATE was issued."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with (
        patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx,
        patch("loaders.load_stock_scores.execute_values") as mock_execute_values,
    ):
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        loader.update_market_cap_tilted_weights()
    if not mock_execute_values.called:
        return {}
    _cur_arg, _sql, updates = mock_execute_values.call_args[0][:3]
    return {row[0]: row[1:] for row in updates}


class TestMarketCapTiltedWeights:
    def test_larger_market_cap_gets_larger_tilted_weight_at_equal_score(self) -> None:
        """Basic sanity: three symbols with identical composite_score (same z, same tilt
        multiplier for all three) must rank by market_cap alone - the pure cap-weighting
        behavior at a fixed tilt. A 4th differently-scored symbol is included purely so the
        population has nonzero variance (stdev=0 would otherwise make the z-score/tilt
        undefined and this pass correctly skips that degenerate case, same as every sibling
        z-score pass)."""
        rows = [
            _row("BIG", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 100_000_000_000.0),
            _row("SMALL", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 1_000_000_000.0),
            _row("MID", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
            _row("OTHER", 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 10_000_000_000.0),
        ]
        result = _run_with_mocked_rows(rows)
        big, mid, small = result["BIG"][0], result["MID"][0], result["SMALL"][0]
        assert big is not None and mid is not None and small is not None
        assert big > mid > small

    def test_higher_score_tilts_weight_up_at_equal_market_cap(self) -> None:
        """Two symbols with identical market_cap must rank by composite_score - the factor-tilt
        behavior on top of the cap-weighted base."""
        rows = [
            _row("GOOD", 90.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
            _row("BAD", 10.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
            _row("MID", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
        ]
        result = _run_with_mocked_rows(rows)
        good, mid, bad = result["GOOD"][0], result["MID"][0], result["BAD"][0]
        assert good is not None and mid is not None and bad is not None
        assert good > mid > bad

    def test_missing_market_cap_gets_null_tilted_weight_not_fabricated(self) -> None:
        """A symbol with no market_cap gets NULL for every *_tilted_weight column - never a
        fallback/fabricated value, same 'skip what's unavailable' principle as every other
        pillar batch pass."""
        rows = [
            _row("HASCAP", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
            _row("NOCAP", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, None),
            _row("OTHER", 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 10_000_000_000.0),
        ]
        result = _run_with_mocked_rows(rows)
        assert result["NOCAP"] == (None, None, None, None, None, None)
        assert result["HASCAP"][0] is not None

    def test_missing_pillar_score_gets_null_for_just_that_columns_weight(self) -> None:
        """A symbol missing only one pillar's score (e.g. no growth_score) gets NULL for just
        that pillar's tilted weight - the other 5 columns are computed independently, not
        all-or-nothing."""
        rows = [
            _row("FULL", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0),
            _row("NOGROWTH", 50.0, 50.0, 50.0, 50.0, None, 50.0, 10_000_000_000.0),
            _row("OTHER", 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 10_000_000_000.0),
        ]
        result = _run_with_mocked_rows(rows)
        # composite_tilted_weight, momentum, quality, value, growth, risk
        assert result["NOGROWTH"][4] is None  # growth_tilted_weight
        assert result["NOGROWTH"][0] is not None  # composite_tilted_weight still computed
        assert result["NOGROWTH"][3] is not None  # value_tilted_weight still computed

    def test_no_eligible_rows_skips_without_update(self) -> None:
        result = _run_with_mocked_rows([])
        assert result == {}

    def test_single_symbol_population_produces_no_signal_not_a_crash(self) -> None:
        """A population of 1 has no variance to standardize against - must not raise
        (ZeroDivisionError/stdev=0 guard), and should just skip that column's tilt (or leave
        weight computed off a degenerate/no z-score), not fabricate a number."""
        rows = [_row("ONLY", 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 10_000_000_000.0)]
        # Should not raise.
        result = _run_with_mocked_rows(rows)
        # With <2 values, every column's z-score population is too thin to trust - all NULL.
        assert result == {} or result.get("ONLY") == (None, None, None, None, None, None)

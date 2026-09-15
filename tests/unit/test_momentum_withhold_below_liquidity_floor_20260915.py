"""Tests for MomentumScoringMixin._withhold_momentum_below_floor() (loaders/stock_scores/
momentum_scoring.py).

ADDED 2026-09-15 (/goal session, user directive: filtering belongs in the scoring pipeline,
never bolted onto the display or API layer). Before this fix, a symbol below the liquidity
floor (or excluded by NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) never reached
update_momentum_sector_relative_mom_12_1()'s own correction population, so it kept Pass 1's
raw, potentially-saturated _pct_to_score curve value in stock_scores forever - live-confirmed
WHG (Westwood Holdings, sub-$500K ADV) pegged at momentum_score=100.00. A first attempt hid
this at the display layer (algo/signals/investable_universe.py) and was reverted; this method
is the real, scoring-pipeline-side fix - it withholds (NULLs) momentum_score for exactly that
complement population instead.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(
    symbol: str,
    composite_score: float,
    quality_score: float | None,
    growth_score: float | None,
    value_score: float | None,
    risk_score: float | None,
    components: dict | None,
    data_completeness: float | None,
    data_unavailable: bool,
) -> tuple:
    """Matches _withhold_momentum_below_floor()'s own SELECT column order exactly: symbol,
    composite_score, quality_score, growth_score, value_score, risk_score, components,
    data_completeness, data_unavailable."""
    return (
        symbol,
        composite_score,
        quality_score,
        growth_score,
        value_score,
        risk_score,
        components if components is not None else {},
        data_completeness,
        data_unavailable,
    )


def _run(rows: list[tuple]) -> list[tuple]:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    with patch("loaders.load_stock_scores.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = mock_cur
        loader = L.__new__(L)
        return loader._withhold_momentum_below_floor()


class TestWithholdBelowFloor:
    def test_withholds_momentum_score_to_none(self) -> None:
        rows = [_row("WHG", 73.96, 64.42, 60.30, 94.97, 50.10, {"momentum": 100.0}, 99.99, False)]
        withheld = _run(rows)
        assert len(withheld) == 1
        symbol, momentum_score_new, _composite, _components, _dc, _du = withheld[0]
        assert symbol == "WHG"
        assert momentum_score_new is None

    def test_composite_score_recomputed_without_momentum(self) -> None:
        """quality=64.42/growth=60.30/value=94.97/risk=50.10, momentum dropped entirely -
        composite must be a real recompute off the remaining 4 pillars, not the stale value."""
        rows = [_row("WHG", 73.96, 64.42, 60.30, 94.97, 50.10, {}, 99.99, False)]
        withheld = _run(rows)
        _symbol, _momentum, composite_new, _components, _dc, _du = withheld[0]
        assert composite_new != 73.96
        assert 0.0 <= composite_new <= 100.0

    def test_components_json_momentum_key_nulled(self) -> None:
        import json

        rows = [_row("WHG", 73.96, 64.42, 60.30, 94.97, 50.10, {"momentum": 100.0, "value": 94.97}, 99.99, False)]
        withheld = _run(rows)
        _symbol, _momentum, _composite, components_json, _dc, _du = withheld[0]
        components = json.loads(components_json)
        assert components["momentum"] is None
        assert components["value"] == 94.97

    def test_empty_population_returns_empty_list(self) -> None:
        assert _run([]) == []

    def test_data_completeness_drops_when_momentum_withheld(self) -> None:
        """A symbol with all 5 pillars previously complete (99.99%) drops below 100% once
        momentum is withheld - data_completeness must reflect only the 4 remaining pillars."""
        rows = [_row("WHG", 73.96, 64.42, 60.30, 94.97, 50.10, {}, 99.99, False)]
        withheld = _run(rows)
        _symbol, _momentum, _composite, _components, data_completeness_new, _du = withheld[0]
        assert data_completeness_new < 99.99

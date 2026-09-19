#!/usr/bin/env python3
"""Regression test: negative raw beta must never be clamped to 0 before z-scoring
(loaders/stock_scores/risk_scoring.py, `_compute_risk_absolute_zscore_percentiles`'s beta leg).

Before the original 2026-08-28/29 fix, `beta = max(0, metrics["beta"])` collapsed every
negative beta to the same input value (0), so ALL negative-beta symbols got an identical
score. Beta is a signed regression coefficient (unlike volatility, which is a magnitude and
correctly floor-clipped elsewhere) - a wildly anti-correlated beta should score DIFFERENTLY
from a mildly negative one, not identically.

AQR PIVOT 2026-09-17, then REVERTED 2026-09-19 (see risk_scoring.py's own module docstring for
the full evidence trail - live TOP/BVC bad-print Safety-leaderboard inversion, explicit user
directive to put every pillar back on one consistent MSCI/Barra methodology). Risk is back to
its pre-pivot 3-component construction (volatility_60d/cmra_12m/beta, equal-weighted 1/3 each),
scored by the real winsorize+z-score batch pass (`update_risk_absolute_zscore_scores`), not by
a Pass-1 hand-tuned curve - Pass-1 (`_score_risk`) is now a flat NEUTRAL_PLACEHOLDER_SCORE
placeholder for every present, reliable field (matching value_metrics.py's own post-revert
convention) and no longer differentiates by input VALUE at all, only by which fields are
present. The "don't clip negative beta before scoring" property this file guards now lives in
the batch pass instead: `_compute_risk_absolute_zscore_percentiles` negates each raw beta
before z-scoring without clamping to >=0 first, so a more-negative beta gets a more-favorable
(higher) z-score, not an identical one.
"""

from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader as L


def _row(symbol: str, beta: float | None, avg_dollar_volume_20d: float = 5_000_000.0) -> tuple:
    """Matches _fetch_risk_absolute_zscore_rows' real SELECT shape: symbol, risk_score,
    composite_score, quality_score, growth_score, value_score, momentum_score, components,
    data_completeness, data_unavailable, avg_dollar_volume_20d, volatility_60d, market_cap,
    cmra_12m, beta. volatility_60d/cmra_12m are pinned to a fixed, identical-across-symbols
    value (not None) so every symbol clears RISK_MIN_WEIGHT_AVAILABLE (needs >=2 of 3
    components) while only the `beta` leg actually varies between symbols under test."""
    return (
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
        avg_dollar_volume_20d,
        0.5,
        1_000_000_000.0,
        0.5,
        beta,
    )


def _run_with_mocked_rows(rows: list[tuple]) -> dict[str, tuple[float | None, float]]:
    mock_cur = MagicMock()
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


class TestRiskNegativeBetaNotClipped:
    def test_negative_beta_values_score_distinctly_not_clamped_to_zero(self):
        """A more-negative beta must score STRICTLY higher than a mildly-negative one - if beta
        were clamped to 0 before z-scoring, MILD/MODERATE/EXTREME would all score identically
        (all mapping to the same clamped 0)."""
        rows = [
            _row("MILD", beta=-0.05),
            _row("MODERATE", beta=-0.5),
            _row("EXTREME", beta=-9.97),
            *[_row(f"PEER{i}", beta=1.0 + i * 0.1) for i in range(15)],
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["EXTREME"][0] > updates["MODERATE"][0] > updates["MILD"][0], (
            f"expected strictly increasing scores for more-negative beta, got "
            f"MILD={updates['MILD'][0]} MODERATE={updates['MODERATE'][0]} EXTREME={updates['EXTREME'][0]}"
        )

    def test_negative_beta_scores_above_zero_beta(self):
        """A negative beta must score strictly higher than beta=0.0 - it's the real, more
        desirable (lower) direction, not floored to the same value as 0."""
        rows = [
            _row("NEG", beta=-0.5),
            _row("ZERO", beta=0.0),
            *[_row(f"PEER{i}", beta=1.0 + i * 0.1) for i in range(15)],
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["NEG"][0] > updates["ZERO"][0]

    def test_lower_beta_scores_higher_than_higher_beta(self):
        """Direct low-beta-anomaly check: a lower positive beta must score strictly HIGHER than
        a higher one."""
        rows = [
            _row("LOW_BETA", beta=0.5),
            _row("HIGH_BETA", beta=2.0),
            *[_row(f"PEER{i}", beta=1.0 + i * 0.1) for i in range(15)],
        ]
        updates = _run_with_mocked_rows(rows)
        assert updates["LOW_BETA"][0] > updates["HIGH_BETA"][0]

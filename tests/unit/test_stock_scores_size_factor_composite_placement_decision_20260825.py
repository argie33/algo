"""Regression/documentation test for the Size-factor composite-placement decision (real-money-
readiness goal session, stock_scores multi-pillar re-audit) - now pinning the 2026-08-27
re-promotion, the third flip of this same decision.

TIMELINE:
- 2026-08-25: Size (market cap, Fama-French SMB / Banz 1981) found completely absent from all
  6 stock_scores pillars, tested standalone at t=-5.37 (150 months 2014-2026, median 2,601
  symbols), implemented as a 20%-weighted sub-component inside the Value pillar (commit
  2d77f7bfd) - not a top-level pillar.
- 2026-08-26: promoted to a real top-level 7th pillar (20% weight, the other 6 pillars scaled
  x0.8 preserving relative proportions) after size_proxy repeatedly tested at t=7.63
  multivariate, more than 3x every other pillar's own coefficient (commit 869e431c3). Schema
  (stock_scores.size_score), API, and frontend all updated the same commit.
- 2026-08-26 (same day, later): REMOVED entirely (user directive) - a UX/product objection to
  seeing market cap on the scores page, not a dispute of the evidence ("not sure why market cap
  still lingering on our scores page we dont want it included there"). `_score_size` was
  deleted, BASE_PILLAR_WEIGHTS reverted to its pre-promotion values, and the API/frontend
  wiring was rolled back. The stock_scores.size_score column itself was left in the schema
  (unused) rather than migrated away.
- 2026-08-27: RE-PROMOTED to a top-level pillar again (20% weight, the other 5 - Positioning
  having been separately retired in the interim - scaled x0.8), on explicit user direction
  after the evidence cleared a bar it had never actually been tested against: an era-robust
  half-split (t=4.62 first half 2017-2021, t=5.68 second half 2022-2026 - genuinely stable,
  not just a repeated point-estimate on a growing sample). See
  loaders/load_stock_scores.py's _score_size docstring for the full evidence trail.

This test now pins the CURRENT state: Size IS a top-level pillar again, `_score_size` exists
and reads `market_cap` off the Value pillar's upstream value_metrics row.

- 2026-08-28: weight CUT 0.20 -> 0.08 (still a top-level pillar, not removed again) - the
  composite-weights regression this promotion cited (size_proxy t=7.63/t=7.38-7.39 depending on
  the run) was found to rely on 0-imputing missing pillar data for symbols with thin SEC
  fundamentals coverage, a population that correlates with market cap (size_proxy is essentially
  never missing while quality/growth/value often are for the same small-cap names). A rebuilt
  version of that script adding a strict complete-case (no-imputation) regime found size_proxy
  collapses to t=1.80-1.81 (not significant) there - only growth_proxy and value_proxy stayed
  significant in BOTH regimes. Freed 0.12 moved to growth (0.14->0.20) and value (0.17->0.23).
  See loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS docstring for the full evidence trail.
"""

import inspect

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, StockScoresLoader


class TestSizeFactorRePromotedToComposite:
    def test_base_weights_has_size_key(self) -> None:
        """BASE_PILLAR_WEIGHTS must have a top-level 'size' key - the 2026-08-27 re-promotion
        decision - until this gets deliberately revisited again. Weight cut to 0.08 on
        2026-08-28 (still a top-level key, see module docstring) after complete-case testing
        found the original 0.20 was based on an imputation artifact."""
        assert "size" in BASE_PILLAR_WEIGHTS
        assert BASE_PILLAR_WEIGHTS["size"] == 0.08

    def test_base_weights_sum_to_one_with_size(self) -> None:
        assert abs(sum(BASE_PILLAR_WEIGHTS.values()) - 1.0) < 1e-9

    def test_score_size_method_exists(self) -> None:
        assert hasattr(StockScoresLoader, "_score_size")

    def test_score_size_reads_market_cap(self) -> None:
        source = inspect.getsource(StockScoresLoader._score_size)
        assert 'metrics.get("market_cap")' in source or 'metrics["market_cap"]' in source

    def test_no_other_scorer_reads_market_cap(self) -> None:
        """market_cap must be read only by _score_size, not reintroduced as a sub-component of
        any other pillar (e.g. folded back into Value) - it's a standalone top-level pillar,
        not a weighted blend input elsewhere. Checks actual metrics.get("market_cap")/
        metrics["market_cap"] reads, not a raw substring match - comments are allowed to
        mention market_cap by name without tripping this guard."""
        for method_name in (
            "_score_value",
            "_score_quality",
            "_score_growth",
            "_score_risk",
            "_score_momentum",
        ):
            source = inspect.getsource(getattr(StockScoresLoader, method_name))
            assert 'metrics.get("market_cap")' not in source and 'metrics["market_cap"]' not in source, (
                f"{method_name} reads metrics market_cap - Size is its own top-level pillar "
                "(_score_size) and market_cap must not also be scored as a sub-component elsewhere."
            )

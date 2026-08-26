"""Regression/documentation test for the Size-factor composite-placement decision (real-money-
readiness goal session, stock_scores multi-pillar re-audit) - superseding the 2026-08-25 "keep
Size inside Value" call with a 2026-08-26 promotion to a real top-level 7th pillar.

TIMELINE:
- 2026-08-25: Size (market cap, Fama-French SMB / Banz 1981) found completely absent from all
  6 stock_scores pillars, tested standalone at t=-5.37 (150 months 2014-2026, median 2,601
  symbols), implemented as a 20%-weighted sub-component inside the Value pillar (commit
  2d77f7bfd) - not a top-level pillar.
- 2026-08-25 (same day, follow-up): extended algo/research/fama_macbeth_composite_weights.py
  to test log(market_cap) as a 7th top-level factor. First attempt (t=0.47/0.86, not
  significant) was later found to be underpowered by the same sample-selection bias already
  flagged for the base_weights test. A same-day corrected re-run, once double-counting between
  size_proxy and value_proxy's own Size sub-component was removed (value_proxy_nosize
  decomposition), found size_proxy t=7.62/7.63 - dramatically stronger than every other
  pillar's own coefficient (next-best: stability at t=2.37) - but was deliberately NOT acted
  on: promoting Size is a DB schema/API/frontend commitment, flagged for explicit user
  involvement rather than silently overridden.
- 2026-08-26: re-verified live one more time (`python -m algo.research.fama_macbeth_composite_weights`)
  and reproduced the identical t=7.63 multivariate / t=4.44 univariate result on 110 months,
  median 6,505 symbols - the 4th independent confirmation across 2 days, more than 3x every
  other pillar. ACTED ON: Size promoted to a real top-level 7th pillar (20% weight, the other
  6 pillars scaled x0.8 preserving relative proportions). Schema (stock_scores.size_score,
  migration 1230), API (lambda/api/routes/scores.py), and frontend (StockDetail.jsx,
  StockScoreAccordion.jsx, ScoresDashboard.jsx) all updated the same commit.

This test now pins the OPPOSITE of what it pinned on 2026-08-25: that Size IS a top-level
pillar (not silently demoted back to a Value sub-component) and that _score_value no longer
computes it (not silently double-counted by reintroducing it there too).
"""

import inspect

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, StockScoresLoader


class TestSizeFactorCompositePlacementDecision:
    def test_base_weights_has_top_level_size_key(self) -> None:
        """BASE_PILLAR_WEIGHTS must have a top-level 'size' key - the 2026-08-26 promotion
        decision - until this gets deliberately revisited again."""
        assert "size" in BASE_PILLAR_WEIGHTS
        assert abs(BASE_PILLAR_WEIGHTS["size"] - 0.20) < 1e-9

    def test_base_weights_sum_to_one_with_size(self) -> None:
        assert abs(sum(BASE_PILLAR_WEIGHTS.values()) - 1.0) < 1e-9

    def test_score_value_no_longer_computes_size(self) -> None:
        """_score_value must not compute Size internally anymore - it would double-count
        against the new top-level size_score pillar."""
        source = inspect.getsource(StockScoresLoader._score_value)
        assert "market_cap" not in source, (
            "_score_value still references market_cap - Size was promoted to its own "
            "top-level pillar (_score_size) and must be fully removed from _score_value to "
            "avoid double-counting the same signal in the composite."
        )

    def test_score_size_method_exists_and_reads_market_cap(self) -> None:
        assert hasattr(StockScoresLoader, "_score_size")
        source = inspect.getsource(StockScoresLoader._score_size)
        assert "market_cap" in source

"""Regression/documentation test for the Size-factor composite-placement decision (real-money-
readiness goal session, stock_scores multi-pillar re-audit) - superseding the 2026-08-26
"promote Size to a top-level 7th pillar" call with a same-day removal (user directive).

TIMELINE:
- 2026-08-25: Size (market cap, Fama-French SMB / Banz 1981) found completely absent from all
  6 stock_scores pillars, tested standalone at t=-5.37 (150 months 2014-2026, median 2,601
  symbols), implemented as a 20%-weighted sub-component inside the Value pillar (commit
  2d77f7bfd) - not a top-level pillar.
- 2026-08-26: promoted to a real top-level 7th pillar (20% weight, the other 6 pillars scaled
  x0.8 preserving relative proportions) after size_proxy repeatedly tested at t=7.63
  multivariate, more than 3x every other pillar's own coefficient (commit 869e431c3). Schema
  (stock_scores.size_score), API, and frontend all updated the same commit.
- 2026-08-26 (same day, later): REMOVED entirely (user directive) - market cap is not a scored
  input at all anymore, whether as its own pillar or folded back into Value. `_score_size` was
  deleted, BASE_PILLAR_WEIGHTS reverted to its pre-promotion 6-pillar values, and the API/
  frontend wiring (allowed_sorts, FACTOR_WEIGHTS, SIZE_SCHEMA/FACTORS entries) was rolled back.
  The stock_scores.size_score column itself is left in the schema (unused) rather than
  migrated away.

This test now pins the OPPOSITE of what it pinned right after the 2026-08-26 promotion: that
Size is NOT a top-level pillar, `_score_size` does not exist, and neither `_score_value` nor
any other scorer reads `market_cap`.
"""

import inspect

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, StockScoresLoader


class TestSizeFactorRemovedFromComposite:
    def test_base_weights_has_no_size_key(self) -> None:
        """BASE_PILLAR_WEIGHTS must not have a top-level 'size' key - the 2026-08-26 removal
        decision - until this gets deliberately revisited again."""
        assert "size" not in BASE_PILLAR_WEIGHTS

    def test_base_weights_sum_to_one_without_size(self) -> None:
        assert abs(sum(BASE_PILLAR_WEIGHTS.values()) - 1.0) < 1e-9

    def test_score_size_method_removed(self) -> None:
        assert not hasattr(StockScoresLoader, "_score_size")

    def test_no_scorer_reads_market_cap(self) -> None:
        """market_cap must not be a scored input anywhere - not in _score_value (its
        pre-promotion home) and not reintroduced elsewhere as a substitute for the removed
        Size pillar. Checks actual metrics.get("market_cap")/metrics["market_cap"] reads, not
        a raw substring match - comments are allowed to mention market_cap by name (e.g. to
        document that it's deliberately unused) without tripping this guard."""
        for method_name in (
            "_score_value",
            "_score_quality",
            "_score_growth",
            "_score_positioning",
            "_score_risk",
            "_score_momentum",
        ):
            source = inspect.getsource(getattr(StockScoresLoader, method_name))
            assert 'metrics.get("market_cap")' not in source and 'metrics["market_cap"]' not in source, (
                f"{method_name} reads metrics market_cap - Size was removed from scoring entirely "
                "2026-08-26 (user directive) and must not be reintroduced anywhere."
            )

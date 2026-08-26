"""Regression/documentation test for a 2026-08-25 decision (real-money-readiness goal
session, follow-up on the stock_scores multi-pillar re-audit): whether the Size factor
(market cap, Fama-French SMB / Banz 1981) should be promoted from a Value-pillar
sub-component to its own top-level composite pillar.

Size was found completely absent from all 6 stock_scores pillars, tested standalone at
t=-5.37 (150 months 2014-2026, median 2,601 symbols), and implemented as a 20%-weighted
sub-component inside the Value pillar (commit 2d77f7bfd) - not a top-level 7th pillar.

Follow-up: algo/research/fama_macbeth_composite_weights.py was extended to test log(market_cap)
as a 7th factor in the SAME multivariate regression used to test the 6 top-level base_weights.
Result: t=0.47 multivariate, t=0.86 univariate - not significant. This is NOT a reversal of the
standalone t=-5.37 finding: the composite-level regression requires all 6 pillars' data
simultaneously, which drops the median cross-section from ~2,601 to 850 and skews toward
larger, more-established names - exactly the population where the size premium is weakest.
A null result on that structurally-biased sample doesn't disprove Size's signal.

DECISION: do NOT promote Size to a top-level 7th pillar - not because the idea is wrong, but
because the one test that could justify that larger schema/API/frontend commitment is
underpowered with current data reconstruction. See _compute_stock_score's "SIZE FACTOR -
RESOLVED" comment in loaders/load_stock_scores.py for the full writeup.

This test pins the current state (Size lives only inside Value, base_weights has no top-level
size/size_proxy key) so a future silent change is caught and this decision gets deliberately
revisited, not silently invalidated.
"""

import inspect

from loaders.load_stock_scores import StockScoresLoader


class TestSizeFactorCompositePlacementDecision:
    def test_base_weights_has_no_top_level_size_key(self) -> None:
        """base_weights (the 6 top-level pillar shares) must not gain a 'size' key without
        deliberately revisiting this decision."""
        source = inspect.getsource(StockScoresLoader._compute_stock_score)
        assert '"quality":' in source and '"growth":' in source and '"value":' in source
        assert '"size":' not in source, (
            "base_weights now has a top-level 'size' key - the 2026-08-25 decision to keep "
            "Size inside the Value pillar only (not promote it) has been changed. Update this "
            "test and the 'SIZE FACTOR - RESOLVED' comment in _compute_stock_score to match "
            "the new reality, and confirm the promotion was backed by a properly-powered test "
            "(not the same underpowered composite-sample regression that originally motivated "
            "keeping it inside Value)."
        )

    def test_value_score_docstring_still_documents_size_subcomponent(self) -> None:
        """_score_value's docstring must still describe Size as a weighted sub-component -
        confirms Size's real, tested signal (t=-5.37) stays represented somewhere even though
        it's not a top-level pillar."""
        source = inspect.getsource(StockScoresLoader._score_value)
        assert "SIZE" in source and "market cap" in source.lower()

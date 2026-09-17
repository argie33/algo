#!/usr/bin/env python3
"""Regression test for StockScoresLoader._pct_to_score (loaders/stock_scores/momentum_scoring.py).

WEAK-MOMENTUM "DEAD ZONE" REMOVED 2026-09-16 (factor-purity sweep, see _pct_to_score's own
docstring in momentum_scoring.py): the old -3%..+3% "insufficient conviction" exclusion had no
counterpart in any published momentum construction (MSCI/Carhart/Jegadeesh-Titman all
z-score/rank the full continuous distribution, including near-zero returns) - it was an
invented threshold, not industry methodology, so it was removed.

REPLACED WITH A FLAT NEUTRAL PLACEHOLDER 2026-09-17 (factor-purity follow-up, "get rid of it"
not just verify it's inert - see _pct_to_score's own docstring for the full live-audit
evidence). The linear -20%/+20%->0/100 mapping this file used to pin exactly was ITSELF
hand-set with no cited source, and proven to never survive as momentum_score's live value (the
real universe-wide z-score computed by update_momentum_sector_relative_mom_12_1() always
overwrites it) - `_pct_to_score` now returns a flat 50.0 for any input, matching the identical
treatment already applied to Value's PE/PB curves, Quality's ROE/D2E/earnings-variability
curves, Growth's `_score_single_growth`, and Risk's volatility/CMRA curves this same session.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestPctToScoreIsNeutralPlaceholder:
    def test_every_input_returns_flat_neutral_placeholder(self) -> None:
        for pct in (-200.0, -20.0, -5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0, 20.0, 200.0):
            assert StockScoresLoader._pct_to_score(pct) == 50.0, (
                f"{pct}% must score the flat NEUTRAL_PLACEHOLDER_SCORE (50.0), not a curve"
            )

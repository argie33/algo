"""Regression test for a within-factor sign-inversion bug in
algo/risk/market_exposure.py::MarketExposure._ad_line, found 2026-08-23 (goal:
exposure-model integrity review, user-prompted).

_ad_line's "confirming" branch used to score 100.0 (the composite's best possible reading)
for BOTH directions of agreement between the A/D line and SPY - including ad_change<0 AND
spy_change_pct<0, i.e. breadth deteriorating alongside a falling SPY: a real, broad-based
selloff, not index-level noise. A confirmed downtrend is a MORE reliable bearish signal than
a mere divergence (the same "confirmation = higher conviction" logic this factor already
applied correctly on the bullish side, where bullish-confirming outscores the 60pt hidden-
bullish-divergence case) - so it must score below bearish_divergence (30), not tied with
bullish-confirming at the very top of the scale.

Every prior audit pass in this file's history checked cross-factor redundancy (is factor A
double-counting factor B); this bug slipped through because it's a within-factor sign error
instead - a mechanism built correctly for one direction (bullish) silently mis-scoring its
mirror-image case (bearish), never caught until this pass looked at each factor's own
scoring curve rather than only pairwise correlations.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from algo.risk.market_exposure import MarketExposure


def _ad_line_rows(ratios, spy_closes):
    """(date, advance_decline_ratio, spy_close) rows, ascending by date (oldest first) -
    matches _ad_line's `ORDER BY mh.date ASC` query.
    """
    base = date(2026, 7, 1)
    return [(base + timedelta(days=i), ratios[i], spy_closes[i]) for i in range(len(ratios))]


class TestAdLineDirectionalScoring:
    def test_bearish_confirming_scores_worse_than_bearish_divergence(self):
        # Breadth deteriorating (ratio falling 1.5 -> 0.6) AND SPY falling: a real,
        # broad-based decline - must NOT score as well as a mere bearish divergence.
        cur = MagicMock()
        ratios = [1.5, 1.3, 1.1, 0.9, 0.7, 0.6]
        spy_closes = [460.0, 458.0, 455.0, 452.0, 450.0, 445.0]
        cur.fetchall.return_value = _ad_line_rows(ratios, spy_closes)
        me = MarketExposure()
        confirming = me._ad_line(date(2026, 7, 10), cur)

        cur2 = MagicMock()
        # Breadth deteriorating while SPY still grinds higher (rally not broadly supported).
        spy_closes_up = [450.0, 451.0, 452.0, 453.0, 455.0, 460.0]
        cur2.fetchall.return_value = _ad_line_rows(ratios, spy_closes_up)
        divergence = me._ad_line(date(2026, 7, 10), cur2)

        assert confirming["relation"] == "bearish_confirming"
        assert divergence["relation"] == "bearish_divergence"
        assert confirming["score"] < divergence["score"], (
            "A confirmed broad-based decline (breadth + price both falling) must score "
            "worse than a mere bearish divergence, not tie/beat it."
        )

    def test_bullish_confirming_still_scores_best(self):
        cur = MagicMock()
        ratios = [0.6, 0.8, 1.0, 1.2, 1.4, 1.6]
        spy_closes = [450.0, 452.0, 454.0, 456.0, 458.0, 462.0]
        cur.fetchall.return_value = _ad_line_rows(ratios, spy_closes)
        me = MarketExposure()
        result = me._ad_line(date(2026, 7, 10), cur)
        assert result["relation"] == "bullish_confirming"
        assert result["score"] == 100.0

    def test_bearish_confirming_scores_worst_of_all_four_relations(self):
        me = MarketExposure()
        cur = MagicMock()

        # bullish_confirming
        cur.fetchall.return_value = _ad_line_rows(
            [0.6, 0.8, 1.0, 1.2, 1.4, 1.6], [450.0, 452.0, 454.0, 456.0, 458.0, 462.0]
        )
        bullish_confirming = me._ad_line(date(2026, 7, 10), cur)["score"]

        # bullish_divergence (hidden bullish)
        cur.fetchall.return_value = _ad_line_rows(
            [0.6, 0.8, 1.0, 1.2, 1.4, 1.6], [460.0, 458.0, 455.0, 452.0, 450.0, 445.0]
        )
        bullish_divergence = me._ad_line(date(2026, 7, 10), cur)["score"]

        # bearish_divergence
        cur.fetchall.return_value = _ad_line_rows(
            [1.5, 1.3, 1.1, 0.9, 0.7, 0.6], [450.0, 451.0, 452.0, 453.0, 455.0, 460.0]
        )
        bearish_divergence = me._ad_line(date(2026, 7, 10), cur)["score"]

        # bearish_confirming
        cur.fetchall.return_value = _ad_line_rows(
            [1.5, 1.3, 1.1, 0.9, 0.7, 0.6], [460.0, 458.0, 455.0, 452.0, 450.0, 445.0]
        )
        bearish_confirming = me._ad_line(date(2026, 7, 10), cur)["score"]

        assert bullish_confirming > bullish_divergence > bearish_divergence > bearish_confirming

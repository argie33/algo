#!/usr/bin/env python3
"""Regression test for StockScoresLoader._score_value's dividend_yield term
(loaders/load_stock_scores.py) - same bug class as the "UNPROFITABLE-COMPANY FLOOR ADDED
2026-08-28" / "UNPROFITABLE-FORECAST FLOOR ADDED 2026-08-28" fixes for P/E and Forward P/E.

value_metrics.dividend_yield is a REAL, already-computed 0.0 (not NULL) for non-dividend-paying
stocks - live-confirmed 2,850 of 5,111 universe symbols (56%), dividend_yield_unavailable_reason
='non_dividend_paying_stock', dividend_yield=0.0 exactly, never NULL. A `> 0` gate in both
_score_value's Pass-1 scoring and update_value_multiples_percentiles' recompute treated that
real, correctly-computed 0% yield exactly like missing data - silently reweighting the 11%
dividend term away onto PE/PB/PS/Forward P/E instead of scoring it at the floor (0% yield is
definitionally the worst end of any yield ranking). Fixed by changing the gate from `> 0` to
`is not None` in both places - div_score's own formula (min(100, div*16.7)) already floors
correctly at div=0 -> score=0 once the gate lets it through.
"""

from loaders.load_stock_scores import StockScoresLoader


class TestDividendYieldZeroFloor:
    def _base_metrics(self, dividend_yield) -> dict:
        return {"pe_ratio": 18.0, "pb_ratio": 2.0, "dividend_yield": dividend_yield}

    def test_zero_dividend_yield_is_scored_not_excluded(self):
        """A real 0.0 dividend_yield (non-dividend-paying stock) must count toward
        total_weight at the normal 0.11 weight, scored at the floor (0), not be silently
        reweighted away as if the field were missing."""
        loader = StockScoresLoader()

        payer = loader._score_value(self._base_metrics(0.03), "PAYER")
        non_payer = loader._score_value(self._base_metrics(0.0), "NONPAYER")

        assert isinstance(payer, float)
        assert isinstance(non_payer, float)
        # Same PE/PB inputs, only dividend_yield differs - a real payer must score
        # strictly higher than a real non-payer once the dividend term is correctly
        # floored (not equal, which would mean the term was skipped for both).
        assert non_payer < payer

    def test_zero_dividend_yield_differs_from_missing_dividend_yield(self):
        """A real 0.0 (non-payer, real data) and a missing/None value (genuinely
        unavailable, e.g. missing_sec_data) must NOT score identically - only the None
        case should reweight the term away entirely; the real 0.0 case must be scored at
        the floor and therefore score lower (or equal only in the degenerate case where
        PE/PB alone already floor value_score at 0)."""
        loader = StockScoresLoader()

        zero_metrics = self._base_metrics(0.0)
        missing_metrics = dict(self._base_metrics(0.0))
        missing_metrics["dividend_yield"] = None

        zero_score = loader._score_value(zero_metrics, "ZERO")
        missing_score = loader._score_value(missing_metrics, "MISSING")

        assert isinstance(zero_score, float)
        assert isinstance(missing_score, float)
        assert zero_score < missing_score

    def test_missing_dividend_yield_still_does_not_block_scoring(self):
        """A symbol with no dividend_yield at all (genuinely unavailable) must still get
        a real value score from its other available sub-components."""
        loader = StockScoresLoader()

        metrics = self._base_metrics(0.0)
        metrics["dividend_yield"] = None

        score = loader._score_value(metrics, "NO_DIV_DATA")

        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

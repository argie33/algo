#!/usr/bin/env python3
"""Regression test for the dividend payout-sustainability gate added to
StockScoresLoader._score_value (loaders/stock_scores/value_score.py), 2026-09-08
(real-money-readiness audit, memory: cato_value_trap_dividend_no_fcf_check_20260908).

Confirmed real gap: dividend_yield's scoring block only ever looked at yield magnitude - a
stock with a high yield funded by negative free cash flow (a classic value-trap pattern, e.g.
CATO scoring ~71.43 value on a ~21.5% yield backed by negative FCF) scored identically to an
equally-high yield backed by strong FCF coverage. fcf_yield was already fetched into `metrics`
but unused; dividend_yield/fcf_yield are both yield-on-price so their ratio is exactly the FCF
payout ratio (dividends/FCF) with price canceling - no new data source needed.

These tests guard: (1) a high yield funded by negative FCF scores LOWER on value_score than an
identical yield with healthy FCF coverage, (2) a well-covered dividend (payout ratio well under
1.0x) is NOT penalized at all, (3) missing fcf_yield leaves dividend_yield scored on magnitude
alone (fail-safe on missing data, same convention as the rest of this pillar), (4) a
non-dividend-paying stock (dividend_yield == 0) is unaffected regardless of fcf_yield.
"""

from loaders.load_stock_scores import StockScoresLoader
from loaders.stock_scores.value_score import _dividend_sustainability_factor


class TestDividendPayoutSustainabilityGate:
    def _base_metrics(self) -> dict:
        return {
            "pe_ratio": 15.0,
            "pb_ratio": 2.0,
            "ps_ratio": 3.0,
        }

    def test_negative_fcf_high_yield_scores_lower_than_covered_dividend(self):
        """The CATO pattern: same dividend_yield, but one is funded by negative FCF."""
        loader = StockScoresLoader()

        covered = dict(self._base_metrics(), dividend_yield=0.03, fcf_yield=0.10)
        uncovered = dict(self._base_metrics(), dividend_yield=0.03, fcf_yield=-0.03)

        covered_score = loader._score_value(covered, "COVERED")
        uncovered_score = loader._score_value(uncovered, "UNCOVERED")

        assert isinstance(covered_score, float)
        assert isinstance(uncovered_score, float)
        assert uncovered_score < covered_score

    def test_well_covered_dividend_not_penalized(self):
        """Payout ratio well under 1.0x (dividend_yield << fcf_yield) should score identically
        to having no fcf_yield data at all - the gate must not fire on a healthy dividend."""
        loader = StockScoresLoader()

        with_healthy_coverage = dict(self._base_metrics(), dividend_yield=0.03, fcf_yield=0.10)
        without_fcf_data = dict(self._base_metrics(), dividend_yield=0.03)

        score_with = loader._score_value(with_healthy_coverage, "HEALTHY")
        score_without = loader._score_value(without_fcf_data, "NO_FCF_DATA")

        assert score_with == score_without

    def test_missing_fcf_yield_leaves_dividend_scored_on_magnitude(self):
        loader = StockScoresLoader()
        score = loader._score_value(dict(self._base_metrics(), dividend_yield=0.215), "NO_FCF")
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_zero_dividend_yield_unaffected_by_fcf(self):
        """Non-dividend-paying stock: the gate is a no-op regardless of fcf_yield sign."""
        loader = StockScoresLoader()

        zero_div_negative_fcf = dict(self._base_metrics(), dividend_yield=0.0, fcf_yield=-0.05)
        zero_div_no_fcf = dict(self._base_metrics(), dividend_yield=0.0)

        assert loader._score_value(zero_div_negative_fcf, "A") == loader._score_value(zero_div_no_fcf, "B")


class TestDividendSustainabilityFactorUnit:
    """Direct unit coverage of the pure helper, independent of _score_value's wiring."""

    def test_no_dividend_no_penalty(self):
        assert _dividend_sustainability_factor(0.0, -0.05) == 1.0

    def test_missing_fcf_yield_no_penalty(self):
        assert _dividend_sustainability_factor(0.05, None) == 1.0

    def test_negative_fcf_floors_to_zero(self):
        assert _dividend_sustainability_factor(0.05, -0.01) == 0.0

    def test_zero_fcf_floors_to_zero(self):
        assert _dividend_sustainability_factor(0.05, 0.0) == 0.0

    def test_payout_ratio_under_threshold_no_penalty(self):
        # dividend 3%, fcf 10% -> payout ratio 0.3x, well covered
        assert _dividend_sustainability_factor(0.03, 0.10) == 1.0

    def test_payout_ratio_at_unsustainable_threshold_no_penalty_yet(self):
        # exactly 1.0x - still fully covered by definition, taper starts strictly above this
        assert _dividend_sustainability_factor(0.05, 0.05) == 1.0

    def test_payout_ratio_midway_tapers_linearly(self):
        # dividend 7.5%, fcf 5% -> payout ratio 1.5x, halfway between 1.0x and 2.0x floor
        factor = _dividend_sustainability_factor(0.075, 0.05)
        assert abs(factor - 0.5) < 1e-9

    def test_payout_ratio_at_or_above_floor_ratio_is_zero(self):
        # dividend 10%, fcf 5% -> payout ratio 2.0x, at the floor
        assert _dividend_sustainability_factor(0.10, 0.05) == 0.0
        # well beyond the floor
        assert _dividend_sustainability_factor(0.20, 0.05) == 0.0

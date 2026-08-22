"""Regression coverage for the exposure-model factors touched by the 2026-08-22 redesign
(goal: exposure-model integrity review - see market_exposure.py's module docstring).

This file was originally written for redesign pass 1 (2026-08-22) and rewritten again for
pass 2 the same day. Pass 2 findings: _sahm_rule -> _sahm_rule_factor (demoted from a hard
veto to a graded factor, scored via _sahm_ramp_score's threshold-anchored ramp instead of a
binary trigger - see module docstring for why a raw z-score against Sahm's own
right-skewed history would have been the wrong tool). _financial_conditions_factor and
_financial_stress_factor (ANFCI/STLFSI4) were deleted entirely - live-verified
substantially redundant with the pre-existing Credit Spread/Yield Curve factors, not just
with each other - so TestFinancialConditionsVeto is gone with them.

_valuation_extension_breadth (unchanged 2026-08-20) keeps its original tests.
_cross_asset_confirmation -> _cross_asset_factor (z-scored composite, no more binary
"count >= 2 of 4" rule, no more technical_bullish gate) and _fundamental_quality ->
_fundamental_quality_factor (scores unconditionally, returns "score" not "penalty") are
unchanged from pass 1. The old _economic_regime_overlay's breakeven-inflation signal is
still its own standalone _inflation_expectations_factor; T10Y2Y/T10Y3M's overlay signal is
still _yield_curve_factor, built on the shared _single_series_zscore_factor helper (which
stays, still exercised generically below even though ANFCI/STLFSI4 no longer have their
own factory functions calling it).
"""

import math
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from algo.risk.market_exposure import MarketExposure

# --- Sahm Rule (demoted 2026-08-22 pass 2 from a hard veto to a graded factor - see
# market_exposure.py module docstring for why) ---


def _unrate_rows(values):
    """rows[0] = most recent month, descending, matching _sahm_rule_factor's DESC query order."""
    base = date(2026, 8, 1)
    return [(v, base) for v in values]


class TestSahmRuleFactor:
    def test_insufficient_history_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = _unrate_rows([4.0] * 14)  # needs >= 15
        me = MarketExposure()
        result = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_nan_value_is_data_unavailable_not_fabricated(self):
        cur = MagicMock()
        values = [4.0] * 20
        values[5] = float("nan")
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        result = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_infinity_value_is_data_unavailable(self):
        cur = MagicMock()
        values = [4.0] * 20
        values[0] = float("inf")
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        result = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_rising_unemployment_triggers_and_scores_low(self):
        cur = MagicMock()
        values = [4.7, 4.7, 4.7] + [4.0] * 17
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        result = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert result["value"] == 0.70
        assert result["triggered"] is True
        # 0.70pp is past the 0.50 trigger, ramping toward 0 by 1.5pp - solidly bearish
        # but not necessarily zero (continuous, not a binary cliff).
        assert result["score"] < 40.0

    def test_flat_unemployment_does_not_trigger_and_scores_max(self):
        cur = MagicMock()
        cur.fetchall.return_value = _unrate_rows([4.0] * 20)
        me = MarketExposure()
        result = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert result["value"] == 0.0
        assert result["triggered"] is False
        assert result["score"] == 100.0

    def test_triggered_sahm_no_longer_caps_exposure_directly(self):
        # Pass 2: Sahm Rule is a graded factor now, not a hard veto - it can only ever
        # contribute up to its own W_SAHM_RULE=2.0pt weight to the composite, it cannot
        # cap the whole portfolio to 25% by itself the way the old veto did.
        me = MarketExposure()
        cur = MagicMock()
        values = [4.7, 4.7, 4.7] + [4.0] * 17
        cur.fetchall.return_value = _unrate_rows(values)
        sahm = me._sahm_rule_factor(date(2026, 8, 20), cur)
        assert sahm["triggered"] is True
        pts, _ = me.calculator._wt_pts(sahm, me.W_SAHM_RULE)
        assert 0.0 <= pts <= me.W_SAHM_RULE


class TestSahmRampScore:
    """_sahm_ramp_score's threshold-anchored curve (real 0.50pp trigger, not a generic
    z-score against Sahm's own right-skewed history - see its docstring)."""

    def test_negative_or_zero_scores_max(self):
        assert MarketExposure._sahm_ramp_score(-1.0) == 100.0
        assert MarketExposure._sahm_ramp_score(0.0) == 100.0

    def test_exactly_at_trigger_scores_40(self):
        assert MarketExposure._sahm_ramp_score(0.50) == pytest.approx(40.0)

    def test_far_past_trigger_scores_zero(self):
        assert MarketExposure._sahm_ramp_score(1.5) == 0.0
        assert MarketExposure._sahm_ramp_score(5.0) == 0.0

    def test_monotonically_decreasing(self):
        xs = [-0.2, 0.0, 0.1, 0.25, 0.4, 0.5, 0.7, 1.0, 1.3, 1.5, 2.0]
        scores = [MarketExposure._sahm_ramp_score(x) for x in xs]
        assert scores == sorted(scores, reverse=True)


# --- Single-series z-score factor (shared helper, still used by _yield_curve_factor's two
# components even though ANFCI/STLFSI4 no longer have their own factory functions calling
# it - see module docstring on why those two were dropped entirely in pass 2) ---


class TestSingleSeriesZscoreFactor:
    def test_insufficient_history_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(4.0,)] * 10  # < 15 needed
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "ANFCI", higher_is_worse=True)
        assert result["data_unavailable"] is True

    def test_no_rows_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "STLFSI4", higher_is_worse=True)
        assert result["data_unavailable"] is True

    def test_elevated_reading_scores_low_when_higher_is_worse(self):
        # History flat at 0.0, current reading is a real outlier at +3.0 -> large positive z
        # -> score should be pinned near 0 (higher_is_worse=True: high reading = bad).
        cur = MagicMock()
        history = [0.0] * 30 + [0.1, -0.1, 0.05, -0.05]
        cur.fetchall.return_value = [(3.0,)] + [(v,) for v in history]
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "ANFCI", higher_is_worse=True)
        assert not result.get("data_unavailable")
        assert result["z"] > 2.0
        assert result["score"] < 10.0

    def test_elevated_reading_scores_high_when_higher_is_worse_false(self):
        # Same data, but higher_is_worse=False (e.g. a curve spread where MORE NEGATIVE is
        # bad) - an elevated (high, positive) current reading is the GOOD direction here,
        # so the sign gets flipped and the score should be pinned near 100, not near 0.
        cur = MagicMock()
        history = [0.0] * 30 + [0.1, -0.1, 0.05, -0.05]
        cur.fetchall.return_value = [(3.0,)] + [(v,) for v in history]
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "T10Y3M", higher_is_worse=False)
        assert not result.get("data_unavailable")
        assert result["z"] < -2.0
        assert result["score"] > 90.0

    def test_average_reading_scores_near_50(self):
        cur = MagicMock()
        values = [0.0, 0.1, -0.1, 0.05, -0.05, 0.02, -0.02] * 3
        cur.fetchall.return_value = [(v,) for v in values]
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "ANFCI", higher_is_worse=True)
        assert not result.get("data_unavailable")
        assert 30.0 < result["score"] < 70.0

    def test_nan_current_value_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(float("nan"),)] + [(0.0,)] * 20
        me = MarketExposure()
        result = me._single_series_zscore_factor(date(2026, 8, 20), cur, "STLFSI4", higher_is_worse=True)
        assert result["data_unavailable"] is True


# --- Yield Curve factor (T10Y2Y + T10Y3M average) ---


class TestYieldCurveFactor:
    def test_both_series_available_averages_scores(self):
        cur = MagicMock()
        jittered = [(0.0,), (0.1,), (-0.1,), (0.05,), (-0.05,)] * 4
        cur.fetchall.side_effect = [jittered, jittered]
        me = MarketExposure()
        result = me._yield_curve_factor(date(2026, 8, 20), cur)
        assert not result.get("data_unavailable")
        assert "t10y2y" in result and "t10y3m" in result
        assert 40.0 < result["score"] < 60.0

    def test_both_series_unavailable_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.side_effect = [[], []]
        me = MarketExposure()
        result = me._yield_curve_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_one_series_available_still_computes(self):
        cur = MagicMock()
        jittered = [(0.0,), (0.1,), (-0.1,), (0.05,), (-0.05,)] * 4
        cur.fetchall.side_effect = [[], jittered]
        me = MarketExposure()
        result = me._yield_curve_factor(date(2026, 8, 20), cur)
        assert not result.get("data_unavailable")


# --- Inflation Expectations factor (T5YIE + T10YIE average, z-scored) ---


class TestInflationExpectationsFactor:
    def test_insufficient_history_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        me = MarketExposure()
        result = me._inflation_expectations_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_elevated_breakeven_scores_low(self):
        # History flat at 2.2, current reading spikes to 3.2 -> stress, low score.
        cur = MagicMock()
        rows = [(date(2026, 8, 20), 3.2)] + [(date(2026, 8, 20) - timedelta(days=i), 2.2) for i in range(1, 30)]
        cur.fetchall.return_value = rows
        me = MarketExposure()
        result = me._inflation_expectations_factor(date(2026, 8, 20), cur)
        assert not result.get("data_unavailable")
        assert result["score"] < 20.0

    def test_nan_average_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20), float("nan"))] + [
            (date(2026, 8, 20) - timedelta(days=i), 2.2) for i in range(1, 20)
        ]
        me = MarketExposure()
        result = me._inflation_expectations_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True


# --- Sector Rotation factor ---


class TestSectorRotationFactor:
    def test_high_defensive_lead_inverts_to_low_score(self):
        with patch("algo.signals.sector_rotation.SectorRotationDetector") as mock_cls:
            mock_cls.return_value.compute.return_value = {
                "defensive_lead_score": 80.0,
                "signal": "severe_defensive_rotation",
            }
            me = MarketExposure()
            cur = MagicMock()
            result = me._sector_rotation_factor(date(2026, 8, 20), cur)
        assert result["score"] == 20.0
        assert result["defensive_lead_score"] == 80.0

    def test_data_unavailable_passes_through(self):
        with patch("algo.signals.sector_rotation.SectorRotationDetector") as mock_cls:
            mock_cls.return_value.compute.return_value = {
                "data_unavailable": True,
                "reason": "insufficient_12w_sector_history",
                "reduce_exposure_pts": 0,
            }
            me = MarketExposure()
            cur = MagicMock()
            result = me._sector_rotation_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True


# --- Cross-Asset Confirmation factor ---


def _jittered_series(current_date, n=280, base=0.0, amplitude=0.5, current_value=None):
    """A deterministic, non-constant historical series (real variance, needed for
    _sample_zscore - a perfectly flat/zero-variance series is correctly treated as
    unscoreable, not a neutral reading) via a fixed oscillation, not random (test
    determinism). `current_value`, if given, overrides just the most recent (today's) row -
    used to inject a genuine, isolated outlier against otherwise-routine history.
    """
    rows = [(current_date - timedelta(days=i), base + amplitude * math.sin(i * 0.7)) for i in range(n)]
    if current_value is not None:
        rows[0] = (current_date, current_value)
    return rows


class TestCrossAssetFactor:
    def test_no_spy_history_returns_none(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        me = MarketExposure()
        assert me._cross_asset_factor(date(2026, 8, 20), cur) is None

    def test_routine_variation_scores_near_neutral(self):
        eval_date = date(2026, 8, 20)
        series = _jittered_series(eval_date)
        cur = MagicMock()
        cur.fetchall.side_effect = [series, series, series, series, series]  # spy, gld, tlt, usd, oil
        me = MarketExposure()
        result = me._cross_asset_factor(eval_date, cur)
        assert result is not None
        assert 30.0 <= result["score"] <= 70.0

    def test_gold_and_bonds_diverging_from_spy_scores_low(self):
        # Gold and bonds have genuinely outperformed SPY by a wide, historically-unusual
        # margin today (routine +/-0.5 jitter historically, spikes to +10 today) -> two real
        # z-score outliers -> composite risk-off -> low score (divergence penalized).
        eval_date = date(2026, 8, 20)
        spy_series = _jittered_series(eval_date, amplitude=0.0)  # keep SPY itself flat/neutral
        gld_spike = _jittered_series(eval_date, current_value=10.0)
        tlt_spike = _jittered_series(eval_date, current_value=10.0)
        usd_series = _jittered_series(eval_date)
        oil_series = _jittered_series(eval_date)
        cur = MagicMock()
        cur.fetchall.side_effect = [spy_series, gld_spike, tlt_spike, usd_series, oil_series]
        me = MarketExposure()
        result = me._cross_asset_factor(eval_date, cur)
        assert result is not None
        assert result["score"] < 20.0
        assert result["composite_z"] > 0

    def test_agreement_gives_bounded_bonus_not_symmetric(self):
        # Gold/bonds underperforming SPY (negative spread outlier = risk-ON agreement) -
        # composite z well below 0. Response curve is asymmetric: this should raise the
        # score above 50 but stop short of the ceiling divergence would hit going the other
        # way, since the curve deliberately weights divergence more than agreement.
        eval_date = date(2026, 8, 20)
        spy_series = _jittered_series(eval_date, amplitude=0.0)
        gld_dip = _jittered_series(eval_date, current_value=-3.0)
        tlt_dip = _jittered_series(eval_date, current_value=-3.0)
        usd_series = _jittered_series(eval_date)
        oil_series = _jittered_series(eval_date)
        cur = MagicMock()
        cur.fetchall.side_effect = [spy_series, gld_dip, tlt_dip, usd_series, oil_series]
        me = MarketExposure()
        result = me._cross_asset_factor(eval_date, cur)
        assert result is not None
        assert 50.0 < result["score"] < 100.0

    def test_insufficient_asset_history_degrades_only_that_signal(self):
        eval_date = date(2026, 8, 20)
        spy_series = _jittered_series(eval_date)
        cur = MagicMock()
        # GLD has only 5 overlapping points with SPY (< 15 minimum) - should be excluded,
        # not crash, and the rest still combine into a result.
        cur.fetchall.side_effect = [
            spy_series,
            _jittered_series(eval_date, n=5),
            _jittered_series(eval_date),
            _jittered_series(eval_date),
            _jittered_series(eval_date),
        ]
        me = MarketExposure()
        result = me._cross_asset_factor(eval_date, cur)
        assert result is not None
        assert result["gld_vs_spy_chg_20d"] is None


# --- Earnings Revision Breadth factor ---


class TestEarningsRevisionBreadthFactor:
    """Split 2026-08-22 from the old 3-way "Fundamental Quality" blend - see
    market_exposure.py's module docstring and _earnings_revision_breadth_factor's own
    docstring for why. Now a standalone factor: one query (rising, total), not three.
    """

    def test_strong_revisions_scores_high(self):
        cur = MagicMock()
        cur.fetchone.return_value = (150, 200)  # 75% breadth
        me = MarketExposure()
        result = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur)
        assert not result.get("data_unavailable")
        assert result["score"] == 100.0
        assert result["revision_breadth_pct"] == 75.0

    def test_weak_revisions_scores_low(self):
        cur = MagicMock()
        cur.fetchone.return_value = (10, 200)  # 5% breadth
        me = MarketExposure()
        result = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur)
        assert not result.get("data_unavailable")
        assert result["score"] == 0.0

    def test_insufficient_sample_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchone.return_value = (10, 50)  # total=50 < 200 sample floor
        me = MarketExposure()
        result = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_no_rows_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        me = MarketExposure()
        result = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_scores_the_same_regardless_of_technical_direction(self):
        # This factor never took a technical_bullish parameter in the first place (unlike
        # the old blended Fundamental Quality it replaced) - same inputs, same output,
        # always. Guards against that conditional gating ever creeping back in.
        cur_a = MagicMock()
        cur_a.fetchone.return_value = (10, 200)
        cur_b = MagicMock()
        cur_b.fetchone.return_value = (10, 200)
        me = MarketExposure()
        result_a = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur_a)
        result_b = me._earnings_revision_breadth_factor(date(2026, 8, 20), cur_b)
        assert result_a["score"] == result_b["score"] == 0.0


class TestValuationExtensionBreadth:
    """Unchanged 2026-08-22's edits to this method - still its own standalone factor now
    (split from the old blended Fundamental Quality, see module docstring)."""

    def test_insufficient_sample_returns_none(self):
        cur = MagicMock()
        cur.fetchone.return_value = (150, 40)  # total=150 < 200 sample floor
        me = MarketExposure()
        assert me._valuation_extension_breadth(date(2026, 8, 20), cur) is None

    def test_no_rows_returns_none(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        me = MarketExposure()
        assert me._valuation_extension_breadth(date(2026, 8, 20), cur) is None

    def test_low_froth_scores_high(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 50)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["breadth_pct"] == 5.0
        assert result["score"] == 100.0

    def test_high_froth_scores_low(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 600)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["breadth_pct"] == 60.0
        assert result["score"] == 0.0

    def test_midpoint_breadth_scores_midpoint(self):
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 350)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["score"] == 50.0


class TestZscoreToScoreMapping:
    """Direct coverage of MarketFactorCalculator._zscore_to_score / _sample_zscore, the
    shared primitive every z-scored factor in this file is built on."""

    def test_zero_z_maps_to_50(self):
        me = MarketExposure()
        assert me.calculator._zscore_to_score(0.0) == 50.0

    def test_positive_cap_z_maps_to_0(self):
        me = MarketExposure()
        assert me.calculator._zscore_to_score(2.5) == 0.0

    def test_negative_cap_z_maps_to_100(self):
        me = MarketExposure()
        assert me.calculator._zscore_to_score(-2.5) == 100.0

    def test_beyond_cap_still_clips(self):
        me = MarketExposure()
        assert me.calculator._zscore_to_score(10.0) == 0.0
        assert me.calculator._zscore_to_score(-10.0) == 100.0

    def test_nan_z_maps_to_neutral(self):
        me = MarketExposure()
        assert me.calculator._zscore_to_score(float("nan")) == 50.0

    def test_sample_zscore_needs_minimum_history(self):
        me = MarketExposure()
        assert me.calculator._sample_zscore(1.0, [1.0] * 14) is None
        assert me.calculator._sample_zscore(1.0, [1.0] * 15) is None  # zero variance too

    def test_sample_zscore_zero_variance_returns_none(self):
        me = MarketExposure()
        assert me.calculator._sample_zscore(5.0, [1.0] * 20) is None

    def test_sample_zscore_normal_case(self):
        me = MarketExposure()
        history = [0.0] * 19 + [2.0]  # mean != 0, real variance
        z = me.calculator._sample_zscore(0.0, history)
        assert z is not None
        assert not math.isnan(z)

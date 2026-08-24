"""Regression coverage for the exposure-model macro-watch factors and slow macro veto.

REWRITTEN 2026-08-23 for the pillar redesign (see market_exposure.py's module
docstring): Sahm Rule, Yield Curve, and Inflation Expectations are no longer scored in
the composite - Estrella & Mishkin (1998) show yield-curve inversion leads recessions
by 6-24 months, the wrong horizon for this system's responsive exposure dial, so all
three now feed only a slow, wide, rare tail-risk veto (_slow_macro_veto) instead of
earning composite weight. sector_rotation, cross_asset_confirmation,
earnings_revision_breadth, and valuation_extension_breadth were dropped entirely (not
covered by the redesign's evidence framework, or structurally unbacktestable) - their
test classes (TestSectorRotationFactor, TestCrossAssetFactor,
TestEarningsRevisionBreadthFactor, TestValuationExtensionBreadth) are removed along
with the methods they covered.
"""

import math
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from algo.risk.market_exposure import MarketExposure

# --- Sahm Rule (macro-watch only since 2026-08-23 - feeds _slow_macro_veto, no longer
# scored in the composite at all, graded or otherwise) ---


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


# --- Single-series z-score factor (shared helper - still used by _yield_curve_factor's
# two components, now macro-watch-only, see module docstring) ---


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


# --- Yield Curve reading (T10Y2Y + T10Y3M average) - macro-watch only ---


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


class TestYieldCurveInvertedPersistent:
    """New for the 2026-08-23 slow macro veto: a persistence check (every session in the
    trailing window inverted), distinct from _yield_curve_factor's single-day z-score."""

    def test_full_window_inverted_returns_true(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20) - timedelta(days=i), -0.15) for i in range(63)]
        me = MarketExposure()
        assert me._yield_curve_inverted_persistent(date(2026, 8, 20), cur) is True

    def test_one_non_inverted_session_returns_false(self):
        cur = MagicMock()
        rows = [(date(2026, 8, 20) - timedelta(days=i), -0.15) for i in range(63)]
        rows[30] = (rows[30][0], 0.05)  # one positive (un-inverted) session breaks persistence
        cur.fetchall.return_value = rows
        me = MarketExposure()
        assert me._yield_curve_inverted_persistent(date(2026, 8, 20), cur) is False

    def test_insufficient_window_returns_false_not_unavailable(self):
        # A veto input must never trip on an incomplete signal - short history degrades to
        # "not triggered", not data_unavailable (this isn't a scored composite factor).
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20) - timedelta(days=i), -0.15) for i in range(10)]
        me = MarketExposure()
        assert me._yield_curve_inverted_persistent(date(2026, 8, 20), cur) is False


# --- Inflation Expectations reading (T5YIE + T10YIE average, z-scored) - macro-watch only ---


class TestInflationExpectationsFactor:
    def test_insufficient_history_is_data_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        me = MarketExposure()
        result = me._inflation_expectations_factor(date(2026, 8, 20), cur)
        assert result["data_unavailable"] is True

    def test_elevated_breakeven_scores_low(self):
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


# --- Slow macro veto (new 2026-08-23: Sahm / persistent yield-curve inversion /
# inflation-expectations tail extreme, caps exposure to 45% - see module docstring) ---


class TestSlowMacroVeto:
    def _cur_no_inversion(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20) - timedelta(days=i), 0.1) for i in range(63)]
        return cur

    def test_nothing_triggered_is_clear(self):
        me = MarketExposure()
        sahm = {"triggered": False, "value": 0.0}
        infl = {"z": 0.2}
        result = me._slow_macro_veto(date(2026, 8, 20), self._cur_no_inversion(), sahm, infl)
        assert result["triggered"] is False
        assert result["cap"] == 100.0

    def test_sahm_triggered_caps_to_45(self):
        me = MarketExposure()
        sahm = {"triggered": True, "value": 0.7}
        infl = {"z": 0.2}
        result = me._slow_macro_veto(date(2026, 8, 20), self._cur_no_inversion(), sahm, infl)
        assert result["triggered"] is True
        assert result["cap"] == 45.0
        assert any("Sahm" in r for r in result["reasons"])

    def test_persistent_inversion_caps_to_45(self):
        me = MarketExposure()
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20) - timedelta(days=i), -0.2) for i in range(63)]
        sahm = {"triggered": False, "value": 0.0}
        infl = {"z": 0.2}
        result = me._slow_macro_veto(date(2026, 8, 20), cur, sahm, infl)
        assert result["triggered"] is True
        assert result["cap"] == 45.0
        assert any("Yield curve" in r for r in result["reasons"])

    def test_inflation_tail_extreme_caps_to_45(self):
        me = MarketExposure()
        sahm = {"triggered": False, "value": 0.0}
        infl = {"z": 2.5}
        result = me._slow_macro_veto(date(2026, 8, 20), self._cur_no_inversion(), sahm, infl)
        assert result["triggered"] is True
        assert result["cap"] == 45.0
        assert any("Inflation" in r for r in result["reasons"])

    def test_multiple_triggers_still_cap_to_45_not_stacked_lower(self):
        # All three are correlated reads of the same macro-stress regime, not independent
        # risks that compound - see _slow_macro_veto's docstring.
        me = MarketExposure()
        cur = MagicMock()
        cur.fetchall.return_value = [(date(2026, 8, 20) - timedelta(days=i), -0.2) for i in range(63)]
        sahm = {"triggered": True, "value": 0.7}
        infl = {"z": 2.5}
        result = me._slow_macro_veto(date(2026, 8, 20), cur, sahm, infl)
        assert result["triggered"] is True
        assert result["cap"] == 45.0
        assert len(result["reasons"]) == 3

    def test_data_unavailable_sahm_and_inflation_do_not_trigger(self):
        me = MarketExposure()
        sahm = {"data_unavailable": True, "reason": "no data"}
        infl = {"data_unavailable": True, "reason": "no data"}
        result = me._slow_macro_veto(date(2026, 8, 20), self._cur_no_inversion(), sahm, infl)
        assert result["triggered"] is False


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

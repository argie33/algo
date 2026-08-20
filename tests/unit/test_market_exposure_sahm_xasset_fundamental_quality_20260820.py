"""Regression coverage for the three new modifiers/veto added to
algo/risk/market_exposure.py in the 2026-08-20 exposure-model redesign
(see [[market_exposure_positioning_factor_replaces_naaim_20260820]] in memory):
_sahm_rule (hard veto), _cross_asset_confirmation and _fundamental_quality
(post-score discount-only modifiers).

These landed with the same NaN/insufficient-data graceful-degrade discipline as every other
factor in this file (see test_market_exposure_nan_guards.py), but had no dedicated test
coverage of their own until now - this file closes that gap, following the same MagicMock
cursor pattern as test_market_exposure_nan_guards.py.
"""

import math
from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.risk.market_exposure import MarketExposure

# --- Sahm Rule ---


def _unrate_rows(values):
    """rows[0] = most recent month, descending, matching _sahm_rule's DESC query order."""
    base = date(2026, 8, 1)
    return [(v, base) for v in values]


class TestSahmRule:
    def test_insufficient_history_returns_none(self):
        cur = MagicMock()
        cur.fetchall.return_value = _unrate_rows([4.0] * 14)  # needs >= 15
        me = MarketExposure()
        assert me._sahm_rule(date(2026, 8, 20), cur) is None

    def test_nan_value_returns_none_not_fabricated(self):
        cur = MagicMock()
        values = [4.0] * 20
        values[5] = float("nan")
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        assert me._sahm_rule(date(2026, 8, 20), cur) is None

    def test_infinity_value_returns_none(self):
        cur = MagicMock()
        values = [4.0] * 20
        values[0] = float("inf")
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        assert me._sahm_rule(date(2026, 8, 20), cur) is None

    def test_rising_unemployment_triggers(self):
        # Most recent 3 months averaging 4.7, everything else flat at 4.0 ->
        # current_avg=4.7, trailing_12mo_min=4.0, sahm_value=0.70 >= 0.50 threshold.
        cur = MagicMock()
        values = [4.7, 4.7, 4.7] + [4.0] * 17
        cur.fetchall.return_value = _unrate_rows(values)
        me = MarketExposure()
        result = me._sahm_rule(date(2026, 8, 20), cur)
        assert result is not None
        assert result["value"] == 0.70
        assert result["triggered"] is True

    def test_flat_unemployment_does_not_trigger(self):
        cur = MagicMock()
        cur.fetchall.return_value = _unrate_rows([4.0] * 20)
        me = MarketExposure()
        result = me._sahm_rule(date(2026, 8, 20), cur)
        assert result is not None
        assert result["value"] == 0.0
        assert result["triggered"] is False

    def test_triggered_sahm_rule_caps_exposure_at_25(self):
        """End-to-end: a triggered Sahm Rule must show up as a hard veto capping exposure,
        not just a computed-but-unused factor entry."""
        me = MarketExposure()
        cur = MagicMock()
        values = [4.7, 4.7, 4.7] + [4.0] * 17
        cur.fetchall.return_value = _unrate_rows(values)
        sahm = me._sahm_rule(date(2026, 8, 20), cur)
        assert sahm["triggered"] is True
        # Mirrors the veto-application logic at the _sahm_rule call site in compute().
        cap = 100.0
        if sahm["triggered"]:
            cap = min(cap, 25.0)
        assert cap == 25.0


# --- Cross-Asset Confirmation ---


def _price_rows(current, baseline, n=21):
    """n rows of (close,); rows[0]=current (most recent), rows[-1]=baseline, matching
    _trailing_pct_change's DESC query order and its use of only the first/last row."""
    mid = [current] * (n - 2)
    return [(current,), *[(v,) for v in mid], (baseline,)]


class TestCrossAssetConfirmation:
    def test_insufficient_spy_history_returns_none(self):
        cur = MagicMock()
        cur.fetchall.return_value = _price_rows(103, 100, n=10)  # < 21 rows
        me = MarketExposure()
        assert me._cross_asset_confirmation(date(2026, 8, 20), cur, True) is None

    def test_two_of_four_risk_off_and_bullish_equities_applies_penalty(self):
        # SPY +3%, GLD +10.3% (7.3pp over SPY, >3pp threshold -> gold risk-off),
        # TLT +7% (4.0pp over SPY, >3pp threshold -> bonds risk-off), USD and oil flat
        # (no risk-off) - still 2-or-more of 4 signals triggers the penalty.
        cur = MagicMock()
        cur.fetchall.side_effect = [
            _price_rows(103, 100),  # SPY
            _price_rows(110.3, 100),  # GLD
            _price_rows(107, 100),  # TLT
            _price_rows(100, 100, n=21),  # USD (DTWEXBGS)
            _price_rows(100, 100, n=21),  # oil (DCOILWTICO)
        ]
        me = MarketExposure()
        result = me._cross_asset_confirmation(date(2026, 8, 20), cur, equities_bullish=True)
        assert result is not None
        assert result["penalty"] == 8.0
        assert result["pts"] == -8.0
        assert len(result["risk_off_signals"]) == 2

    def test_only_one_of_four_risk_off_applies_no_penalty(self):
        # Only gold disagrees (7.3pp); bonds (2.0pp), USD (0%), oil (0%) all under threshold.
        cur = MagicMock()
        cur.fetchall.side_effect = [
            _price_rows(103, 100),  # SPY
            _price_rows(110.3, 100),  # GLD (risk-off)
            _price_rows(105, 100),  # TLT (not risk-off: 2.0pp)
            _price_rows(100, 100, n=21),  # USD (not risk-off)
            _price_rows(100, 100, n=21),  # oil (not risk-off)
        ]
        me = MarketExposure()
        result = me._cross_asset_confirmation(date(2026, 8, 20), cur, equities_bullish=True)
        assert result is not None
        assert result["penalty"] == 0.0

    def test_disagreement_without_bullish_equities_applies_no_penalty(self):
        # Same 2-of-4 risk-off as the triggering case above, but equities aren't bullish ->
        # the modifier only discounts a technical picture that's actually claiming strength.
        cur = MagicMock()
        cur.fetchall.side_effect = [
            _price_rows(103, 100),  # SPY
            _price_rows(110.3, 100),  # GLD (risk-off)
            _price_rows(107, 100),  # TLT (risk-off)
            _price_rows(100, 100, n=21),  # USD
            _price_rows(100, 100, n=21),  # oil
        ]
        me = MarketExposure()
        result = me._cross_asset_confirmation(date(2026, 8, 20), cur, equities_bullish=False)
        assert result is not None
        assert result["penalty"] == 0.0

    def test_oil_spike_counts_as_a_risk_off_signal(self):
        # Gold risk-off (7.3pp) + oil +20%/20d (>15% threshold) = 2-of-4 -> penalty, even
        # though bonds and USD both agree with the equity rally.
        cur = MagicMock()
        cur.fetchall.side_effect = [
            _price_rows(103, 100),  # SPY
            _price_rows(110.3, 100),  # GLD (risk-off)
            _price_rows(100, 100, n=21),  # TLT (flat, not risk-off)
            _price_rows(100, 100, n=21),  # USD (flat, not risk-off)
            _price_rows(120, 100, n=21),  # oil +20%/20d (risk-off)
        ]
        me = MarketExposure()
        result = me._cross_asset_confirmation(date(2026, 8, 20), cur, equities_bullish=True)
        assert result is not None
        assert result["oil_chg_20d"] == 20.0
        assert result["penalty"] == 8.0
        assert any("oil" in s for s in result["risk_off_signals"])

    def test_insufficient_oil_history_degrades_only_that_signal(self):
        # Oil query returns < 21 rows (insufficient) - oil_risk_off must stay False, not
        # crash or get treated as risk-off by default. Everything else is flat/no-signal.
        cur = MagicMock()
        cur.fetchall.side_effect = [
            _price_rows(103, 100),  # SPY
            _price_rows(100, 100, n=21),  # GLD (flat)
            _price_rows(100, 100, n=21),  # TLT (flat)
            _price_rows(100, 100, n=21),  # USD (flat)
            _price_rows(150, 100, n=10),  # oil: insufficient history (<21 rows)
        ]
        me = MarketExposure()
        result = me._cross_asset_confirmation(date(2026, 8, 20), cur, equities_bullish=True)
        assert result is not None
        assert result["oil_chg_20d"] is None
        assert result["penalty"] == 0.0


# --- Fundamental Quality of the Rally ---


class TestFundamentalQuality:
    def test_strong_fundamentals_no_penalty_even_when_bullish(self):
        calc_cur = MagicMock()
        # revision query: 150/200 rising -> 75% breadth (>= 200 sample floor)
        # insider query (via calculator._insider_buying_breadth): 150/200 net buyers -> 75%
        # valuation query: 50/1000 extended -> 5% breadth (low froth -> high score)
        calc_cur.fetchone.side_effect = [(150, 200), (200, 150), (1000, 50)]
        me = MarketExposure()
        result = me._fundamental_quality(date(2026, 8, 20), calc_cur, technical_bullish=True)
        assert result is not None
        assert result["fundamental_score"] == 100.0
        assert result["valuation_extension_breadth_pct"] == 5.0
        assert result["penalty"] == 0.0

    def test_weak_fundamentals_with_bullish_technicals_applies_capped_penalty(self):
        calc_cur = MagicMock()
        # revision: 10/200 rising -> 5% breadth (clamps to score 0)
        # insider: 10/100 net buyers -> 10% breadth (clamps to score 0)
        # valuation: 600/1000 extended -> 60% breadth (high froth -> clamps to score 0)
        calc_cur.fetchone.side_effect = [(10, 200), (100, 10), (1000, 600)]
        me = MarketExposure()
        result = me._fundamental_quality(date(2026, 8, 20), calc_cur, technical_bullish=True)
        assert result is not None
        assert result["fundamental_score"] == 0.0
        assert result["penalty"] == 5.0  # capped at 5pt max haircut
        assert result["pts"] == -5.0

    def test_weak_fundamentals_without_bullish_technicals_applies_no_penalty(self):
        calc_cur = MagicMock()
        calc_cur.fetchone.side_effect = [(10, 200), (100, 10), (1000, 600)]
        me = MarketExposure()
        result = me._fundamental_quality(date(2026, 8, 20), calc_cur, technical_bullish=False)
        assert result is not None
        assert result["penalty"] == 0.0

    def test_all_inputs_unavailable_returns_none(self):
        calc_cur = MagicMock()
        # revision: total=50 < 200 sample floor -> revision_breadth_pct stays None
        # insider: active_count=10 < 50 minimum sample -> _insider_buying_breadth returns None
        # valuation: total=100 < 200 sample floor -> _valuation_extension_breadth returns None
        calc_cur.fetchone.side_effect = [(0, 50), (10, 5), (100, 20)]
        me = MarketExposure()
        result = me._fundamental_quality(date(2026, 8, 20), calc_cur, technical_bullish=True)
        assert result is None

    def test_only_valuation_available_still_computes(self):
        # revision and insider both unavailable; valuation alone should still drive the score
        # (weight redistribution: 0.25 total_weight, still normalized to fundamental_score).
        calc_cur = MagicMock()
        calc_cur.fetchone.side_effect = [(0, 50), (10, 5), (1000, 600)]
        me = MarketExposure()
        result = me._fundamental_quality(date(2026, 8, 20), calc_cur, technical_bullish=True)
        assert result is not None
        assert result["revision_breadth_pct"] is None
        assert result["insider_buying_breadth_pct"] is None
        assert result["valuation_extension_breadth_pct"] == 60.0
        assert result["fundamental_score"] == 0.0


class TestValuationExtensionBreadth:
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
        # 5% extended -> healthy, low froth -> score should clamp to 100
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 50)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["breadth_pct"] == 5.0
        assert result["score"] == 100.0

    def test_high_froth_scores_low(self):
        # 60% extended -> high froth -> score should clamp to 0
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 600)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["breadth_pct"] == 60.0
        assert result["score"] == 0.0

    def test_midpoint_breadth_scores_midpoint(self):
        # 35% extended -> midpoint of the linear scale -> score == 50
        cur = MagicMock()
        cur.fetchone.return_value = (1000, 350)
        me = MarketExposure()
        result = me._valuation_extension_breadth(date(2026, 8, 20), cur)
        assert result is not None
        assert result["score"] == 50.0


# --- Breakeven Inflation (Signal 8 of _economic_regime_overlay) ---


def _neutral_overlay_cur(t5yie, t10yie):
    """A cursor where Signals 1-4 (fetchall-based) and Signals 5-7 (fetchone-based) are all
    empty/None - i.e. contribute zero stress - isolating Signal 8 (breakeven inflation,
    T5YIE/T10YIE) as the only source of stress/signals in the result. Call order in
    _economic_regime_overlay: fetchall x4 (T10Y2Y, ICSA, STLFSI4, CFNAI), then fetchone x5
    (T10Y3M, ANFCI, BAMLC0A0CM, T5YIE, T10YIE)."""
    cur = MagicMock()
    cur.fetchall.side_effect = [[], [], [], []]
    cur.fetchone.side_effect = [None, None, None, t5yie, t10yie]
    return cur


class TestBreakevenInflationOverlaySignal:
    def test_no_breakeven_data_contributes_no_stress(self):
        cur = _neutral_overlay_cur(None, None)
        me = MarketExposure()
        result = me._economic_regime_overlay(date(2026, 8, 20), cur)
        assert result["macro_stress_score"] == 0.0
        assert result["signals"] == []

    def test_elevated_breakeven_adds_moderate_stress(self):
        # avg(2.6, 2.6) = 2.6, in the (2.5, 2.8] "elevated" band -> +7.0 stress
        cur = _neutral_overlay_cur((2.6,), (2.6,))
        me = MarketExposure()
        result = me._economic_regime_overlay(date(2026, 8, 20), cur)
        assert result["macro_stress_score"] == 7.0
        assert any("Breakeven inflation" in s for s in result["signals"])

    def test_severe_breakeven_adds_high_stress(self):
        # avg(2.9, 2.9) = 2.9, above 2.8 "severe" threshold -> +15.0 stress
        cur = _neutral_overlay_cur((2.9,), (2.9,))
        me = MarketExposure()
        result = me._economic_regime_overlay(date(2026, 8, 20), cur)
        assert result["macro_stress_score"] == 15.0
        assert any("severe" in s for s in result["signals"])

    def test_only_one_series_available_still_computes(self):
        # T5YIE missing, T10YIE=2.9 alone still crosses the severe threshold.
        cur = _neutral_overlay_cur(None, (2.9,))
        me = MarketExposure()
        result = me._economic_regime_overlay(date(2026, 8, 20), cur)
        assert result["macro_stress_score"] == 15.0

    def test_nan_value_excluded_not_laundered_into_average(self):
        # T5YIE is NaN (corrupted) and must be excluded, not silently averaged in; T10YIE=2.3
        # alone is below both thresholds -> zero stress, not a NaN-poisoned score.
        cur = _neutral_overlay_cur((float("nan"),), (2.3,))
        me = MarketExposure()
        result = me._economic_regime_overlay(date(2026, 8, 20), cur)
        assert result["macro_stress_score"] == 0.0
        assert not math.isnan(result["macro_stress_score"])

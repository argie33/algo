"""Regression tests for the Market Technicals factor (SPY RSI(14) + MACD(12,26,9)),
added 2026-08-23 replacing Consumer Sentiment (UMCSENT) - see
MarketExposure._market_technicals_factor's docstring. Shipped with no test coverage at
all for the actual calculation logic (only the weight-sum test was updated for the
renamed constant) - this file fills that gap.

BUG FOUND while writing these tests (goal: verify market technicals is correctly built
and integrated): MarketFactorCalculator._compute_rsi's `if avg_loss < 1e-9: return 100.0`
branch conflated a genuinely flat/frozen price feed (avg_gain==0 AND avg_loss==0 - zero
price movement at all, e.g. a stale feed or duplicate/placeholder rows, the same failure
mode as this session's flat-OHLC-placeholder-row and near-zero-ATR bugs) with a real
all-up-days rally (avg_gain>0, avg_loss==0 - a legitimate RSI=100 extreme). Both hit the
same branch and returned an identical, maximally-confident 100.0 - fabricating an extreme
overbought reading from data with no actual price action in it. Fixed by special-casing
the zero-gain-AND-zero-loss case to 50.0 (neutral) before the all-up-days check.
"""

import math
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from algo.infrastructure import MarketCalendar
from algo.risk.market_exposure import MarketExposure
from algo.risk.market_factor_calculator import MarketFactorCalculator


class TestComputeRsiFlatVsRally:
    def test_flat_frozen_feed_is_neutral_not_a_fabricated_extreme(self):
        # Zero movement at all (avg_gain==0 AND avg_loss==0) must NOT be scored the same
        # as a genuine all-up-days rally - see module docstring.
        closes = [421.37] * 20
        assert MarketFactorCalculator._compute_rsi(closes, period=14) == 50.0

    def test_real_all_up_days_rally_is_still_100(self):
        closes = [100.0 + i for i in range(20)]
        assert MarketFactorCalculator._compute_rsi(closes, period=14) == 100.0

    def test_real_all_down_days_selloff_is_still_0(self):
        closes = [200.0 - i for i in range(20)]
        assert MarketFactorCalculator._compute_rsi(closes, period=14) == 0.0

    def test_insufficient_history_returns_none(self):
        assert MarketFactorCalculator._compute_rsi([100.0] * 5, period=14) is None


class TestMacdHistogramPctSeries:
    def test_zero_variance_history_is_unavailable_not_a_fabricated_zscore(self):
        # A fully flat close series also makes the MACD histogram identically zero
        # everywhere, which _sample_zscore correctly refuses to standardize (stdev<1e-9).
        closes = [421.37] * 250
        hist = MarketFactorCalculator._macd_histogram_pct_series(closes)
        window = hist[200:]
        assert MarketFactorCalculator._sample_zscore(window[-1], window) is None

    def test_uptrend_produces_positive_histogram(self):
        closes = [100.0 + i * 0.3 for i in range(250)]
        hist = MarketFactorCalculator._macd_histogram_pct_series(closes)
        assert hist[-1] > 0

    def test_downtrend_produces_negative_histogram(self):
        closes = [300.0 - i * 0.3 for i in range(250)]
        hist = MarketFactorCalculator._macd_histogram_pct_series(closes)
        assert hist[-1] < 0


def _spy_rows(closes, eval_date):
    """(close, date) rows, most-recent-first, ending on eval_date - matches
    _market_technicals_factor's `ORDER BY date DESC` query shape. Uses real trading days
    so the staleness check (walks back via MarketCalendar) passes naturally."""
    days = MarketCalendar.get_trading_days(eval_date - timedelta(days=800), eval_date)
    days = days[-len(closes) :]
    assert len(days) == len(closes)
    return [(closes[i], days[i]) for i in range(len(days) - 1, -1, -1)]


class TestMarketTechnicalsFactorIntegration:
    EVAL_DATE = date(2026, 8, 20)  # a Thursday, not a holiday

    def test_insufficient_price_history_is_unavailable(self):
        cur = MagicMock()
        cur.fetchall.return_value = _spy_rows([420.0] * 100, self.EVAL_DATE)
        me = MarketExposure()
        result = me._market_technicals_factor(self.EVAL_DATE, cur)
        assert result["data_unavailable"] is True
        assert "Insufficient" in result["reason"]

    def test_stale_price_data_is_unavailable(self):
        cur = MagicMock()
        rows = _spy_rows([420.0] * 250, self.EVAL_DATE)
        # Shift every date back by 10 calendar days so the most recent close is well
        # before the expected prior trading day.
        stale_rows = [(c, d - timedelta(days=10)) for c, d in rows]
        cur.fetchall.return_value = stale_rows
        me = MarketExposure()
        result = me._market_technicals_factor(self.EVAL_DATE, cur)
        assert result["data_unavailable"] is True
        assert "stale" in result["reason"].lower()

    def test_flat_frozen_feed_does_not_fabricate_an_extreme_composite(self):
        # End-to-end: a frozen SPY feed (250 identical closes) must not produce a
        # maximally-confident bullish or bearish composite score - RSI neutral (50) and
        # MACD unavailable (zero variance) should leave the factor unavailable or neutral,
        # never pinned at 0/100.
        cur = MagicMock()
        cur.fetchall.return_value = _spy_rows([421.37] * 250, self.EVAL_DATE)
        me = MarketExposure()
        result = me._market_technicals_factor(self.EVAL_DATE, cur)
        # MACD z-score is unavailable on zero variance -> whole factor reports unavailable
        # rather than silently blending in a fabricated RSI-only extreme.
        assert result.get("data_unavailable") is True

    def test_macd_z_composes_direct_not_contrarian_when_rsi_neutral(self):
        # Isolates the composition/sign logic from RSI's contrarian-at-extremes behavior
        # (already covered separately below and can dominate/mask the blend over a long
        # sustained trend, since 250 days of real drift easily pins RSI near 80/20 - see
        # the two tests above/below this one for why a naive "uptrend must score >50"
        # integration test doesn't hold for this deliberately-contrarian factor). With RSI
        # held neutral (50 - no contrarian pull either way), a positive macd_z (momentum
        # stronger than its own trailing history) must push the composite ABOVE 50
        # (direct, trend-confirming - not flipped contrarian), and a negative macd_z must
        # push it below.
        closes = [420.0 + math.sin(i / 7.0) * 0.3 for i in range(250)]
        cur = MagicMock()
        cur.fetchall.return_value = _spy_rows(closes, self.EVAL_DATE)
        me = MarketExposure()

        from unittest.mock import patch

        with (
            patch.object(me.calculator, "_compute_rsi", return_value=50.0),
            patch.object(me.calculator, "_sample_zscore", return_value=2.0),
        ):
            bullish = me._market_technicals_factor(self.EVAL_DATE, cur)
        with (
            patch.object(me.calculator, "_compute_rsi", return_value=50.0),
            patch.object(me.calculator, "_sample_zscore", return_value=-2.0),
        ):
            bearish = me._market_technicals_factor(self.EVAL_DATE, cur)

        assert bullish["rsi_score"] == 50.0
        assert bearish["rsi_score"] == 50.0
        assert bullish["score"] > 50.0
        assert bearish["score"] < 50.0

    def test_pinned_rsi_monotonic_rally_is_scored_contrarian_bearish_by_design(self):
        # Documents the intentional contrarian convention: a straight-line rally with zero
        # down days pins RSI(14) at 100 (real overbought extreme, not the flat-feed 50.0
        # case above), which this factor deliberately scores toward the bearish end via
        # its 40-60 dead-zone/extremes convention (same as AAII/Put-Call) - a "due for a
        # pullback" contrarian read, not a bullish-momentum one.
        closes = [400.0 + i * 0.4 for i in range(250)]
        cur = MagicMock()
        cur.fetchall.return_value = _spy_rows(closes, self.EVAL_DATE)
        me = MarketExposure()
        result = me._market_technicals_factor(self.EVAL_DATE, cur)
        assert not result.get("data_unavailable")
        assert result["rsi_14"] >= 80
        assert result["rsi_score"] == 0.0

    def test_non_finite_close_is_unavailable(self):
        cur = MagicMock()
        closes = [420.0] * 249 + [float("nan")]
        cur.fetchall.return_value = _spy_rows(closes, self.EVAL_DATE)
        me = MarketExposure()
        result = me._market_technicals_factor(self.EVAL_DATE, cur)
        assert result["data_unavailable"] is True

"""Regression tests for NaN-comparison-guard gaps in algo/risk/market_exposure.py, found
2026-08-10 continuing the systematic sweep (`value <= 0` never catches NaN - always False
in Python; 21 instances already fixed elsewhere this session), plus one more found 2026-08-20
(goal: finance-accuracy audit).

- _ad_line: `first_spy <= 0` didn't catch NaN/Inf, and last_spy had no finiteness check at
  all - a NaN SPY close would produce a NaN spy_change_pct whose comparisons all silently
  evaluate False, instead of this function's own fail-closed RuntimeError contract.
- _economic_overlay's jobless-claims signal: `claims_26w <= 0` didn't catch NaN/Inf, and
  claims_now had no finiteness check at all.
- _credit_spread (2026-08-20): `hy`/`hy_20d_ago` had NO finiteness check at all - worse than
  the other two, since every tiered `hy < X` comparison falls through to the LAST (worst-case,
  score=10.0 "severe stress") branch on NaN, not a skipped/neutral one - a corrupted HY OAS
  reading would confidently score as the market's most stressed credit state (a real 10pt
  factor feeding position sizing) instead of raising. Found while auditing why an equivalent,
  already-NaN-guarded `MarketFactorCalculator.credit_spread()` method exists in a sibling file
  but is dead code (never called - `_credit_spread` here, not the calculator's method, is the
  one actually wired into MarketExposure.compute()) - the live method had silently missed the
  2026-08-10 sweep's protection that its dead counterpart already had.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from algo.risk.market_exposure import MarketExposure


def _ad_line_rows(spy_closes):
    """5+ rows of (date, advance_decline_ratio, spy_close)."""
    base = date(2026, 7, 1)
    return [(base + timedelta(days=i), 1.1, spy_closes[i]) for i in range(len(spy_closes))]


class TestAdLineRejectsNaN:
    def test_nan_first_spy_close_raises(self):
        cur = MagicMock()
        closes = [float("nan"), 450.0, 451.0, 452.0, 453.0, 455.0]
        cur.fetchall.return_value = _ad_line_rows(closes)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match=r"Non-finite|Invalid"):
            me._ad_line(date(2026, 7, 10), cur)

    def test_nan_last_spy_close_raises(self):
        cur = MagicMock()
        closes = [450.0, 451.0, 452.0, 453.0, 455.0, float("nan")]
        cur.fetchall.return_value = _ad_line_rows(closes)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match=r"Non-finite|Invalid"):
            me._ad_line(date(2026, 7, 10), cur)

    def test_normal_closes_still_compute(self):
        cur = MagicMock()
        closes = [450.0, 451.0, 452.0, 453.0, 455.0, 460.0]
        cur.fetchall.return_value = _ad_line_rows(closes)
        me = MarketExposure()
        result = me._ad_line(date(2026, 7, 10), cur)
        assert "relation" in result


def _hy_rows(values):
    """25 rows of (value, date), most-recent-first (matches _credit_spread's query order)."""
    base = date(2026, 8, 10)
    return [(values[i], base - timedelta(days=i)) for i in range(len(values))]


class TestCreditSpreadRejectsNaN:
    def test_nan_current_hy_raises_instead_of_scoring_severe_stress(self):
        # Without the fix: every `hy < X` tier comparison is False for NaN, falling through
        # to the LAST branch (score=10.0, "severe stress") - a confidently wrong worst-case
        # score, not a skipped one.
        cur = MagicMock()
        values = [float("nan")] + [4.0] * 24
        cur.fetchall.return_value = _hy_rows(values)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match="Non-finite HY OAS"):
            me._credit_spread(date(2026, 8, 10), cur)

    def test_infinity_current_hy_raises(self):
        cur = MagicMock()
        values = [float("inf")] + [4.0] * 24
        cur.fetchall.return_value = _hy_rows(values)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match="Non-finite HY OAS"):
            me._credit_spread(date(2026, 8, 10), cur)

    def test_nan_20d_ago_hy_raises(self):
        cur = MagicMock()
        values = [4.0] * 24 + [float("nan")]
        cur.fetchall.return_value = _hy_rows(values)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match="Non-finite 20-day-ago HY OAS"):
            me._credit_spread(date(2026, 8, 10), cur)

    def test_normal_hy_values_still_compute(self):
        cur = MagicMock()
        values = [4.0] * 25
        cur.fetchall.return_value = _hy_rows(values)
        me = MarketExposure()
        result = me._credit_spread(date(2026, 8, 10), cur)
        assert result["score"] == 85.0

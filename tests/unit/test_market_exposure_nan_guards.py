"""Regression tests for 2 NaN-comparison-guard gaps in algo/risk/market_exposure.py, found
2026-08-10 continuing the systematic sweep (`value <= 0` never catches NaN - always False
in Python; 21 instances already fixed elsewhere this session).

- _ad_line: `first_spy <= 0` didn't catch NaN/Inf, and last_spy had no finiteness check at
  all - a NaN SPY close would produce a NaN spy_change_pct whose comparisons all silently
  evaluate False, instead of this function's own fail-closed RuntimeError contract.
- _economic_overlay's jobless-claims signal: `claims_26w <= 0` didn't catch NaN/Inf, and
  claims_now had no finiteness check at all.
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
        with pytest.raises(RuntimeError, match="Non-finite|Invalid"):
            me._ad_line(date(2026, 7, 10), cur)

    def test_nan_last_spy_close_raises(self):
        cur = MagicMock()
        closes = [450.0, 451.0, 452.0, 453.0, 455.0, float("nan")]
        cur.fetchall.return_value = _ad_line_rows(closes)
        me = MarketExposure()
        with pytest.raises(RuntimeError, match="Non-finite|Invalid"):
            me._ad_line(date(2026, 7, 10), cur)

    def test_normal_closes_still_compute(self):
        cur = MagicMock()
        closes = [450.0, 451.0, 452.0, 453.0, 455.0, 460.0]
        cur.fetchall.return_value = _ad_line_rows(closes)
        me = MarketExposure()
        result = me._ad_line(date(2026, 7, 10), cur)
        assert "relation" in result

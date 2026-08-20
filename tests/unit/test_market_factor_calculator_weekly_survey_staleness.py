"""Regression test: MarketFactorCalculator.aaii()/naaim() must reject stale weekly-survey
readings instead of silently using "most recent, however old" data forever.

BUG FOUND 2026-08-11: every daily factor in market_factor_calculator.py (e.g. the SPY
selling-pressure check) enforces freshness and raises if the data is stale, but the two
weekly-survey factors (AAII sentiment, NAAIM exposure) had `SELECT ... WHERE date <= %s
ORDER BY date DESC LIMIT 1` with no staleness bound at all - if either loader silently
stopped running for weeks, these factors would keep feeding an arbitrarily old contrarian
signal into risk/exposure scoring with zero warning. Fixed with a 21-day tolerance (generous
for a weekly survey - never false-positives on normal operation, still catches a genuinely
dead loader).

FIXED 2026-08-20: NAAIM's public page has required a subscription since 2026-08-01 with no
free source left - live-confirmed 19 consecutive days of the staleness check below raising
and taking the entire 12-factor market exposure composite down with it. naaim() now degrades
gracefully (data_unavailable marker, same as put_call_ratio's precedent) instead of raising,
so market_exposure.py can skip just this 5pt factor. aaii() is unchanged (still hard-fails) -
its source hasn't suffered the same permanent loss.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.risk.market_factor_calculator import MarketFactorCalculator


@pytest.fixture
def calc():
    return MarketFactorCalculator()


class TestAaiiStaleness:
    def test_fresh_reading_within_tolerance_succeeds(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (30.0, 25.0, date(2026, 8, 6))
        result = calc.aaii(date(2026, 8, 11), cur)
        assert result["score"] == 50  # neutral spread

    def test_reading_exactly_at_boundary_succeeds(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (30.0, 25.0, date(2026, 7, 21))  # exactly 21 days
        result = calc.aaii(date(2026, 8, 11), cur)
        assert result["score"] == 50

    def test_stale_reading_beyond_tolerance_raises(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (30.0, 25.0, date(2026, 7, 1))  # 41 days stale
        with pytest.raises(RuntimeError, match="stale"):
            calc.aaii(date(2026, 8, 11), cur)


class TestNaaimStaleness:
    def test_fresh_reading_within_tolerance_succeeds(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (60.0, date(2026, 8, 6))
        result = calc.naaim(date(2026, 8, 11), cur)
        assert result["value"] == 60.0

    def test_stale_reading_beyond_tolerance_degrades_gracefully(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (60.0, date(2026, 7, 1))  # 41 days stale
        result = calc.naaim(date(2026, 8, 11), cur)
        assert result["data_unavailable"] is True
        assert "stale" in result["reason"]

    def test_no_reading_at_all_degrades_gracefully(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = None
        result = calc.naaim(date(2026, 8, 11), cur)
        assert result["data_unavailable"] is True

    def test_non_finite_value_still_raises(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (float("nan"), date(2026, 8, 6))
        with pytest.raises(RuntimeError, match="Non-finite"):
            calc.naaim(date(2026, 8, 11), cur)

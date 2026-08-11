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

    def test_stale_reading_beyond_tolerance_raises(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (60.0, date(2026, 7, 1))  # 41 days stale
        with pytest.raises(RuntimeError, match="stale"):
            calc.naaim(date(2026, 8, 11), cur)

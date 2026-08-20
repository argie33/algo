"""Regression test: MarketFactorCalculator.aaii() must reject stale weekly-survey readings
instead of silently using "most recent, however old" data forever.

BUG FOUND 2026-08-11: every daily factor in market_factor_calculator.py (e.g. the SPY
selling-pressure check) enforces freshness and raises if the data is stale, but the
weekly-survey factors (AAII sentiment, formerly also NAAIM exposure) had
`SELECT ... WHERE date <= %s ORDER BY date DESC LIMIT 1` with no staleness bound at all -
if the loader silently stopped running for weeks, this factor would keep feeding an
arbitrarily old contrarian signal into risk/exposure scoring with zero warning. Fixed with
a 21-day tolerance (generous for a weekly survey - never false-positives on normal
operation, still catches a genuinely dead loader).

REPLACED 2026-08-20: NAAIM's public page has required a subscription since 2026-08-01 with
no free source left - live-confirmed 19 consecutive days of the staleness check below
raising and taking the entire 12-factor market exposure composite down with it. NAAIM was
replaced by MarketFactorCalculator.positioning() (insider buying breadth + short interest
trend, both official-source SEC/FINRA filings rather than a voluntary self-reported survey)
- its own staleness/sample-size behavior is covered in
test_market_factor_calculator_nan_infinity_pathological_inputs.py's
TestPositioningRejectsNonFiniteShortInterestAvg, since it degrades gracefully (data_unavailable
marker) rather than following this file's raise-on-stale weekly-survey pattern. aaii() is
unchanged (still hard-fails) - its source hasn't suffered the same permanent loss.
"""

from datetime import date
from unittest.mock import MagicMock

import psycopg2
import pytest

from algo.risk.market_factor_calculator import MarketFactorCalculator


@pytest.fixture
def calc():
    return MarketFactorCalculator()


class TestAaiiStaleness:
    # aaii_sentiment.bullish/bearish are stored as fractions of 1 (e.g. 0.30 = 30%), not
    # percentage-points - aaii() converts internally (see its "confirmed live 2026-08-20"
    # comment). Mock values below use the real fraction scale so the spread math (and the
    # 5pp gap -> neutral expectation) matches production.
    def test_fresh_reading_within_tolerance_succeeds(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (0.30, 0.25, date(2026, 8, 6))
        result = calc.aaii(date(2026, 8, 11), cur)
        assert result["score"] == 50  # neutral spread

    def test_reading_exactly_at_boundary_succeeds(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (0.30, 0.25, date(2026, 7, 21))  # exactly 21 days
        result = calc.aaii(date(2026, 8, 11), cur)
        assert result["score"] == 50

    def test_stale_reading_beyond_tolerance_raises(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = (0.30, 0.25, date(2026, 7, 1))  # 41 days stale
        with pytest.raises(RuntimeError, match="stale"):
            calc.aaii(date(2026, 8, 11), cur)


class TestPositioningGracefulDegradation:
    """positioning() replaced naaim() 2026-08-20 - see module docstring. Full coverage of
    its blend/fallback logic lives in test_market_factor_calculator_nan_infinity_pathological_inputs.py;
    this class covers the two simplest edges directly relevant to graceful degradation.
    """

    def test_no_data_at_all_degrades_gracefully(self, calc):
        cur = MagicMock()
        cur.fetchone.return_value = None  # _insider_buying_breadth's query returns no row
        cur.fetchall.return_value = []  # _short_interest_trend's cycles query returns none
        result = calc.positioning(date(2026, 8, 11), cur)
        assert result["data_unavailable"] is True

    def test_db_error_degrades_gracefully_not_raise(self, calc):
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection reset")
        result = calc.positioning(date(2026, 8, 11), cur)
        assert result["data_unavailable"] is True

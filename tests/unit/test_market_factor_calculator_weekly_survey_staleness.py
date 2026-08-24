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
raising and taking the entire market exposure composite down with it. NAAIM was replaced
by MarketFactorCalculator.positioning() (insider buying breadth + short interest trend,
both official-source SEC/FINRA filings rather than a voluntary self-reported survey).
REMOVED 2026-08-23 (pillar redesign, see algo/risk/market_exposure.py's module docstring,
"Dropped entirely" section): positioning() itself was deleted - not covered by the
redesign's evidence framework, and short_interest_finra had only 3 FINRA settlement
cycles of local history, too thin to trust regardless. TestPositioningGracefulDegradation
below is removed along with it. aaii() is unchanged (still hard-fails) - its source
hasn't suffered the same permanent loss, and it's unaffected by the positioning removal.
"""

from datetime import date
from unittest.mock import MagicMock

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


# TestPositioningGracefulDegradation removed 2026-08-23 (pillar redesign) - positioning()
# itself was deleted from MarketFactorCalculator. See module docstring.

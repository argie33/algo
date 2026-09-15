"""Regression test for PriceSanityChecker.check_trading_day_gaps() (added 2026-09-15).

Live-caught gap: none of the pre-existing price_sanity checks catch an isolated missing row
in one symbol's own price_daily history - check_price_moves only looks at the single most
recent date, check_sequence_continuity only checks SPY's own calendar (not per-symbol), and
check_isolated_spike_corruption only considers low-volume yfinance rows as candidates.
Concretely: DELL was missing its 2026-05-29 row, compressing a real 2-day rally into an
apparent 1-day 47% spike that would distort a daily-return-volatility-based momentum calc
while looking like a legitimate mover to every existing check.
"""

import inspect

from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker


class TestTradingDayGaps:
    def test_check_trading_day_gaps_wired_into_run(self):
        source = inspect.getsource(PriceSanityChecker.run)
        assert "check_trading_day_gaps" in source

    def test_check_trading_day_gaps_uses_spy_as_calendar_reference(self):
        source = inspect.getsource(PriceSanityChecker.check_trading_day_gaps)
        assert "symbol = 'SPY'" in source, "must anchor the expected trading-day calendar to SPY"

    def test_check_trading_day_gaps_applies_investability_floor(self):
        source = inspect.getsource(PriceSanityChecker.check_trading_day_gaps)
        assert "value_metrics" in source and "market_cap" in source, (
            "must filter to a market-cap floor - without it this query is swamped by "
            "thousands of thinly-traded rights/warrants that legitimately don't trade "
            "every session, burying real gaps in real actively-traded names"
        )

    def test_check_trading_day_gaps_wires_flagged_symbols_for_quarantine(self):
        source = inspect.getsource(PriceSanityChecker.check_trading_day_gaps)
        assert "flagged_symbols" in source, (
            "ERROR-tier findings must name flagged_symbols so quarantine.py's "
            "apply_symbol_quarantine can exclude just the affected symbols instead of "
            "halting the whole pipeline"
        )
        assert "ERROR" in source

    def test_check_trading_day_gaps_bounds_expected_dates_to_symbols_own_range(self):
        # A real IPO start or delisting end must never be mistaken for a gap - the expected
        # calendar must be bounded to each symbol's own observed min/max date, not the full
        # lookback window.
        source = inspect.getsource(PriceSanityChecker.check_trading_day_gaps)
        assert "min(pd.date)" in source and "max(pd.date)" in source
        assert "BETWEEN sb.min_d AND sb.max_d" in source

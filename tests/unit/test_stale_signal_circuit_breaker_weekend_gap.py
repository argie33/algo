#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: StaleSignalCircuitBreaker.check_signal_freshness()
compared price_daily's latest date against a flat calendar-day threshold (1 day on weekdays,
3 days on weekends) keyed on whether *today* is a trading day. That conflates "is today a
trading day" with "how many calendar days is a normal gap" - on the trading day immediately
after a weekend, days_old is always 3 (Friday's close -> Monday) even though Friday's close is
the correct, most-recent-available data (today's own EOD hasn't posted yet). A weekday threshold
of 1 day would incorrectly open the circuit breaker and block Phase 8 entries for the entire
Monday trading session, every single week.

Reproduced live 2026-07-27 (a real Monday): real wall-clock time, real price_daily MAX date of
2026-07-24 (the prior Friday) computed days_old=3 against the old weekday threshold of 1,
opening the circuit breaker with "Price data 3d old (exceeds 1d threshold)" - discovered by
running Phase 8 with its market-hours guard bypassed (a dedicated live probe, since normal
testing before 9:30 AM ET never reaches this check).

Fixed to compare against the actual previous trading day (MarketCalendar.get_previous_trading_day),
matching the same trading-day-aware pattern already used by Phase 1 (price_daily) and Phase 7
(buy_sell_daily lookback, fixed the same session).
"""

from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from algo.risk.stale_signal_circuit_breaker import StaleSignalCircuitBreaker


def _mock_db(price_date, signal_date):
    """Patch DatabaseContext to answer the two MAX(date) queries in call order."""
    cur = MagicMock()
    cur.fetchone.side_effect = [(price_date,), (signal_date,)]

    @contextmanager
    def _ctx(role):
        yield cur

    return patch("algo.risk.stale_signal_circuit_breaker.DatabaseContext", side_effect=_ctx)


def _fake_utcnow(real_et_date):
    """Return a datetime whose UTC->ET conversion lands on real_et_date at midday ET."""
    return datetime(real_et_date.year, real_et_date.month, real_et_date.day, 16, 0, tzinfo=timezone.utc)


class TestStaleSignalCircuitBreakerWeekendGap:
    def test_monday_with_fridays_close_is_not_stale(self):
        """The core bug: Monday, price_daily's latest row is Friday's close (3 calendar
        days old) - must be treated as FRESH, not stale."""
        monday = date(2026, 7, 27)
        friday_close = date(2026, 7, 24)

        with _mock_db(friday_close, friday_close), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(monday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is True, f"Expected Friday's close to be FRESH on Monday, got: {msg}"

    def test_day_after_holiday_with_prior_trading_days_close_is_not_stale(self):
        """2026-01-20 is the day after MLK Day (2026-01-19); prior trading day is 2026-01-16."""
        day_after_holiday = date(2026, 1, 20)
        prior_trading_day_close = date(2026, 1, 16)

        with _mock_db(prior_trading_day_close, prior_trading_day_close), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(day_after_holiday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is True, f"Expected pre-holiday close to be FRESH the day after, got: {msg}"

    def test_genuinely_stale_data_still_blocks(self):
        """Sanity check: the fix must not silently disable the guard - data older than the
        actual previous trading day must still open the circuit breaker."""
        monday = date(2026, 7, 27)
        stale_date = date(2026, 7, 20)  # the Monday before - a full extra week stale

        with _mock_db(stale_date, stale_date), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(monday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is False
        assert "old" in msg.lower()

    def test_midweek_one_day_lag_is_not_stale(self):
        """Sanity check: normal Tuesday-with-Monday's-close case must still pass."""
        tuesday = date(2026, 7, 21)
        mondays_close = date(2026, 7, 20)

        with _mock_db(mondays_close, mondays_close), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(tuesday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is True, f"Expected yesterday's close to be FRESH mid-week, got: {msg}"

    def test_signals_lagging_price_by_one_day_is_acceptable(self):
        """Phase 8 blocking fix: signals naturally lag price_daily by 1 trading day.
        Today's technical indicators need yesterday's close to compute them.
        This is normal operation, not stale data - must NOT block Phase 8."""
        tuesday = date(2026, 7, 21)
        todays_price = date(2026, 7, 21)  # Tuesday's close (EOD loader just finished)
        yesterdays_signal = date(2026, 7, 20)  # Monday's signal (computed from Friday's close)

        with _mock_db(todays_price, yesterdays_signal), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(tuesday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is True, f"Expected 1-day signal lag to be FRESH (normal), got: {msg}"
        assert "fresh" in msg.lower()

    def test_signals_lagging_by_more_than_one_day_is_stale(self):
        """Sanity check: if signals lag price data by more than 1 trading day, block."""
        tuesday = date(2026, 7, 21)
        todays_price = date(2026, 7, 21)  # Tuesday's close
        week_old_signal = date(2026, 7, 14)  # Previous Tuesday's signal (> 1 day stale)

        with _mock_db(todays_price, week_old_signal), \
             patch("algo.risk.stale_signal_circuit_breaker.datetime") as mock_dt:
            mock_dt.now.return_value = _fake_utcnow(tuesday)
            is_safe, msg = StaleSignalCircuitBreaker.check_signal_freshness()

        assert is_safe is False
        assert "lag" in msg.lower()

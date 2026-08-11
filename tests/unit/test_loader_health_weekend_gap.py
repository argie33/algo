"""Regression test for the 2026-07-27 fix: Orchestrator._check_loader_health()'s "before
market open / after market close" staleness threshold was a flat 36 hours, which cannot span
a Friday->Monday weekend (~63h) or a day-after-holiday gap. On a real Monday premarket run,
every critical loader whose last successful run was Friday's EOD pipeline would be flagged
"STALE" - and since the systemic-escalation check a few lines down requires ALL critical
loaders to be non-stale to avoid firing, that's the *normal* Monday-morning state in
production (all loaders share one schedule), not a rare edge case. In production (non
LOCAL_MODE) this raises a "SYSTEMIC ALERT ... CRITICAL HALT" RuntimeError and sends a real
position alert (email/SNS) claiming EventBridge/loader infrastructure is down - a false alarm
that would fire every single Monday and every day-after-holiday morning.

Live-reproduced 2026-07-27 (a real Monday): price_daily/technical_data_daily/etc. all last
ran Friday 2026-07-24's EOD pipeline (~63h before an 08:16 ET Monday run) and were flagged
STALE under the old flat-36h threshold.

Fixed to anchor the threshold to the actual previous trading day's EOD pipeline completion
(MarketCalendar.get_previous_trading_day), matching the same trading-day-aware pattern
already used by Phase 1 freshness, Phase 7's BUY-signal lookback, and Phase 8's stale-signal
circuit breaker.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    self = object.__new__(Orchestrator)
    self.alerts = MagicMock()
    return self


def _run_check(rows, fake_utc_now):
    cur = MagicMock()
    cur.fetchall.return_value = rows

    @contextmanager
    def _ctx(role, timeout=5):
        yield cur

    with (
        patch("algo.orchestration.orchestrator.DatabaseContext", side_effect=_ctx),
        patch("algo.orchestration.orchestrator.datetime") as mock_dt,
    ):
        mock_dt.now.return_value = fake_utc_now
        mock_dt.combine = datetime.combine  # delegate to the real implementation
        Orchestrator._check_loader_health(_fake_self())


class TestLoaderHealthWeekendGap:
    def test_fridays_data_not_stale_on_monday_premarket(self):
        """The core bug: Friday's close is the correct, most-recent-available data on a
        Monday premarket run - must not be flagged STALE."""
        friday_close_naive = datetime(2026, 7, 24, 17, 0, 0)  # naive ET, matches DB convention
        monday_premarket_utc = datetime(2026, 7, 27, 12, 16, tzinfo=timezone.utc)  # 08:16 ET

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", friday_close_naive, 100.0, 5000, 5000)],
                fake_utc_now=monday_premarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, f"Friday's close must not be flagged stale on Monday premarket: {stale_warnings}"

    def test_genuinely_stale_data_still_flagged_on_monday(self):
        """Sanity check: the fix must not silently disable the check - data older than the
        actual previous trading day (Friday) must still be flagged."""
        stale_naive = datetime(2026, 7, 17, 17, 0, 0)  # the Friday before - a full extra week stale
        monday_premarket_utc = datetime(2026, 7, 27, 12, 16, tzinfo=timezone.utc)

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", stale_naive, 100.0, 5000, 5000)],
                fake_utc_now=monday_premarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert stale_warnings, "data from a full week ago must still be flagged stale"

    def test_yesterdays_close_not_stale_midweek_postmarket(self):
        """Sanity check: normal Tuesday-evening-with-today's-close case must still pass
        (reference day resolves to today itself when today is already a trading day)."""
        tuesday_close_naive = datetime(2026, 7, 21, 17, 0, 0)
        tuesday_postmarket_utc = datetime(2026, 7, 21, 21, 0, tzinfo=timezone.utc)  # 17:00 ET

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", tuesday_close_naive, 100.0, 5000, 5000)],
                fake_utc_now=tuesday_postmarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, f"today's own close must not be flagged stale after market close: {stale_warnings}"


class TestLoaderHealthNonDailyCadence:
    """price_weekly/price_monthly (and ETF counterparts) only update roughly weekly/monthly by
    design - checking them against the daily-trading-day threshold used for daily loaders would
    flag them STALE in literally every health check, forever, training operators to ignore the
    warning (alert fatigue). They get their own wider floor instead."""

    def test_price_weekly_a_few_days_old_is_not_stale(self):
        recent_weekly = datetime(2026, 7, 20, 17, 0, 0)  # ~7 days before the Monday check below
        monday_premarket_utc = datetime(2026, 7, 27, 12, 16, tzinfo=timezone.utc)

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_weekly", "completed", recent_weekly, 100.0, 5000, 5000)],
                fake_utc_now=monday_premarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, f"a ~7-day-old weekly loader run must not be flagged stale: {stale_warnings}"

    def test_price_monthly_a_few_weeks_old_is_not_stale(self):
        recent_monthly = datetime(2026, 7, 1, 17, 0, 0)  # ~26 days before the Monday check below
        monday_premarket_utc = datetime(2026, 7, 27, 12, 16, tzinfo=timezone.utc)

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_monthly", "completed", recent_monthly, 100.0, 5000, 5000)],
                fake_utc_now=monday_premarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, f"a ~26-day-old monthly loader run must not be flagged stale: {stale_warnings}"

    def test_genuinely_stale_weekly_data_still_flagged(self):
        very_old_weekly = datetime(2026, 6, 1, 17, 0, 0)  # ~56 days stale - real gap
        monday_premarket_utc = datetime(2026, 7, 27, 12, 16, tzinfo=timezone.utc)

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_weekly", "completed", very_old_weekly, 100.0, 5000, 5000)],
                fake_utc_now=monday_premarket_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert stale_warnings, "a genuinely stale (56-day-old) weekly loader run must still be flagged"

    def test_earnings_calendar_a_few_days_old_is_not_stale(self):
        """earnings_calendar is forward-looking calendar data (see
        pipeline_health.py CRITICAL_TABLES sla_days=30) - a several-day gap since the last new
        announcement is normal, not a broken loader. Live-reproduced 2026-07-27: flagged STALE
        at 105.2h (~4.4 days) old under the daily-trading-day threshold."""
        recent_earnings = datetime(2026, 7, 23, 0, 0, 0)  # ~4.4 days before the check below
        monday_market_hours_utc = datetime(2026, 7, 27, 13, 7, tzinfo=timezone.utc)  # 09:07 ET

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("earnings_calendar", "completed", recent_earnings, 100.0, 5000, 5000)],
                fake_utc_now=monday_market_hours_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, f"a ~4.4-day-old earnings_calendar run must not be flagged stale: {stale_warnings}"

    def test_genuinely_stale_earnings_calendar_still_flagged(self):
        very_old_earnings = datetime(2026, 5, 1, 0, 0, 0)  # ~87 days stale - real gap
        monday_market_hours_utc = datetime(2026, 7, 27, 13, 7, tzinfo=timezone.utc)

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("earnings_calendar", "completed", very_old_earnings, 100.0, 5000, 5000)],
                fake_utc_now=monday_market_hours_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert stale_warnings, "a genuinely stale (87-day-old) earnings_calendar run must still be flagged"


class TestLoaderHealthMarketHoursFlatWindow:
    """Regression test for a second, related 2026-07-27 fix: the "during market hours"
    (9 AM-4 PM ET) branch used a flat 13-hour threshold, separate from the trading-day-anchored
    logic above. That flat window assumed `last_updated` is a precise per-run completion
    timestamp - true when originally written, but pipeline_health.py's log_health_check() now
    deliberately writes last_updated = latest_date (the loaded row's own business date, at
    midnight ET) for nearly every tracked table. Measured from a midnight-anchored
    last_updated, a flat 13h window breaches on literally EVERY trading morning (yesterday's
    close is always >13h before "now" during market hours), not just after a weekend gap.

    Live-reproduced 2026-07-27: a real Monday 09:07 AM ET dry run (inside the old 9 AM-4 PM
    branch) flagged price_daily/etf_price_daily/technical_data_daily all STALE at "81.1h ago"
    despite Friday's close (stored as last_updated=2026-07-24 00:00:00, confirmed live via
    direct DB query) being the correct, most-recent-available data.
    """

    def test_fridays_close_not_stale_monday_market_hours(self):
        """The exact live-reproduced bug: Friday's close, during Monday market hours."""
        friday_close_midnight = datetime(2026, 7, 24, 0, 0, 0)  # matches real DB convention
        monday_market_hours_utc = datetime(2026, 7, 27, 13, 7, tzinfo=timezone.utc)  # 09:07 ET

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", friday_close_midnight, 100.0, 5000, 5000)],
                fake_utc_now=monday_market_hours_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, (
            f"Friday's close must not be flagged stale during Monday market hours: {stale_warnings}"
        )

    def test_yesterdays_close_not_stale_normal_tuesday_market_hours(self):
        """The broader bug: even a completely normal (non-weekend) trading morning breaches
        the old flat 13h window, since yesterday's midnight-anchored close is always >13h
        before a market-hours "now"."""
        monday_close_midnight = datetime(2026, 7, 27, 0, 0, 0)
        tuesday_market_hours_utc = datetime(2026, 7, 28, 13, 7, tzinfo=timezone.utc)  # 09:07 ET Tue

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", monday_close_midnight, 100.0, 5000, 5000)],
                fake_utc_now=tuesday_market_hours_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert not stale_warnings, (
            f"yesterday's close must not be flagged stale on a normal trading morning: {stale_warnings}"
        )

    def test_genuinely_stale_data_still_flagged_during_market_hours(self):
        """Sanity check: the fix must not silently disable the check during market hours."""
        stale_naive = datetime(2026, 7, 17, 0, 0, 0)  # the Friday before - a full extra week stale
        monday_market_hours_utc = datetime(2026, 7, 27, 13, 7, tzinfo=timezone.utc)  # 09:07 ET

        with patch("logging.Logger.warning") as mock_warn:
            _run_check(
                rows=[("price_daily", "completed", stale_naive, 100.0, 5000, 5000)],
                fake_utc_now=monday_market_hours_utc,
            )

        stale_warnings = [c for c in mock_warn.call_args_list if "is STALE" in str(c)]
        assert stale_warnings, "data from a full week ago must still be flagged stale during market hours"

"""Regression test for a 2026-08-20 fix (goal: finance-accuracy audit) to
utils/loaders/sla_monitor.py's earnings_calendar SLA target.

The old (10, 30, 60)-minute (expected, warn, critical) targets were stale - live-confirmed via
logs/scheduler_invocations.log: 8 real runs over 2026-08-16 through 2026-08-20 (every day
sampled) took 62.3-75.3 min (avg 66.3 min), firing a false "CRITICAL: exceeded 60 min SLA" alert
on literally every single run, not a genuine hang/failure.
loaders/loader_timeout_config.py's own earnings_calendar entry was already recalibrated to a
generous 180 min hard timeout for this same real measured duration, but this separate alerting
threshold was never updated to match.

An alert that fires on every single normal run stops functioning as a signal - it trains
whoever's watching to ignore "CRITICAL" for this loader, which is exactly the condition under
which a genuine hang would go unnoticed.
"""

from utils.loaders.sla_monitor import LOADER_SLA_TARGETS


class TestEarningsCalendarRealisticThresholds:
    def test_real_observed_durations_do_not_trigger_critical(self) -> None:
        """The 8 real, successful run durations observed this session must all fall below
        the critical threshold - a normal run must never cross this line."""
        _, _, critical_seconds = LOADER_SLA_TARGETS["earnings_calendar"]
        observed_minutes = [65.4, 62.3, 75.3, 63.9, 66.5, 64.5, 66.4, 66.1]

        for minutes in observed_minutes:
            assert minutes * 60 < critical_seconds, (
                f"A real, successful {minutes}-minute run would still trigger a false CRITICAL "
                f"alert (threshold={critical_seconds / 60:.0f}min)"
            )

    def test_thresholds_stay_safely_under_the_hard_timeout(self) -> None:
        """The critical alert must fire before the loader would actually be killed by its
        real hard timeout (loader_timeout_config.py: 180 min), so an operator gets warning
        before the run is lost outright."""
        _, _, critical_seconds = LOADER_SLA_TARGETS["earnings_calendar"]
        hard_timeout_seconds = 180 * 60

        assert critical_seconds < hard_timeout_seconds

    def test_ordering_still_holds(self) -> None:
        expected, warn, critical = LOADER_SLA_TARGETS["earnings_calendar"]
        assert expected < warn < critical

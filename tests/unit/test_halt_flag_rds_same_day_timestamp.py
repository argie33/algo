"""Regression test for the 2026-07-27 halt_flag_manager.py RDS-fallback same-day crash.

_set_halt_flag_rds writes halt_triggered_at as now_utc.isoformat() - a genuinely UTC
value - into algo_runtime_state's `timestamp without time zone` column. Confirmed live:
Postgres's cast from a tz-aware ISO string into that column type drops the offset but
keeps the wall-clock digits verbatim (does not convert via the session timezone), so a
naive value read back is UTC digits, not Eastern.

_check_halt_flag_rds mislabeled that naive value as Eastern via .replace(tzinfo=EASTERN_TZ)
when building trigger_et, while leaving the original `trigger_dt` naive. The very next
same-day branch then computed `now_utc - trigger_dt` - subtracting an aware datetime from
a naive one - which raised TypeError on every real same-day active halt read via the RDS
fallback path (the only path exercised in local dev, and the fallback path in prod
whenever DynamoDB has any transient issue). The crash was caught by a broad
except (ValueError, KeyError, TypeError), silently dropping the halt's real reason and
duration from the CRITICAL log in favor of a generic "could not parse timestamp" warning.
The system still correctly failed closed (returned True), so this was not a trading-safety
bug, but it destroyed the operator-facing diagnosis of an active halt precisely when it
mattered most.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.orchestration.halt_flag_manager import HaltFlagManager


def _manager() -> HaltFlagManager:
    return HaltFlagManager(alerts=MagicMock(), log_phase_result=MagicMock())


def _mock_db_context(row):
    cur = MagicMock()
    cur.fetchone.return_value = row
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestHaltFlagRdsSameDayNaiveTimestamp:
    # Fixed instant well after market open ET, so "2 hours earlier" is guaranteed to land
    # on the same ET calendar day. Using the real, unmocked datetime.now() here (as this
    # test previously did) makes the test's own "same calendar day" premise wall-clock
    # dependent - it silently broke for ~2 hours every night whenever the suite happened
    # to run between midnight and 2 AM ET, since "2 hours ago" then falls on the *previous*
    # ET calendar day and the code correctly (and intentionally) takes the "still active
    # before market open" info-log branch instead of the same-day critical-log branch this
    # test asserts on - not a code bug, a flaky, time-dependent test.
    _FAKE_NOW_UTC = datetime(2026, 7, 27, 18, 0, 0, tzinfo=timezone.utc)  # 2:00 PM EDT

    def test_same_day_active_halt_does_not_crash_and_reports_hours_halted(self):
        """The exact live-reproduced bug: a same-day halt_triggered_at stored as naive
        UTC digits (matching real DB round-trip behavior) must not crash the subtraction
        and must produce a real hours-halted figure in the CRITICAL log, not fall through
        to the generic "could not parse timestamp" path."""
        manager = _manager()
        naive_utc_triggered_at = self._FAKE_NOW_UTC.replace(tzinfo=None) - timedelta(hours=2)
        row = (True, "stale data detected", naive_utc_triggered_at, {"halt_triggered_by": "phase1_data_freshness"})

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self._FAKE_NOW_UTC if tz is not None else self._FAKE_NOW_UTC.replace(tzinfo=None)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.logger") as mock_logger,
            patch("algo.orchestration.halt_flag_manager.datetime", _FrozenDatetime),
        ):
            result = manager._check_halt_flag_rds()

        assert result is True

        parse_warnings = [c for c in mock_logger.warning.call_args_list if "Could not parse RDS timestamp" in str(c)]
        assert not parse_warnings, (
            f"same-day naive-UTC timestamp must parse cleanly, not fall through: {parse_warnings}"
        )

        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("Triggered" in c and "h ago" in c for c in critical_calls), (
            f"expected a real hours-halted figure in the CRITICAL log, got: {critical_calls}"
        )
        assert any("could not parse timestamp" not in c for c in critical_calls)

    def test_same_day_active_halt_reason_preserved_in_critical_log(self):
        manager = _manager()
        naive_utc_triggered_at = self._FAKE_NOW_UTC.replace(tzinfo=None)
        row = (
            True,
            "Phase 1 degraded: stale data detected",
            naive_utc_triggered_at,
            {"halt_triggered_by": "phase1_data_freshness"},
        )

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return self._FAKE_NOW_UTC if tz is not None else self._FAKE_NOW_UTC.replace(tzinfo=None)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.logger") as mock_logger,
            patch("algo.orchestration.halt_flag_manager.datetime", _FrozenDatetime),
        ):
            manager._check_halt_flag_rds()

        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("Phase 1 degraded: stale data detected" in c for c in critical_calls), critical_calls


class TestProactiveClearRdsDateRolloverWindow:
    """_proactive_clear_stale_halt_rds shares the same root cause: mislabeling a naive
    (genuinely-UTC) halt_triggered_at as Eastern shifts trigger_date forward by the
    ET-UTC offset. For a halt genuinely triggered late evening ET (already past midnight
    UTC), this pushes trigger_date from "yesterday" to "today" - so the
    previous-trading-day auto-clear branch (ISSUE #31's startup-deadlock fix) never
    fires for exactly the halts most likely to still be sitting there the next morning.
    """

    def test_late_evening_et_halt_still_auto_clears_next_morning(self):
        # Real instant: 2026-07-26 23:00 ET (11 PM Saturday ET, EDT = UTC-4) = 2026-07-27
        # 03:00 UTC. Confirmed DB round-trip behavior: the naive value read back from
        # `timestamp without time zone` is exactly these UTC digits, no offset applied.
        naive_utc_triggered_at = datetime(2026, 7, 27, 3, 0, 0)
        fake_now_utc = datetime(2026, 7, 27, 14, 0, 0, tzinfo=timezone.utc)  # 10:00 AM EDT - past market open

        manager = _manager()
        row = (True, naive_utc_triggered_at, {"halt_triggered_by": "phase1_data_freshness"})

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now_utc if tz is not None else fake_now_utc.replace(tzinfo=None)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.datetime", _FrozenDatetime),
        ):
            cleared = manager._proactive_clear_stale_halt_rds()

        assert cleared is True, (
            "a halt genuinely triggered late evening ET the prior day must still be "
            "recognized as stale and auto-cleared the next morning past market open - "
            "not silently kept alive by mislabeling its UTC timestamp as Eastern"
        )

    def test_manual_operator_halt_not_auto_cleared_at_startup(self):
        """Regression test for the 2026-08-10 bug: this proactive-clear path (runs at
        orchestrator STARTUP, before Phase 1 or any other phase reasoning) used to
        auto-clear ANY prior-day halt purely on calendar rollover with zero check of who
        set it - so a manual operator kill-switch halt would be silently wiped the very
        next trading day at market open, regardless of whether the operator's underlying
        investigation was ever resolved."""
        naive_utc_triggered_at = datetime(2026, 7, 27, 3, 0, 0)
        fake_now_utc = datetime(2026, 7, 27, 14, 0, 0, tzinfo=timezone.utc)  # past market open

        manager = _manager()
        row = (True, naive_utc_triggered_at, {"halt_triggered_by": "manual_operator"})

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now_utc if tz is not None else fake_now_utc.replace(tzinfo=None)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.datetime", _FrozenDatetime),
        ):
            cleared = manager._proactive_clear_stale_halt_rds()

        assert cleared is False, (
            "a manual operator halt must NEVER be auto-cleared on pure calendar rollover - "
            "only an explicit scripts/manage_halt_flag.py --clear may resume trading"
        )

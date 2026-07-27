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
    def test_same_day_active_halt_does_not_crash_and_reports_hours_halted(self):
        """The exact live-reproduced bug: a same-day halt_triggered_at stored as naive
        UTC digits (matching real DB round-trip behavior) must not crash the subtraction
        and must produce a real hours-halted figure in the CRITICAL log, not fall through
        to the generic "could not parse timestamp" path."""
        manager = _manager()
        naive_utc_triggered_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        row = (True, "stale data detected", naive_utc_triggered_at)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.logger") as mock_logger,
        ):
            result = manager._check_halt_flag_rds()

        assert result is True

        parse_warnings = [c for c in mock_logger.warning.call_args_list if "Could not parse RDS timestamp" in str(c)]
        assert not parse_warnings, f"same-day naive-UTC timestamp must parse cleanly, not fall through: {parse_warnings}"

        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("Triggered" in c and "h ago" in c for c in critical_calls), (
            f"expected a real hours-halted figure in the CRITICAL log, got: {critical_calls}"
        )
        assert any("could not parse timestamp" not in c for c in critical_calls)

    def test_same_day_active_halt_reason_preserved_in_critical_log(self):
        manager = _manager()
        naive_utc_triggered_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row = (True, "Phase 1 degraded: stale data detected", naive_utc_triggered_at)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.logger") as mock_logger,
        ):
            manager._check_halt_flag_rds()

        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("Phase 1 degraded: stale data detected" in c for c in critical_calls), critical_calls

"""Regression test for a diagnostic gap in HaltFlagManager's "prior trading day, still
before market open" branch (both the DynamoDB and RDS check paths).

A halt triggered late evening ET (e.g. 11 PM) is, by design, still correctly reported as
active (returns True) when checked again before the next market open, even though its
trigger_date is technically "yesterday" in ET once the calendar rolls over midnight. But
the branch handling this case only logged an INFO line with no `reason` and no CRITICAL
alert - unlike the same-day branch a few lines below it, which logs reason + hours-halted
at CRITICAL. This was discovered because test_halt_flag_rds_same_day_timestamp.py's own
"2 hours ago" fixture is time-of-day dependent: it only exercises the same-day branch when
run more than ~2 hours after midnight ET, and happened to hit this exact gap when run
between midnight and market open ET (see this repo's session notes 2026-07-27/28).

An operator watching for CRITICAL halt alerts would see nothing for a genuinely active
halt during the overnight window - the same "operator-facing diagnosis destroyed" bug
class already found twice in this file (see steering/DATA_LOADERS.md / memory
sec_xbrl_companyfacts_limitation-adjacent halt_flag_manager fixes), just triggered by a
day-boundary condition instead of a timestamp-parsing crash.
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


class TestOvernightPriorDayHaltStillCritical:
    def test_rds_path_logs_critical_with_reason_before_market_open(self):
        # Fixed instant: 2026-07-28 03:00 UTC = 2026-07-27 23:00 EDT (11 PM ET the prior
        # calendar day), halt triggered 2h earlier at 01:00 UTC = 2026-07-27 21:00 EDT.
        # now_et (2026-07-27 23:00) is well before the next market open, so trigger_date
        # (07-27) < now_date_et would only differ if "now" rolled past midnight - use a
        # genuinely cross-midnight pair instead: trigger 2026-07-27 23:30 ET, now
        # 2026-07-28 00:30 ET (both before market open).
        fake_now_utc = datetime(2026, 7, 28, 4, 30, 0, tzinfo=timezone.utc)  # 00:30 EDT
        naive_utc_triggered_at = datetime(2026, 7, 28, 2, 30, 0)  # 2026-07-27 22:30 EDT

        manager = _manager()
        row = (True, "stale data detected", naive_utc_triggered_at)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fake_now_utc if tz is not None else fake_now_utc.replace(tzinfo=None)

        with (
            patch("algo.orchestration.halt_flag_manager.DatabaseContext", return_value=_mock_db_context(row)),
            patch("algo.orchestration.halt_flag_manager.datetime", _FrozenDatetime),
            patch("algo.orchestration.halt_flag_manager.logger") as mock_logger,
        ):
            result = manager._check_halt_flag_rds()

        assert result is True

        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert critical_calls, "an active overnight halt must still produce a CRITICAL log, not just INFO"
        assert any("stale data detected" in c for c in critical_calls), (
            f"reason must survive into the CRITICAL log for the overnight prior-day case: {critical_calls}"
        )
        assert any("h ago" in c for c in critical_calls), critical_calls

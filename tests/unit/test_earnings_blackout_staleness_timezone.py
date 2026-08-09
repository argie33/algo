#!/usr/bin/env python3
"""Regression test for the Session 81 earnings_blackout.py staleness timezone fix.

EarningsBlackout.run() computes hours_since_last_load to enforce a 48-hour freshness
gate on earnings_calendar data (added Session 79 after trades entered without knowledge
of next-day earnings). The original implementation did:

    now_et = datetime.now(EASTERN_TZ)
    hours_since_last_load = (now_et.replace(tzinfo=timezone.utc) - last_load_time...).total_seconds() / 3600

.replace(tzinfo=timezone.utc) relabels an Eastern wall-clock reading as UTC without
converting it - understating elapsed hours by the ET/UTC offset (4h EDT / 5h EST). A
load that was actually 50 hours stale would compute as ~45-46 hours, sliding under the
48-hour gate and silently allowing entry on stale earnings data - defeating the exact
fix this function exists to provide.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.risk.earnings_blackout import EarningsBlackout


def _config():
    cfg = {"earnings_blackout_days_before": 7, "earnings_blackout_days_after": 1}
    m = MagicMock()
    m.get.side_effect = lambda k: cfg.get(k)
    return m


def _mock_db_returning(last_load_naive_utc):
    mock_cur = MagicMock()
    # First execute() call: MAX(created_at) staleness check. Second (only reached if not
    # blocked on staleness): earnings_date lookup -> no row (no earnings on file).
    mock_cur.fetchone.side_effect = [(last_load_naive_utc,), None]
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context


class TestEarningsBlackoutStalenessUsesRealUtcElapsedTime:
    def test_load_50_hours_stale_is_blocked(self):
        """A load that is genuinely 50h stale must trip the >48h gate regardless of
        what wall-clock hour it is in US/Eastern when the check runs."""
        blackout = EarningsBlackout(config=_config())
        last_load = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=50)

        with patch(
            "algo.risk.earnings_blackout.DatabaseContext",
            return_value=_mock_db_returning(last_load),
        ):
            result = blackout.run("AAPL", datetime.now(timezone.utc).date())

        assert result["pass"] is False, (
            "50h-stale earnings data must be blocked by the 48h freshness gate - "
            f"got {result}"
        )
        assert "stale" in result["reason"].lower()

    def test_load_10_hours_stale_passes_freshness_gate(self):
        """A genuinely fresh load (well under 48h) must not be blocked by staleness -
        confirms the fix didn't flip the check into always-blocking."""
        blackout = EarningsBlackout(config=_config())
        last_load = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)

        mock_cur = MagicMock()
        # First call: staleness check row. Second call: earnings_date lookup -> no row (no earnings).
        mock_cur.fetchone.side_effect = [(last_load,), None]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("AAPL", datetime.now(timezone.utc).date())

        assert result["pass"] is True, f"10h-stale (fresh) earnings data should not be blocked - got {result}"

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
    # First execute() call: MAX(updated_at) staleness check. Second (only reached if not
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
            f"50h-stale earnings data must be blocked by the 48h freshness gate - got {result}"
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


class TestEarningsBlackoutStalenessChecksUpdatedAtNotCreatedAt:
    """Regression test for the 2026-08-10 fix: the staleness query used MAX(created_at),
    which for an upserted row only reflects its ORIGINAL insertion, never subsequent
    refreshes. Live-reproduced: MSA's created_at was 5 days old while its updated_at was
    hours old (genuinely fresh, actively-maintained data) - the old query incorrectly
    reported it as 123h stale and blocked a real entry. load_earnings_calendar.py
    explicitly maintains updated_at=now() on every write for exactly this purpose;
    phase1_data_freshness.py already correctly keys off it for the same table."""

    def test_staleness_query_uses_updated_at_not_created_at(self) -> None:
        mock_cur = MagicMock()
        mock_cur.fetchone.side_effect = [
            (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10),),
            None,
        ]
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        blackout = EarningsBlackout(config=_config())
        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            blackout.run("MSA", datetime.now(timezone.utc).date())

        staleness_sql = mock_cur.execute.call_args_list[0].args[0]
        assert "MAX(updated_at)" in staleness_sql, (
            f"Expected the staleness check to query MAX(updated_at), got: {staleness_sql}"
        )
        assert "created_at" not in staleness_sql, (
            f"Found created_at again in the staleness query - it only reflects a row's "
            f"original insertion, not refreshes: {staleness_sql}"
        )

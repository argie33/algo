"""Tests for scripts/expire_stale_pending_signals.py.

See that script's own module docstring for the full finding: algo_signals rows stuck in
'pending' past Phase 8's own staleness window (max_signal_age_hours) are never revisited by
any current code path (Phase 7 only looks at "today's" signals since commit 9f13337c2), so they
accumulate forever instead of resolving to a terminal status. This is a standalone housekeeping
script, deliberately not wired into the live orchestrator phases.
"""

from datetime import date, datetime, tzinfo
from unittest.mock import MagicMock, patch

from scripts.expire_stale_pending_signals import (
    expire_stale_pending_signals,
    find_stale_pending_signals,
)
from utils.infrastructure.timezone import EASTERN_TZ


def _mock_cursor(rows: list[tuple[int, str, date, float]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestFindStalePendingSignals:
    def test_signal_older_than_threshold_is_flagged(self) -> None:
        # WHWK: signal_date 2026-08-07, run_date 2026-08-23 - many trading days old, well
        # past a 1-trading-day (24h) threshold.
        rows = [(1, "WHWK", date(2026, 8, 7), 4.76)]
        with patch("scripts.expire_stale_pending_signals.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = _mock_cursor(rows)
            stale = find_stale_pending_signals(run_date=date(2026, 8, 23), max_age_hours=24)

        assert len(stale) == 1
        assert stale[0]["symbol"] == "WHWK"
        assert stale[0]["age_trading_days"] > 1

    def test_signal_within_threshold_is_not_flagged(self) -> None:
        # A signal generated the same day as run_date is 0 trading days old - never stale.
        rows = [(2, "FRESH", date(2026, 8, 22), 10.0)]
        with patch("scripts.expire_stale_pending_signals.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = _mock_cursor(rows)
            stale = find_stale_pending_signals(run_date=date(2026, 8, 22), max_age_hours=24)

        assert stale == []

    def test_only_pending_rows_are_queried(self) -> None:
        with patch("scripts.expire_stale_pending_signals.DatabaseContext") as mock_ctx:
            cur = _mock_cursor([])
            mock_ctx.return_value.__enter__.return_value = cur
            find_stale_pending_signals(run_date=date(2026, 8, 23), max_age_hours=24)

        sql = cur.execute.call_args[0][0]
        assert "execution_status = 'pending'" in sql


class _FrozenDatetime(datetime):
    """A fixed `datetime.now()` so `expire_stale_pending_signals()`'s internal
    `datetime.now(EASTERN_TZ).date()` call is deterministic in tests. Without this, the
    "FRESH" fixture below (a hardcoded literal signal_date meant to be "0 trading days old")
    silently ages past the 1-trading-day threshold as real time passes since this test was
    written - live-confirmed 2026-08-25: `signal_date=2026-08-22` was fresh when written, but
    by the time real trading days advanced to 2026-08-25 it was 2 trading days old, exceeding
    the 24h/1-trading-day threshold and flipping `found` from 1 to 2. Freezing "now" makes the
    fixture's freshness invariant hold regardless of when the test actually runs."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> "_FrozenDatetime":
        # Only ever called here as datetime.now(EASTERN_TZ) - always frozen to that same tz,
        # so no real tz-conversion is needed for this test double's one call site.
        return cls(2026, 8, 22, 16, 0, tzinfo=tz or EASTERN_TZ)


class TestExpireStalePendingSignals:
    def test_dry_run_makes_no_database_writes(self) -> None:
        with (
            patch("scripts.expire_stale_pending_signals._get_max_signal_age_hours", return_value=24),
            patch("scripts.expire_stale_pending_signals.DatabaseContext") as mock_ctx,
            patch("scripts.expire_stale_pending_signals.datetime", _FrozenDatetime),
        ):
            mock_ctx.return_value.__enter__.return_value = _mock_cursor([(1, "WHWK", date(2026, 8, 7), 4.76)])
            result = expire_stale_pending_signals(dry_run=True)

        assert result["dry_run"] is True
        assert result["expired"] == 0
        assert result["found"] == 1
        # Only the read-mode DatabaseContext should have been entered - never "write".
        for call in mock_ctx.call_args_list:
            assert call.args[0] != "write"

    def test_real_run_updates_only_the_stale_ids(self) -> None:
        # FRESH's signal_date matches _FrozenDatetime's frozen "today" (2026-08-22) - always
        # exactly 0 trading days old under the frozen clock, regardless of real wall-clock time.
        read_cur = _mock_cursor([(1, "WHWK", date(2026, 8, 7), 4.76), (2, "FRESH", date(2026, 8, 22), 10.0)])
        write_cur = MagicMock()
        write_cur.rowcount = 1

        def _context(mode: str) -> MagicMock:
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur if mode == "write" else read_cur
            return ctx

        with (
            patch("scripts.expire_stale_pending_signals._get_max_signal_age_hours", return_value=24),
            patch("scripts.expire_stale_pending_signals.DatabaseContext", side_effect=_context),
            patch("scripts.expire_stale_pending_signals.datetime", _FrozenDatetime),
        ):
            result = expire_stale_pending_signals(dry_run=False)

        assert result["expired"] == 1
        assert result["found"] == 1
        update_sql, update_params = write_cur.execute.call_args[0]
        assert "UPDATE algo_signals SET execution_status = 'expired'" in update_sql
        assert update_params == ([1],)

"""Regression test: Phase 8's pending-orders guard must not fire for "dry" mode.

BUG FOUND 2026-08-11: the "CRITICAL GUARD: Check for pending/recent orders that may still be
filling" block used a blocklist (`execution_mode != "paper"`) instead of this codebase's
established allowlist convention for broker-touching checks. Because of the blocklist, "dry"
mode (this system's default outside-market-hours mode - same LOCAL-only-fill semantics as
paper) also ran this guard, querying algo_positions for rows that can never represent a real
in-flight broker order in that mode, and could incorrectly return a "blocked" PhaseResult
whenever any local position happened to be recently created. Fixed to
`execution_mode not in ("paper", "dry")` (`604f03a38`), matching paper mode's pre-existing
(already correct) exemption. "review" mode deliberately keeps the guard active - unlike dry, it
persists real (locally-pending) trade/position rows that a hasty re-run could duplicate.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import run

_MARKET_HOURS_NOW = datetime(2026, 7, 27, 11, 0)  # 11 AM ET, market open, not an early close


def _base_kwargs(execution_mode):
    return {
        "config": {
            "execution_mode": execution_mode,
            "alpaca_paper_trading": True,
        },
        "run_date": date(2026, 7, 27),
        "dry_run": True,
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
    }


def _db_context_with_recent_count(count):
    """Mock DatabaseContext("read") returning a cursor whose fetchone() reports `count`
    positions created in the last 10 minutes - the exact shape the guard's own query expects."""
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (count,)
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def _run_during_market_hours(execution_mode, recent_count):
    with (
        patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt,
        patch(
            "algo.orchestrator.phase8_entry_execution.DatabaseContext",
            return_value=_db_context_with_recent_count(recent_count),
        ),
    ):
        mock_dt.now.return_value = _MARKET_HOURS_NOW
        mock_dt.combine = datetime.combine
        return run(**_base_kwargs(execution_mode))


class TestPendingOrdersGuardDryMode:
    def test_dry_mode_not_blocked_by_recent_positions(self):
        """Even with 5 "recent" local positions, dry mode must not be blocked - there is no
        real broker order behind them to risk duplicating."""
        result = _run_during_market_hours("dry", recent_count=5)

        assert not (result.status == "blocked" and "pending" in (result.error or "").lower()), (
            f"dry mode must not be blocked by the pending-orders guard, got: {result.status} / {result.error}"
        )

    def test_review_mode_still_blocked_by_recent_positions(self):
        """Sanity check: unlike dry mode, "review" persists real locally-pending trade/position
        rows - the guard must still protect it from a duplicate-creating re-run."""
        result = _run_during_market_hours("review", recent_count=5)

        assert result.status == "blocked"
        assert result.halted is False
        assert result.data["entered"] == 0
        assert "pending" in result.error.lower()

    def test_auto_mode_still_blocked_by_recent_positions(self):
        """Sanity check: the guard must still protect real live trading - this behavior must
        not have been accidentally removed for "auto" mode."""
        result = _run_during_market_hours("auto", recent_count=3)

        assert result.status == "blocked"
        assert result.halted is False
        assert result.data["entered"] == 0
        assert "pending" in result.error.lower()

    def test_paper_mode_still_not_blocked(self):
        """Sanity check: paper mode's pre-existing (already correct) behavior is unchanged."""
        result = _run_during_market_hours("paper", recent_count=5)

        assert not (result.status == "blocked" and "pending" in (result.error or "").lower()), (
            f"paper mode must not be blocked by the pending-orders guard, got: {result.status} / {result.error}"
        )

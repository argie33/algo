"""Regression test for the 2026-07-27 fix: AlpacaSyncManager.sync_alpaca_positions wrote to
algo_positions (status/quantity/price) without taking the ALGO_POSITIONS_LOCK_ID advisory
lock that executor.py's entry/exit code already takes for writes to the same table
(executor.py:611-617). Not exploitable in production (orchestrator.py's run lock already
serializes phases within one run), but this local dev environment has multiple concurrent
sessions writing to the same DB outside any run lock - matching the same defense-in-depth
this table's other writers already have. See memory: session_2026-07-27_order_edge_case_audit.

Fixed by splitting the original body into _sync_alpaca_positions_impl and wrapping it in a
thin sync_alpaca_positions() that acquires/releases ALGO_POSITIONS_LOCK_ID around it.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.infrastructure.alpaca_sync_manager import ALGO_POSITIONS_LOCK_ID, AlpacaSyncManager


def _make_manager():
    return object.__new__(AlpacaSyncManager)


class TestSyncAlpacaPositionsAdvisoryLock:
    def test_acquires_and_releases_lock_around_impl(self):
        manager = _make_manager()
        cur = MagicMock()

        with (
            patch.object(manager, "_sync_alpaca_positions_impl", return_value={"synced": 1}) as mock_impl,
            patch("algo.infrastructure.alpaca_sync_manager.acquire_advisory_lock") as mock_acquire,
            patch("algo.infrastructure.alpaca_sync_manager.release_advisory_lock") as mock_release,
        ):
            result = manager.sync_alpaca_positions(cur)

        assert result == {"synced": 1}
        mock_acquire.assert_called_once_with(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
        mock_release.assert_called_once_with(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
        mock_impl.assert_called_once_with(cur)

    def test_lock_released_even_if_impl_raises(self):
        manager = _make_manager()
        cur = MagicMock()

        with (
            patch.object(manager, "_sync_alpaca_positions_impl", side_effect=RuntimeError("boom")),
            patch("algo.infrastructure.alpaca_sync_manager.acquire_advisory_lock") as mock_acquire,
            patch("algo.infrastructure.alpaca_sync_manager.release_advisory_lock") as mock_release,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                manager.sync_alpaca_positions(cur)

        mock_acquire.assert_called_once()
        mock_release.assert_called_once()

    def test_lock_acquired_before_impl_runs(self):
        """Order matters: the lock must be held before any algo_positions write starts."""
        manager = _make_manager()
        cur = MagicMock()
        call_order = []

        def _fake_acquire(*args, **kwargs):
            call_order.append("acquire")

        def _fake_impl(cur):
            call_order.append("impl")
            return {}

        with (
            patch.object(manager, "_sync_alpaca_positions_impl", side_effect=_fake_impl),
            patch("algo.infrastructure.alpaca_sync_manager.acquire_advisory_lock", side_effect=_fake_acquire),
            patch("algo.infrastructure.alpaca_sync_manager.release_advisory_lock"),
        ):
            manager.sync_alpaca_positions(cur)

        assert call_order == ["acquire", "impl"]

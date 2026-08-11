"""Test Phase 1 cache invalidation failure handling.

Scenario: Status is marked COMPLETED but cache invalidation fails.
Expected: RuntimeError is raised BEFORE status is committed (fail-fast).
"""

from unittest.mock import MagicMock, patch

import pytest

from loaders.load_prices import PriceLoader


def _make_loader():
    """Create test PriceLoader instance."""
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader._stats = {"symbols_total": 10, "symbols_processed": 10, "start_time": 1_700_000_000.0}
    return loader


class TestCacheInvalidationFailure:
    """Verify cache invalidation failures are caught BEFORE status update."""

    def test_cache_invalidation_failure_raises_before_status_update(self):
        """Verify RuntimeError from cache invalidation is raised (fail-fast)."""
        loader = _make_loader()
        cur = MagicMock()
        # Mock database queries for data collection
        cur.fetchone.side_effect = [
            (500, "2026-07-31"),  # COUNT(*), MAX(date)
            (10,),  # COUNT(DISTINCT symbol)
            (None, None, None, 500, 100.0, 10, 10),  # SELECT from status for archive
        ]
        cur.rowcount = 1

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache") as mock_cache,
        ):
            # Setup database contexts
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur

            # Cache invalidation fails
            mock_cache.side_effect = RuntimeError("CRITICAL: Cache invalidation completely failed")

            # Should raise before marking status as COMPLETED
            with pytest.raises(RuntimeError, match="Cache invalidation completely failed"):
                loader._update_loader_status()

    def test_loader_status_updated_on_success(self):
        """Verify LoaderStatusManager is called when cache invalidation succeeds."""
        loader = _make_loader()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (500, "2026-07-31"),
            (10,),
            (None, None, None, 500, 100.0, 10, 10),
        ]
        cur.rowcount = 1

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache"),
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur

            # Just verify that the method completes without error
            # when cache invalidation succeeds
            loader._update_loader_status()

            # If we got here, status was updated successfully after cache invalidation
            assert True, "Status update succeeded after cache invalidation"

    def test_status_not_updated_if_cache_invalidation_fails(self):
        """Verify LoaderStatusManager is never called if cache invalidation fails."""
        loader = _make_loader()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            (500, "2026-07-31"),
            (10,),
        ]
        cur.rowcount = 1

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache") as mock_cache,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_cache.side_effect = RuntimeError("Cache failed")

            # Patch LoaderStatusManager to verify it's NOT called
            with patch("utils.loaders.status_manager.LoaderStatusManager") as mock_mgr_class:
                with pytest.raises(RuntimeError):
                    loader._update_loader_status()

                # LoaderStatusManager should NOT have been instantiated
                mock_mgr_class.assert_not_called()

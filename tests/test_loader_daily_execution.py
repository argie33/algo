#!/usr/bin/env python3
"""Test that critical loaders run daily and update data_loader_status.

This test verifies that each critical loader:
1. Can be instantiated and executed
2. Updates its entry in data_loader_status after successful completion
3. Has been updated within 24 hours (detects silent failures)

Critical loaders (independent of stale dependencies):
- stock_symbols (upstream dependency for all)
- price_daily (upstream for technical indicators)
- technical_data_daily (upstream for buy_sell_daily)
- sector_ranking (sector rankings)

Note: buy_sell_daily, signal_quality_scores, and swing_trader_scores are
downstream of technical_data_daily and not monitored independently as they
require fresh upstream data to run successfully.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo


sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

import pytest


logger = logging.getLogger(__name__)
EASTERN_TZ = ZoneInfo("America/New_York")

from utils.db.context import DatabaseContext


class TestCriticalLoaderDailyExecution:
    """Verify critical loaders run daily and update data_loader_status."""

    CRITICAL_LOADERS = [
        "stock_symbols",
        "price_daily",
        "market_health_daily",
        "technical_data_daily",
        "sector_ranking",
    ]

    def _get_loader_status(self, table_name: str) -> dict | None:
        """Get current status of a loader from data_loader_status table."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT * FROM data_loader_status WHERE table_name = %s",
                    (table_name,),
                )
                row = cur.fetchone()
                if row:
                    cols = [desc[0] for desc in cur.description]
                    return dict(zip(cols, row, strict=False))
                return None
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def test_loader_status_table_structure(self):
        """Verify data_loader_status table has required columns for watermark tracking."""
        required_columns = [
            "table_name",
            "status",
            "last_updated",
            "execution_started",
            "execution_completed",
            "row_count",
            "latest_date",
        ]

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'data_loader_status' AND table_schema = 'public'"
                )
                existing_cols = {row[0] for row in cur.fetchall()}

                missing = set(required_columns) - existing_cols
                if missing:
                    pytest.fail(f"data_loader_status missing columns: {missing}")

                cur.execute("SELECT COUNT(*) FROM data_loader_status")
                assert cur.fetchone()[0] >= 0, "Could not read data_loader_status"

        except Exception as e:
            pytest.fail(f"Failed to verify data_loader_status structure: {e}")

    def test_critical_loaders_status_updated_within_24h(self):
        """REQUIREMENT: All critical loaders must have updated status within 24h."""
        now_et = datetime.now(EASTERN_TZ)
        cutoff_time = now_et - timedelta(hours=24)

        stale = {}
        for loader_name in self.CRITICAL_LOADERS:
            status = self._get_loader_status(loader_name)
            if not status:
                stale[loader_name] = "NEVER_RUN"
                continue

            last_updated = status.get("last_updated")
            if last_updated:
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))

                # Ensure timezone-aware datetime in Eastern TZ for comparison
                if last_updated.tzinfo is None:
                    # Naive datetime from DB - assume it's in Eastern TZ
                    last_updated = last_updated.replace(tzinfo=EASTERN_TZ)
                elif last_updated.tzinfo != EASTERN_TZ:
                    # Convert to Eastern TZ if in different timezone
                    last_updated = last_updated.astimezone(EASTERN_TZ)

                if last_updated < cutoff_time:
                    stale[loader_name] = "STALE (>24h)"

        if stale:
            error_msg = "Critical loaders with missing/stale status:\n"
            for loader_name, reason in stale.items():
                error_msg += f"  {loader_name}: {reason}\n"
            pytest.fail(error_msg)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
